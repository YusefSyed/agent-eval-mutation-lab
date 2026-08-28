"""Transactional resumable execution over the typed task plan."""

from __future__ import annotations

from collections.abc import Mapping

from agent_eval_mutation_lab.engine.artifacts import ContentAddressedStore
from agent_eval_mutation_lab.engine.contracts import (
    ArtifactCorruptionError,
    ExecutionFailure,
    ExecutionSummary,
    RunPlan,
    RunState,
    StoreInvariantError,
    TaskRecord,
)
from agent_eval_mutation_lab.engine.plugins import (
    ScorerPlugin,
    default_scorer_plugins,
)
from agent_eval_mutation_lab.engine.runner import record_from_score
from agent_eval_mutation_lab.engine.scheduler import iter_ordered_attempts
from agent_eval_mutation_lab.engine.store import SqliteRunStore


def _validate_cached_record(
    *, task_key: str, ordinal: int, record: TaskRecord
) -> None:
    if record.task_key != task_key or record.ordinal != ordinal:
        raise StoreInvariantError(
            "cached record does not match its canonical task identity"
        )


def run_resumable(
    plan: RunPlan,
    *,
    store: SqliteRunStore,
    artifacts: ContentAddressedStore,
    plugins: Mapping[str, ScorerPlugin] | None = None,
    max_new_tasks: int | None = None,
    workers: int = 1,
    max_in_flight: int | None = None,
) -> ExecutionSummary:
    """Execute unfinished tasks and transactionally reuse verified results."""

    if max_new_tasks is not None and max_new_tasks < 0:
        raise ValueError("max_new_tasks must be non-negative")
    if workers < 1:
        raise ValueError("workers must be positive")
    registry = default_scorer_plugins() if plugins is None else plugins
    store.initialize(plan)
    store.set_run_state(plan.run_key, RunState.RUNNING)

    records_by_ordinal: dict[int, TaskRecord] = {}
    failures: list[ExecutionFailure] = []
    executed = 0
    resumed = 0
    pending_tasks = []

    for task in plan.tasks:
        cached = store.completed_artifact(
            plan.run_key, task.worker.context.task_key
        )
        if cached is not None:
            try:
                record = artifacts.load_task_record(cached)
                _validate_cached_record(
                    task_key=task.worker.context.task_key,
                    ordinal=task.worker.context.ordinal,
                    record=record,
                )
            except ArtifactCorruptionError as error:
                artifacts.quarantine(cached)
                store.reset_task(
                    run_key=plan.run_key,
                    task_key=task.worker.context.task_key,
                    reason=str(error),
                )
                pending_tasks.append(task)
            else:
                records_by_ordinal[record.ordinal] = record
                resumed += 1
        else:
            pending_tasks.append(task)

    selected_tasks = (
        pending_tasks
        if max_new_tasks is None
        else pending_tasks[:max_new_tasks]
    )
    interrupted = len(selected_tasks) < len(pending_tasks)
    for task, attempt in iter_ordered_attempts(
        selected_tasks,
        plugins=registry,
        workers=workers,
        max_in_flight=max_in_flight,
    ):
        executed += 1
        if attempt.failure is not None:
            store.record_failure(
                run_key=plan.run_key, failure=attempt.failure
            )
            failures.append(attempt.failure)
            continue
        if attempt.score is None:
            raise StoreInvariantError("worker attempt has no result")
        record = record_from_score(task, attempt.score)
        artifact = artifacts.put_task_record(record)
        store.commit_task(
            run_key=plan.run_key, task=task, artifact=artifact
        )
        records_by_ordinal[record.ordinal] = record

    pending, completed, failed = store.counts(plan.run_key)
    if failures or failed:
        state = RunState.INCOMPLETE
    elif interrupted or pending:
        state = RunState.INTERRUPTED
    else:
        state = RunState.COMPLETE
    store.set_run_state(plan.run_key, state)
    return ExecutionSummary(
        run_key=plan.run_key,
        state=state,
        expected_tasks=len(plan.tasks),
        completed_tasks=completed,
        failed_tasks=failed,
        executed_tasks=executed,
        resumed_tasks=resumed,
        records=tuple(
            records_by_ordinal[index] for index in sorted(records_by_ordinal)
        ),
        failures=tuple(sorted(failures, key=lambda failure: failure.ordinal)),
    )
