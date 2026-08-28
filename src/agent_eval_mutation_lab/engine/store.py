"""Single-writer transactional SQLite run ledger."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from agent_eval_mutation_lab.engine.canonical import (
    canonical_json_bytes,
    run_spec_payload,
)
from agent_eval_mutation_lab.engine.contracts import (
    ExecutionFailure,
    PlannedTask,
    RunPlan,
    RunState,
    StoredArtifact,
    StoreInvariantError,
    TaskState,
)

SCHEMA_VERSION = 1


class SqliteRunStore:
    """Derived operational state; canonical JSON artifacts remain authoritative."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _create_schema(self, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs (
                run_key TEXT PRIMARY KEY,
                spec_json TEXT NOT NULL,
                state TEXT NOT NULL,
                expected_tasks INTEGER NOT NULL CHECK (expected_tasks >= 0)
            );
            CREATE TABLE IF NOT EXISTS artifacts (
                digest TEXT PRIMARY KEY,
                media_type TEXT NOT NULL,
                size INTEGER NOT NULL CHECK (size >= 0),
                relative_path TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tasks (
                run_key TEXT NOT NULL REFERENCES runs(run_key),
                task_key TEXT NOT NULL,
                ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
                state TEXT NOT NULL,
                result_digest TEXT REFERENCES artifacts(digest),
                error_type TEXT,
                error_message TEXT,
                PRIMARY KEY (run_key, task_key),
                UNIQUE (run_key, ordinal)
            );
            """
        )
        existing = connection.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone()
        if existing is None:
            connection.execute(
                "INSERT INTO metadata(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
        elif existing["value"] != str(SCHEMA_VERSION):
            raise StoreInvariantError(
                "unsupported SQLite run-store schema version"
            )

    def initialize(self, plan: RunPlan) -> None:
        spec_json = canonical_json_bytes(run_spec_payload(plan.spec)).decode()
        with self._connect() as connection:
            self._create_schema(connection)
            existing = connection.execute(
                "SELECT spec_json, expected_tasks FROM runs WHERE run_key = ?",
                (plan.run_key,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    "INSERT INTO runs(run_key, spec_json, state, expected_tasks) "
                    "VALUES(?, ?, ?, ?)",
                    (
                        plan.run_key,
                        spec_json,
                        RunState.PLANNED.value,
                        len(plan.tasks),
                    ),
                )
            elif (
                existing["spec_json"] != spec_json
                or existing["expected_tasks"] != len(plan.tasks)
            ):
                raise StoreInvariantError(
                    "run key collides with a different specification"
                )

            for task in plan.tasks:
                connection.execute(
                    "INSERT OR IGNORE INTO tasks"
                    "(run_key, task_key, ordinal, state) VALUES(?, ?, ?, ?)",
                    (
                        plan.run_key,
                        task.worker.context.task_key,
                        task.worker.context.ordinal,
                        TaskState.PENDING.value,
                    ),
                )

            rows = connection.execute(
                "SELECT task_key, ordinal FROM tasks WHERE run_key = ? "
                "ORDER BY ordinal",
                (plan.run_key,),
            ).fetchall()
            expected = [
                (task.worker.context.task_key, task.worker.context.ordinal)
                for task in plan.tasks
            ]
            actual = [(row["task_key"], row["ordinal"]) for row in rows]
            if actual != expected:
                raise StoreInvariantError(
                    "stored task plan differs from the canonical task plan"
                )

    def set_run_state(self, run_key: str, state: RunState) -> None:
        with self._connect() as connection:
            changed = connection.execute(
                "UPDATE runs SET state = ? WHERE run_key = ?",
                (state.value, run_key),
            ).rowcount
            if changed != 1:
                raise StoreInvariantError(f"unknown run {run_key}")

    def completed_artifact(
        self, run_key: str, task_key: str
    ) -> StoredArtifact | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT a.digest, a.media_type, a.size, a.relative_path "
                "FROM tasks t JOIN artifacts a ON a.digest = t.result_digest "
                "WHERE t.run_key = ? AND t.task_key = ? AND t.state = ?",
                (run_key, task_key, TaskState.COMPLETE.value),
            ).fetchone()
        if row is None:
            return None
        return StoredArtifact(
            digest=row["digest"],
            media_type=row["media_type"],
            size=row["size"],
            relative_path=row["relative_path"],
        )

    def commit_task(
        self,
        *,
        run_key: str,
        task: PlannedTask,
        artifact: StoredArtifact,
    ) -> bool:
        """Commit exactly once; identical recommits are harmless."""

        with self._connect() as connection:
            self._create_schema(connection)
            row = connection.execute(
                "SELECT state, result_digest FROM tasks "
                "WHERE run_key = ? AND task_key = ?",
                (run_key, task.worker.context.task_key),
            ).fetchone()
            if row is None:
                raise StoreInvariantError("task is not part of the stored plan")
            if row["state"] == TaskState.COMPLETE.value:
                if row["result_digest"] != artifact.digest:
                    raise StoreInvariantError(
                        "task key produced a different result digest"
                    )
                return False

            existing_artifact = connection.execute(
                "SELECT media_type, size, relative_path FROM artifacts "
                "WHERE digest = ?",
                (artifact.digest,),
            ).fetchone()
            metadata = (
                artifact.media_type,
                artifact.size,
                artifact.relative_path,
            )
            if existing_artifact is None:
                connection.execute(
                    "INSERT INTO artifacts"
                    "(digest, media_type, size, relative_path) "
                    "VALUES(?, ?, ?, ?)",
                    (artifact.digest, *metadata),
                )
            elif tuple(existing_artifact) != metadata:
                raise StoreInvariantError(
                    "artifact digest collides with different metadata"
                )

            connection.execute(
                "UPDATE tasks SET state = ?, result_digest = ?, "
                "error_type = NULL, error_message = NULL "
                "WHERE run_key = ? AND task_key = ?",
                (
                    TaskState.COMPLETE.value,
                    artifact.digest,
                    run_key,
                    task.worker.context.task_key,
                ),
            )
            return True

    def record_failure(
        self, *, run_key: str, failure: ExecutionFailure
    ) -> None:
        with self._connect() as connection:
            changed = connection.execute(
                "UPDATE tasks SET state = ?, result_digest = NULL, "
                "error_type = ?, error_message = ? "
                "WHERE run_key = ? AND task_key = ?",
                (
                    TaskState.FAILED.value,
                    failure.error_type,
                    failure.message[:1000],
                    run_key,
                    failure.task_key,
                ),
            ).rowcount
            if changed != 1:
                raise StoreInvariantError("failed task is not in the run plan")

    def reset_task(
        self, *, run_key: str, task_key: str, reason: str
    ) -> None:
        """Invalidate a corrupt cached result while preserving diagnostics."""

        with self._connect() as connection:
            changed = connection.execute(
                "UPDATE tasks SET state = ?, result_digest = NULL, "
                "error_type = ?, error_message = ? "
                "WHERE run_key = ? AND task_key = ?",
                (
                    TaskState.PENDING.value,
                    "ArtifactCorruptionError",
                    reason[:1000],
                    run_key,
                    task_key,
                ),
            ).rowcount
            if changed != 1:
                raise StoreInvariantError("task reset target is not in the run plan")

    def counts(self, run_key: str) -> tuple[int, int, int]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT state, COUNT(*) AS count FROM tasks "
                "WHERE run_key = ? GROUP BY state",
                (run_key,),
            ).fetchall()
        counts = {row["state"]: row["count"] for row in rows}
        return (
            counts.get(TaskState.PENDING.value, 0),
            counts.get(TaskState.COMPLETE.value, 0),
            counts.get(TaskState.FAILED.value, 0),
        )
