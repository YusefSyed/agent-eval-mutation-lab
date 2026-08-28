"""Transactional resumable execution over the typed task plan."""

from __future__ import annotations

from collections.abc import Mapping

from agent_eval_mutation_lab.engine.artifacts import ContentAddressedStore
from agent_eval_mutation_lab.engine.contracts import (
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
from agent_eval_mutation_lab.engine.runner import run_task
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
) -> ExecutionSummary:
    """Execute unfinished tasks and transactionally reuse verified results."""

    if max_new_tasks is not None and max_new_tasks < 0:
        raise ValueError("max_new_tasks must be non-negative")
    registry = default_scorer_plugins() if plugins is None else plugins
    store.initialize(plan)
    store.set_run_state(plan.run_key, RunState.RUNNING)

    records: list[TaskRecord] = []
    failures: list[ExecutionFailure] = []
    executed = 0
    resumed = 0
    interrupted = False

    for task in plan.tasks:
        cached = store.completed_artifact(
            plan.run_key, task.worker.context.task_key
        )
        if cached is not None:
            record = artifacts.load_task_record(cached)
            _validate_cached_record(
                task_key=task.worker.context.task_key,
                ordinal=task.worker.context.ordinal,
                record=record,
            )
            records.append(record)
            resumed += 1
            continue

        if max_new_tasks is not None and executed >= max_new_tasks:
            interrupted = True
            break

        try:
            record = run_task(task, plugins=registry)
            artifact = artifacts.put_task_record(record)
            store.commit_task(
                run_key=plan.run_key, task=task, artifact=artifact
            )
            records.append(record)
            executed += 1
        except Exception as error:
            failure = ExecutionFailure(
                ordinal=task.worker.context.ordinal,
                task_key=task.worker.context.task_key,
                error_type=type(error).__name__,
                message=str(error),
            )
            store.record_failure(run_key=plan.run_key, failure=failure)
            failures.append(failure)
            executed += 1

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
        records=tuple(records),
        failures=tuple(failures),
    )
