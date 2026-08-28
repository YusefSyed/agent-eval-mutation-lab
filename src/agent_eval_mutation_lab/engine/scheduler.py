"""Bounded schedule-independent worker execution."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass

from agent_eval_mutation_lab.engine.contracts import (
    ExecutionFailure,
    PlannedTask,
    ScoreResult,
    WorkerTask,
)
from agent_eval_mutation_lab.engine.plugins import ScorerPlugin
from agent_eval_mutation_lab.engine.runner import run_worker


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkerAttempt:
    score: ScoreResult | None
    failure: ExecutionFailure | None

    def __post_init__(self) -> None:
        if (self.score is None) == (self.failure is None):
            raise ValueError("attempt must contain exactly one result or failure")


def _attempt_worker(
    worker: WorkerTask, plugins: Mapping[str, ScorerPlugin]
) -> WorkerAttempt:
    try:
        return WorkerAttempt(
            score=run_worker(worker, plugins=plugins), failure=None
        )
    except Exception as error:
        return WorkerAttempt(
            score=None,
            failure=ExecutionFailure(
                ordinal=worker.context.ordinal,
                task_key=worker.context.task_key,
                error_type=type(error).__name__,
                message=str(error),
            ),
        )


def iter_ordered_attempts(
    tasks: Sequence[PlannedTask],
    *,
    plugins: Mapping[str, ScorerPlugin],
    workers: int,
    max_in_flight: int | None = None,
) -> Iterator[tuple[PlannedTask, WorkerAttempt]]:
    """Yield worker attempts in plan order regardless of completion order."""

    if workers < 1:
        raise ValueError("workers must be positive")
    if not tasks:
        return
    if workers == 1:
        for task in tasks:
            yield task, _attempt_worker(task.worker, plugins)
        return

    limit = max_in_flight if max_in_flight is not None else workers * 2
    if limit < workers:
        raise ValueError("max_in_flight must be at least workers")

    task_iterator = iter(tasks)
    in_flight: dict[Future[WorkerAttempt], PlannedTask] = {}
    buffered: dict[int, tuple[PlannedTask, WorkerAttempt]] = {}
    next_index = 0

    def submit_next(executor: ThreadPoolExecutor) -> bool:
        try:
            task = next(task_iterator)
        except StopIteration:
            return False
        future = executor.submit(_attempt_worker, task.worker, plugins)
        in_flight[future] = task
        return True

    with ThreadPoolExecutor(
        max_workers=workers, thread_name_prefix="agent-eval"
    ) as executor:
        while len(in_flight) < limit and submit_next(executor):
            pass

        while in_flight:
            done, _ = wait(tuple(in_flight), return_when=FIRST_COMPLETED)
            ordered_done = sorted(
                done,
                key=lambda future: in_flight[future].worker.context.ordinal,
            )
            for future in ordered_done:
                task = in_flight.pop(future)
                buffered[task.worker.context.ordinal] = (task, future.result())
                submit_next(executor)

            while next_index < len(tasks):
                ordinal = tasks[next_index].worker.context.ordinal
                ready = buffered.pop(ordinal, None)
                if ready is None:
                    break
                yield ready
                next_index += 1
