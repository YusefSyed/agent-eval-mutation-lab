from __future__ import annotations

import threading
import time
from dataclasses import replace
from pathlib import Path

from agent_eval_mutation_lab.engine.artifacts import ContentAddressedStore
from agent_eval_mutation_lab.engine.contracts import (
    ExecutionSummary,
    PluginDescriptor,
    ScoreResult,
    ScorerInput,
    TaskContext,
)
from agent_eval_mutation_lab.engine.planner import (
    build_default_run_spec,
    plan_run,
)
from agent_eval_mutation_lab.engine.plugins import (
    ScorerPlugin,
    default_scorer_plugins,
)
from agent_eval_mutation_lab.engine.runtime import run_resumable
from agent_eval_mutation_lab.engine.store import SqliteRunStore

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DelayedScorer:
    def __init__(
        self,
        delegate: ScorerPlugin,
        completions: list[int],
        lock: threading.Lock,
    ) -> None:
        self._delegate = delegate
        self._completions = completions
        self._lock = lock
        self.descriptor = replace(
            delegate.descriptor,
            implementation_digest=(
                "d" + delegate.descriptor.implementation_digest[1:]
            ),
        )

    descriptor: PluginDescriptor

    def score(
        self, item: ScorerInput, *, context: TaskContext
    ) -> ScoreResult:
        time.sleep((7 - context.ordinal % 7) * 0.0005)
        result = self._delegate.score(item, context=context)
        with self._lock:
            self._completions.append(context.ordinal)
        return result


def _delayed_registry(
    completions: list[int], lock: threading.Lock
) -> dict[str, ScorerPlugin]:
    return {
        name: DelayedScorer(plugin, completions, lock)
        for name, plugin in default_scorer_plugins().items()
    }


def _run(
    root: Path,
    *,
    workers: int,
    plugins: dict[str, ScorerPlugin],
) -> tuple[str, ExecutionSummary]:
    plan = plan_run(build_default_run_spec(PROJECT_ROOT), plugins=plugins)
    result = run_resumable(
        plan,
        store=SqliteRunStore(root / "run.sqlite3"),
        artifacts=ContentAddressedStore(root / "objects"),
        plugins=plugins,
        workers=workers,
    )
    return plan.run_key, result


def test_parallel_completion_order_cannot_change_semantic_results(
    tmp_path: Path,
) -> None:
    sequential_completions: list[int] = []
    parallel_completions: list[int] = []
    sequential_plugins = _delayed_registry(
        sequential_completions, threading.Lock()
    )
    parallel_plugins = _delayed_registry(
        parallel_completions, threading.Lock()
    )

    sequential_key, sequential = _run(
        tmp_path / "sequential", workers=1, plugins=sequential_plugins
    )
    parallel_key, parallel = _run(
        tmp_path / "parallel", workers=4, plugins=parallel_plugins
    )

    assert sequential_key == parallel_key
    assert sequential.records == parallel.records
    assert sequential_completions == list(range(104))
    assert parallel_completions != list(range(104))
    assert [record.ordinal for record in parallel.records] == list(range(104))


def test_parallel_resume_uses_single_committed_identity(tmp_path: Path) -> None:
    completions: list[int] = []
    plugins = _delayed_registry(completions, threading.Lock())
    plan = plan_run(build_default_run_spec(PROJECT_ROOT), plugins=plugins)
    store = SqliteRunStore(tmp_path / "run.sqlite3")
    artifacts = ContentAddressedStore(tmp_path / "objects")

    partial = run_resumable(
        plan,
        store=store,
        artifacts=artifacts,
        plugins=plugins,
        workers=4,
        max_new_tasks=23,
        max_in_flight=8,
    )
    resumed = run_resumable(
        plan,
        store=store,
        artifacts=artifacts,
        plugins=plugins,
        workers=3,
        max_in_flight=6,
    )

    assert partial.completed_tasks == 23
    assert resumed.completed_tasks == 104
    assert resumed.resumed_tasks == 23
    assert resumed.executed_tasks == 81
