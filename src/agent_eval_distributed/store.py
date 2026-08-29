"""PostgreSQL lease store with crash recovery and fenced commits."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from agent_eval_distributed.contracts import (
    DistributedPlan,
    DistributedStoreInvariantError,
    LeaseLostError,
    RunCounts,
    TaskLease,
    _digest,
    _nonempty,
)
from agent_eval_distributed.schema import SCHEMA_SQL, SCHEMA_VERSION


class PostgresLeaseStore:
    """Short-transaction queue using row leases and ``SKIP LOCKED``.

    Worker computation always occurs outside database transactions. A UUID lease
    token fences late workers after expiry or reassignment.
    """

    def __init__(
        self,
        dsn: str,
        *,
        min_pool_size: int = 1,
        max_pool_size: int = 8,
        open_immediately: bool = True,
    ) -> None:
        _nonempty(dsn, "dsn")
        if min_pool_size < 0:
            raise ValueError("min_pool_size must be non-negative")
        if max_pool_size < 1 or min_pool_size > max_pool_size:
            raise ValueError("pool sizes are inconsistent")
        self._pool: ConnectionPool[Any] = ConnectionPool(
            conninfo=dsn,
            min_size=min_pool_size,
            max_size=max_pool_size,
            open=open_immediately,
            kwargs={
                "autocommit": False,
                "row_factory": dict_row,
                "options": (
                    "-c statement_timeout=5000 "
                    "-c lock_timeout=2000 "
                    "-c idle_in_transaction_session_timeout=5000"
                ),
            },
        )

    def __enter__(self) -> PostgresLeaseStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._pool.close()

    def wait(self, *, timeout: float = 30.0) -> None:
        self._pool.wait(timeout=timeout)

    def migrate(self) -> None:
        with self._pool.connection() as connection, connection.transaction():
            connection.execute(SCHEMA_SQL)
            row = connection.execute(
                "SELECT value FROM agent_eval.metadata WHERE key = 'schema_version'"
            ).fetchone()
            if row is None or row["value"] != str(SCHEMA_VERSION):
                raise DistributedStoreInvariantError(
                    "unsupported distributed-store schema version"
                )

    def register_plan(self, plan: DistributedPlan) -> None:
        with self._pool.connection() as connection, connection.transaction():
            connection.execute(
                "INSERT INTO agent_eval.runs"
                "(run_key, plan_digest, expected_tasks) VALUES (%s, %s, %s) "
                "ON CONFLICT (run_key) DO NOTHING",
                (plan.run_key, plan.plan_digest, len(plan.tasks)),
            )
            existing = connection.execute(
                "SELECT plan_digest, expected_tasks FROM agent_eval.runs "
                "WHERE run_key = %s FOR UPDATE",
                (plan.run_key,),
            ).fetchone()
            if existing is None:
                raise DistributedStoreInvariantError("run registration disappeared")
            if existing["plan_digest"] != plan.plan_digest or existing[
                "expected_tasks"
            ] != len(plan.tasks):
                raise DistributedStoreInvariantError(
                    "run key collides with a different plan"
                )

            if plan.tasks:
                with connection.cursor() as cursor:
                    cursor.executemany(
                        "INSERT INTO agent_eval.tasks"
                        "(run_key, task_key, ordinal, payload, payload_digest) "
                        "VALUES (%s, %s, %s, %s, %s) "
                        "ON CONFLICT (run_key, task_key) DO NOTHING",
                        (
                            (
                                plan.run_key,
                                task.task_key,
                                task.ordinal,
                                task.payload,
                                task.payload_digest,
                            )
                            for task in plan.tasks
                        ),
                    )

            rows = connection.execute(
                "SELECT task_key, ordinal, payload, payload_digest "
                "FROM agent_eval.tasks WHERE run_key = %s ORDER BY ordinal",
                (plan.run_key,),
            ).fetchall()
            actual = tuple(
                (
                    row["task_key"],
                    row["ordinal"],
                    bytes(row["payload"]),
                    row["payload_digest"],
                )
                for row in rows
            )
            expected = tuple(
                (
                    task.task_key,
                    task.ordinal,
                    task.payload,
                    task.payload_digest,
                )
                for task in plan.tasks
            )
            if actual != expected:
                raise DistributedStoreInvariantError(
                    "stored tasks differ from canonical plan"
                )

    def claim_next(
        self,
        *,
        run_key: str,
        worker_id: str,
        lease_seconds: float,
    ) -> TaskLease | None:
        _nonempty(run_key, "run_key")
        _nonempty(worker_id, "worker_id")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        token = uuid4()
        with self._pool.connection() as connection, connection.transaction():
            candidate = connection.execute(
                """
                    SELECT task_key, ordinal, payload, payload_digest, state,
                           attempt_count
                    FROM agent_eval.tasks
                    WHERE run_key = %s
                      AND (
                        state = 'pending'
                        OR (state = 'leased' AND lease_expires_at <= clock_timestamp())
                      )
                    ORDER BY ordinal
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                    """,
                (run_key,),
            ).fetchone()
            if candidate is None:
                known = connection.execute(
                    "SELECT 1 FROM agent_eval.runs WHERE run_key = %s",
                    (run_key,),
                ).fetchone()
                if known is None:
                    raise DistributedStoreInvariantError("unknown run key")
                return None

            previous_attempt = candidate["attempt_count"]
            if candidate["state"] == "leased":
                changed = connection.execute(
                    "UPDATE agent_eval.attempts "
                    "SET outcome = 'expired', finished_at = clock_timestamp() "
                    "WHERE run_key = %s AND task_key = %s AND attempt_no = %s "
                    "AND outcome IS NULL",
                    (run_key, candidate["task_key"], previous_attempt),
                ).rowcount
                if changed != 1:
                    raise DistributedStoreInvariantError(
                        "expired lease has no active attempt"
                    )

            attempt_no = previous_attempt + 1
            leased = connection.execute(
                """
                    UPDATE agent_eval.tasks
                    SET state = 'leased',
                        attempt_count = %s,
                        lease_owner = %s,
                        lease_token = %s,
                        lease_expires_at = clock_timestamp()
                            + (%s * interval '1 second'),
                        last_error_type = NULL,
                        last_error_message = NULL,
                        updated_at = clock_timestamp()
                    WHERE run_key = %s AND task_key = %s
                    RETURNING lease_expires_at
                    """,
                (
                    attempt_no,
                    worker_id,
                    token,
                    lease_seconds,
                    run_key,
                    candidate["task_key"],
                ),
            ).fetchone()
            if leased is None:
                raise DistributedStoreInvariantError("lease update lost locked task")
            connection.execute(
                """
                    INSERT INTO agent_eval.attempts(
                        run_key, task_key, attempt_no, worker_id, lease_token,
                        leased_at, lease_expires_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, clock_timestamp(), %s
                    )
                    """,
                (
                    run_key,
                    candidate["task_key"],
                    attempt_no,
                    worker_id,
                    token,
                    leased["lease_expires_at"],
                ),
            )
            return _lease(
                run_key=run_key,
                worker_id=worker_id,
                token=token,
                attempt_no=attempt_no,
                expires_at=leased["lease_expires_at"],
                row=candidate,
            )

    def heartbeat(self, *, lease: TaskLease, lease_seconds: float) -> TaskLease:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        with self._pool.connection() as connection, connection.transaction():
            row = connection.execute(
                """
                    UPDATE agent_eval.tasks
                    SET lease_expires_at = clock_timestamp()
                            + (%s * interval '1 second'),
                        updated_at = clock_timestamp()
                    WHERE run_key = %s
                      AND task_key = %s
                      AND state = 'leased'
                      AND lease_owner = %s
                      AND lease_token = %s
                      AND attempt_count = %s
                      AND lease_expires_at > clock_timestamp()
                    RETURNING lease_expires_at
                    """,
                (
                    lease_seconds,
                    lease.run_key,
                    lease.task_key,
                    lease.worker_id,
                    lease.token,
                    lease.attempt_no,
                ),
            ).fetchone()
            if row is None:
                raise LeaseLostError("lease expired or belongs to another worker")
            return TaskLease(
                run_key=lease.run_key,
                task_key=lease.task_key,
                ordinal=lease.ordinal,
                payload=lease.payload,
                payload_digest=lease.payload_digest,
                worker_id=lease.worker_id,
                token=lease.token,
                attempt_no=lease.attempt_no,
                expires_at=row["lease_expires_at"],
            )

    def complete(self, *, lease: TaskLease, result_digest: str) -> bool:
        _digest(result_digest, "result_digest")
        with self._pool.connection() as connection, connection.transaction():
            task = _locked_task(connection, lease)
            if task["state"] == "complete":
                if task["result_digest"] != result_digest:
                    raise DistributedStoreInvariantError(
                        "task already has a different terminal digest"
                    )
                return False
            _require_live_lease(task, lease)
            changed = connection.execute(
                """
                    UPDATE agent_eval.tasks
                    SET state = 'complete',
                        result_digest = %s,
                        completed_at = clock_timestamp(),
                        lease_owner = NULL,
                        lease_token = NULL,
                        lease_expires_at = NULL,
                        updated_at = clock_timestamp()
                    WHERE run_key = %s AND task_key = %s
                    """,
                (result_digest, lease.run_key, lease.task_key),
            ).rowcount
            attempt_changed = connection.execute(
                """
                    UPDATE agent_eval.attempts
                    SET outcome = 'complete', result_digest = %s,
                        finished_at = clock_timestamp()
                    WHERE run_key = %s AND task_key = %s AND attempt_no = %s
                      AND worker_id = %s AND lease_token = %s AND outcome IS NULL
                    """,
                (
                    result_digest,
                    lease.run_key,
                    lease.task_key,
                    lease.attempt_no,
                    lease.worker_id,
                    lease.token,
                ),
            ).rowcount
            if changed != 1 or attempt_changed != 1:
                raise DistributedStoreInvariantError(
                    "terminal commit did not update exactly one task and attempt"
                )
            return True

    def record_failure(
        self,
        *,
        lease: TaskLease,
        error_type: str,
        message: str,
        retryable: bool,
    ) -> None:
        _nonempty(error_type, "error_type")
        _nonempty(message, "message")
        outcome = "retryable_failure" if retryable else "terminal_failure"
        state = "pending" if retryable else "failed"
        with self._pool.connection() as connection, connection.transaction():
            task = _locked_task(connection, lease)
            _require_live_lease(task, lease)
            changed = connection.execute(
                """
                    UPDATE agent_eval.tasks
                    SET state = %s,
                        lease_owner = NULL,
                        lease_token = NULL,
                        lease_expires_at = NULL,
                        last_error_type = %s,
                        last_error_message = %s,
                        updated_at = clock_timestamp()
                    WHERE run_key = %s AND task_key = %s
                    """,
                (
                    state,
                    error_type,
                    message[:1000],
                    lease.run_key,
                    lease.task_key,
                ),
            ).rowcount
            attempt_changed = connection.execute(
                """
                    UPDATE agent_eval.attempts
                    SET outcome = %s, error_type = %s, error_message = %s,
                        finished_at = clock_timestamp()
                    WHERE run_key = %s AND task_key = %s AND attempt_no = %s
                      AND worker_id = %s AND lease_token = %s AND outcome IS NULL
                    """,
                (
                    outcome,
                    error_type,
                    message[:1000],
                    lease.run_key,
                    lease.task_key,
                    lease.attempt_no,
                    lease.worker_id,
                    lease.token,
                ),
            ).rowcount
            if changed != 1 or attempt_changed != 1:
                raise DistributedStoreInvariantError(
                    "failure commit did not update exactly one task and attempt"
                )

    def counts(self, *, run_key: str) -> RunCounts:
        _nonempty(run_key, "run_key")
        with self._pool.connection() as connection:
            rows = connection.execute(
                "SELECT state, count(*) AS count FROM agent_eval.tasks "
                "WHERE run_key = %s GROUP BY state",
                (run_key,),
            ).fetchall()
            if not rows:
                known = connection.execute(
                    "SELECT 1 FROM agent_eval.runs WHERE run_key = %s",
                    (run_key,),
                ).fetchone()
                if known is None:
                    raise DistributedStoreInvariantError("unknown run key")
        counts = {row["state"]: row["count"] for row in rows}
        return RunCounts(
            pending=counts.get("pending", 0),
            leased=counts.get("leased", 0),
            complete=counts.get("complete", 0),
            failed=counts.get("failed", 0),
        )


def _locked_task(connection: Connection[Any], lease: TaskLease) -> dict[str, Any]:
    row = connection.execute(
        "SELECT state, result_digest, lease_owner, lease_token, "
        "lease_expires_at, attempt_count, "
        "lease_expires_at > clock_timestamp() AS lease_live "
        "FROM agent_eval.tasks WHERE run_key = %s AND task_key = %s FOR UPDATE",
        (lease.run_key, lease.task_key),
    ).fetchone()
    if row is None:
        raise DistributedStoreInvariantError("lease task is not registered")
    return cast(dict[str, Any], row)


def _require_live_lease(task: dict[str, Any], lease: TaskLease) -> None:
    if (
        task["state"] != "leased"
        or task["lease_owner"] != lease.worker_id
        or task["lease_token"] != lease.token
        or task["attempt_count"] != lease.attempt_no
        or not task["lease_live"]
    ):
        raise LeaseLostError("lease expired or belongs to another worker")


def _lease(
    *,
    run_key: str,
    worker_id: str,
    token: UUID,
    attempt_no: int,
    expires_at: datetime,
    row: dict[str, Any],
) -> TaskLease:
    return TaskLease(
        run_key=run_key,
        task_key=row["task_key"],
        ordinal=row["ordinal"],
        payload=bytes(row["payload"]),
        payload_digest=row["payload_digest"],
        worker_id=worker_id,
        token=token,
        attempt_no=attempt_no,
        expires_at=expires_at,
    )
