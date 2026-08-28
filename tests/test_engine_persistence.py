from pathlib import Path

import pytest

from agent_eval_mutation_lab.engine.artifacts import ContentAddressedStore
from agent_eval_mutation_lab.engine.contracts import (
    ArtifactCorruptionError,
    PluginDescriptor,
    PluginKind,
    RunState,
    ScoreResult,
    ScorerInput,
    StoreInvariantError,
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
from agent_eval_mutation_lab.engine.runner import run_sequential
from agent_eval_mutation_lab.engine.runtime import run_resumable
from agent_eval_mutation_lab.engine.store import SqliteRunStore

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ExplodingScorer:
    descriptor = PluginDescriptor(
        plugin_id="exploding",
        version="1",
        kind=PluginKind.SCORER,
        implementation_digest="f" * 64,
    )

    def score(
        self, item: ScorerInput, *, context: TaskContext
    ) -> ScoreResult:
        del item, context
        raise RuntimeError("deliberate worker failure")


def _runtime(tmp_path: Path) -> tuple[SqliteRunStore, ContentAddressedStore]:
    return (
        SqliteRunStore(tmp_path / "run.sqlite3"),
        ContentAddressedStore(tmp_path / "objects"),
    )


def test_interrupted_run_resumes_without_reexecuting_committed_tasks(
    tmp_path: Path,
) -> None:
    plan = plan_run(build_default_run_spec(PROJECT_ROOT))
    store, artifacts = _runtime(tmp_path)

    partial = run_resumable(
        plan,
        store=store,
        artifacts=artifacts,
        max_new_tasks=17,
    )
    assert partial.state is RunState.INTERRUPTED
    assert partial.completed_tasks == 17
    assert partial.executed_tasks == 17

    resumed = run_resumable(plan, store=store, artifacts=artifacts)
    assert resumed.state is RunState.COMPLETE
    assert resumed.completed_tasks == 104
    assert resumed.executed_tasks == 87
    assert resumed.resumed_tasks == 17
    assert resumed.records == run_sequential(plan)

    warm = run_resumable(plan, store=store, artifacts=artifacts)
    assert warm.state is RunState.COMPLETE
    assert warm.executed_tasks == 0
    assert warm.resumed_tasks == 104
    assert warm.records == resumed.records


def test_content_addressed_store_detects_corruption(tmp_path: Path) -> None:
    plan = plan_run(build_default_run_spec(PROJECT_ROOT))
    record = run_sequential(plan)[0]
    artifacts = ContentAddressedStore(tmp_path / "objects")
    stored = artifacts.put_task_record(record)
    path = artifacts.root / stored.relative_path
    path.write_bytes(path.read_bytes() + b"corrupt")

    with pytest.raises(ArtifactCorruptionError):
        artifacts.load_task_record(stored)


def test_duplicate_task_key_cannot_change_result_digest(tmp_path: Path) -> None:
    plan = plan_run(build_default_run_spec(PROJECT_ROOT))
    store, artifacts = _runtime(tmp_path)
    store.initialize(plan)
    task = plan.tasks[0]
    first_record = run_sequential(plan)[0]
    first = artifacts.put_task_record(first_record)
    assert store.commit_task(run_key=plan.run_key, task=task, artifact=first)

    changed_record = type(first_record)(
        ordinal=first_record.ordinal,
        task_key=first_record.task_key,
        task_seed=first_record.task_seed,
        case_id=first_record.case_id,
        family=first_record.family,
        evidence_condition=first_record.evidence_condition,
        scorer_id=first_record.scorer_id,
        validation=type(first_record.validation)(
            expected=first_record.validation.expected,
            prediction=None,
            correct=False,
            false_safe=False,
            false_success=False,
            unsupported_safe=False,
            unsupported_success=False,
        ),
    )
    changed = artifacts.put_task_record(changed_record)
    with pytest.raises(StoreInvariantError):
        store.commit_task(
            run_key=plan.run_key, task=task, artifact=changed
        )


def test_plugin_failure_is_not_an_unknown_evaluation(tmp_path: Path) -> None:
    default = default_scorer_plugins()
    plugins: dict[str, ScorerPlugin] = {
        **default,
        "exploding": ExplodingScorer(),
    }
    spec = build_default_run_spec(PROJECT_ROOT)
    failing_spec = type(spec)(
        schema_version=spec.schema_version,
        corpus_id=spec.corpus_id,
        scorer_ids=("exploding",),
        evidence_conditions=("baseline",),
        seed=spec.seed,
        source_digest=spec.source_digest,
        frozen_lock_digest=spec.frozen_lock_digest,
    )
    plan = plan_run(failing_spec, plugins=plugins)
    store, artifacts = _runtime(tmp_path)
    result = run_resumable(
        plan, store=store, artifacts=artifacts, plugins=plugins
    )

    assert result.state is RunState.INCOMPLETE
    assert result.completed_tasks == 0
    assert result.failed_tasks == 13
    assert len(result.failures) == 13
    assert all(failure.error_type == "RuntimeError" for failure in result.failures)
