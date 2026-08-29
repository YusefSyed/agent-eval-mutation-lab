from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from multiprocessing import get_context
from typing import Any
from uuid import uuid4

import psycopg
import pytest

from agent_eval_distributed.contracts import (
    DistributedPlan,
    DistributedStoreInvariantError,
    DistributedTask,
    LeaseLostError,
)
from agent_eval_distributed.store import PostgresLeaseStore

DSN = os.environ.get("AGENT_EVAL_TEST_POSTGRES_DSN")
pytestmark = pytest.mark.skipif(
    DSN is None, reason="PostgreSQL integration DSN not set"
)


def _plan(run_key: str, count: int = 4) -> DistributedPlan:
    tasks = tuple(
        DistributedTask.from_payload(
            task_key=f"task-{index}",
            ordinal=index,
            payload=f'{{"index":{index}}}'.encode(),
        )
        for index in range(count)
    )
    return DistributedPlan.from_tasks(run_key=f"{run_key}-{uuid4().hex}", tasks=tasks)


def _claim_then_block(dsn: str, run_key: str, messages: Any) -> None:
    child_store = PostgresLeaseStore(dsn, min_pool_size=1, max_pool_size=1)
    child_store.wait()
    lease = child_store.claim_next(
        run_key=run_key,
        worker_id="worker-killed-after-claim",
        lease_seconds=0.15,
    )
    if lease is None:
        raise RuntimeError("worker found no claimable task")
    messages.put(lease)
    time.sleep(60)


@pytest.fixture
def store() -> PostgresLeaseStore:
    assert DSN is not None
    lease_store = PostgresLeaseStore(DSN, min_pool_size=1, max_pool_size=8)
    lease_store.wait()
    lease_store.migrate()
    yield lease_store
    lease_store.close()


def test_parallel_workers_claim_distinct_tasks(store: PostgresLeaseStore) -> None:
    plan = _plan("parallel-claims")
    store.register_plan(plan)

    def claim(worker: str):  # type: ignore[no-untyped-def]
        return store.claim_next(run_key=plan.run_key, worker_id=worker, lease_seconds=5)

    with ThreadPoolExecutor(max_workers=4) as executor:
        leases = tuple(executor.map(claim, (f"worker-{index}" for index in range(4))))

    assert all(lease is not None for lease in leases)
    assert {lease.task_key for lease in leases if lease is not None} == {
        task.task_key for task in plan.tasks
    }
    assert store.counts(run_key=plan.run_key).leased == 4


def test_plan_registration_is_concurrent_and_collision_fenced(
    store: PostgresLeaseStore,
) -> None:
    plan = _plan("registration")
    with ThreadPoolExecutor(max_workers=4) as executor:
        tuple(executor.map(store.register_plan, (plan,) * 4))
    assert store.counts(run_key=plan.run_key).total == len(plan.tasks)

    changed_tasks = (
        DistributedTask.from_payload(task_key="changed", ordinal=0, payload=b"changed"),
    )
    collision = DistributedPlan.from_tasks(run_key=plan.run_key, tasks=changed_tasks)
    with pytest.raises(DistributedStoreInvariantError, match="different plan"):
        store.register_plan(collision)


def test_unknown_run_fails_closed(store: PostgresLeaseStore) -> None:
    with pytest.raises(DistributedStoreInvariantError, match="unknown"):
        store.claim_next(
            run_key=f"missing-{uuid4().hex}",
            worker_id="worker",
            lease_seconds=1,
        )
    with pytest.raises(DistributedStoreInvariantError, match="unknown"):
        store.counts(run_key=f"missing-{uuid4().hex}")


def test_expired_lease_is_reclaimed_and_fences_old_worker(
    store: PostgresLeaseStore,
) -> None:
    plan = _plan("lease-recovery", count=1)
    store.register_plan(plan)
    first = store.claim_next(
        run_key=plan.run_key, worker_id="worker-a", lease_seconds=0.05
    )
    assert first is not None
    time.sleep(0.08)
    second = store.claim_next(
        run_key=plan.run_key, worker_id="worker-b", lease_seconds=5
    )
    assert second is not None
    assert second.task_key == first.task_key
    assert second.attempt_no == 2
    assert second.token != first.token

    with pytest.raises(LeaseLostError):
        store.complete(lease=first, result_digest=sha256(b"late").hexdigest())
    assert store.complete(lease=second, result_digest=sha256(b"ok").hexdigest())


def test_forced_worker_termination_recovers_and_fences_attempt(
    store: PostgresLeaseStore,
) -> None:
    assert DSN is not None
    plan = _plan("forced-process-termination", count=1)
    store.register_plan(plan)
    context = get_context("spawn")
    messages = context.Queue()
    process = context.Process(
        target=_claim_then_block,
        args=(DSN, plan.run_key, messages),
        name="lease-holder-that-will-be-killed",
    )
    try:
        process.start()
        killed_lease = messages.get(timeout=15)
        process.kill()
        process.join(timeout=5)
        assert not process.is_alive()
        assert process.exitcode is not None and process.exitcode != 0

        time.sleep(0.25)
        recovered = store.claim_next(
            run_key=plan.run_key,
            worker_id="replacement-worker",
            lease_seconds=5,
        )
        assert recovered is not None
        assert recovered.task_key == killed_lease.task_key
        assert recovered.attempt_no == 2
        assert recovered.token != killed_lease.token

        with pytest.raises(LeaseLostError):
            store.complete(
                lease=killed_lease,
                result_digest=sha256(b"late-result").hexdigest(),
            )
        assert store.complete(
            lease=recovered,
            result_digest=sha256(b"replacement-result").hexdigest(),
        )

        with psycopg.connect(DSN) as connection:
            rows = connection.execute(
                "SELECT attempt_no, outcome FROM agent_eval.attempts "
                "WHERE run_key = %s AND task_key = %s ORDER BY attempt_no",
                (plan.run_key, recovered.task_key),
            ).fetchall()
        assert rows == [(1, "expired"), (2, "complete")]
    finally:
        if process.is_alive():
            process.kill()
            process.join(timeout=5)
        messages.close()


def test_terminal_commit_is_idempotent_but_digest_fenced(
    store: PostgresLeaseStore,
) -> None:
    plan = _plan("terminal-fence", count=1)
    store.register_plan(plan)
    lease = store.claim_next(run_key=plan.run_key, worker_id="worker", lease_seconds=5)
    assert lease is not None
    digest = sha256(b"result").hexdigest()
    assert store.complete(lease=lease, result_digest=digest)
    assert not store.complete(lease=lease, result_digest=digest)
    with pytest.raises(DistributedStoreInvariantError, match="different"):
        store.complete(lease=lease, result_digest=sha256(b"other").hexdigest())


def test_heartbeat_extends_only_a_live_lease(store: PostgresLeaseStore) -> None:
    plan = _plan("heartbeat", count=1)
    store.register_plan(plan)
    lease = store.claim_next(
        run_key=plan.run_key, worker_id="worker", lease_seconds=0.05
    )
    assert lease is not None
    extended = store.heartbeat(lease=lease, lease_seconds=0.25)
    assert extended.expires_at > lease.expires_at
    time.sleep(0.08)
    assert store.complete(lease=extended, result_digest=sha256(b"result").hexdigest())


def test_retryable_failure_returns_task_to_queue(store: PostgresLeaseStore) -> None:
    plan = _plan("retryable-failure", count=1)
    store.register_plan(plan)
    first = store.claim_next(
        run_key=plan.run_key, worker_id="worker-a", lease_seconds=5
    )
    assert first is not None
    store.record_failure(
        lease=first,
        error_type="TransportError",
        message="response-free disconnect",
        retryable=True,
    )
    second = store.claim_next(
        run_key=plan.run_key, worker_id="worker-b", lease_seconds=5
    )
    assert second is not None
    assert second.attempt_no == 2
    assert second.task_key == first.task_key


def test_terminal_failure_is_not_released(store: PostgresLeaseStore) -> None:
    plan = _plan("terminal-failure", count=1)
    store.register_plan(plan)
    lease = store.claim_next(run_key=plan.run_key, worker_id="worker", lease_seconds=5)
    assert lease is not None
    store.record_failure(
        lease=lease,
        error_type="ContractError",
        message="invalid terminal result",
        retryable=False,
    )
    assert (
        store.claim_next(run_key=plan.run_key, worker_id="other", lease_seconds=5)
        is None
    )
    counts = store.counts(run_key=plan.run_key)
    assert counts.failed == 1
    assert counts.pending == counts.leased == counts.complete == 0
