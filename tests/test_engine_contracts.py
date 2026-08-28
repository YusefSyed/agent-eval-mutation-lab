from dataclasses import fields
from pathlib import Path

import pytest

from agent_eval_mutation_lab.engine.canonical import (
    canonical_json_bytes,
    scorer_input_payload,
)
from agent_eval_mutation_lab.engine.contracts import (
    PluginContractError,
    PluginDescriptor,
    PluginKind,
    ScoreResult,
    ScorerInput,
    TaskContext,
)
from agent_eval_mutation_lab.engine.equivalence import (
    assert_legacy_v2_equivalence,
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
from agent_eval_mutation_lab.v2_evaluation import run_v2_comparison

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class InvalidScorer:
    descriptor = PluginDescriptor(
        plugin_id="invalid",
        version="1",
        kind=PluginKind.SCORER,
        implementation_digest="0" * 64,
    )

    def score(
        self, item: ScorerInput, *, context: TaskContext
    ) -> ScoreResult:
        del item, context
        return ScoreResult(prediction=1)  # type: ignore[arg-type]


def test_plan_is_canonical_and_content_addressed() -> None:
    spec = build_default_run_spec(PROJECT_ROOT)
    first = plan_run(spec)
    second = plan_run(spec)

    assert first == second
    assert len(first.tasks) == 13 * 2 * 4
    assert [task.worker.context.ordinal for task in first.tasks] == list(
        range(104)
    )
    assert len({task.worker.context.task_key for task in first.tasks}) == 104
    assert len({task.worker.context.seed for task in first.tasks}) == 104
    assert len(first.run_key) == 64


def test_scorer_projection_excludes_oracle_and_execution_truth() -> None:
    plan = plan_run(build_default_run_spec(PROJECT_ROOT))
    item = plan.tasks[0].worker.scorer_input
    field_names = {field.name for field in fields(item)}
    forbidden = {
        "actual_status",
        "actual_effects",
        "attack_success",
        "expected",
        "oracle",
        "outcome",
        "store",
    }
    assert field_names.isdisjoint(forbidden)

    serialized = canonical_json_bytes(scorer_input_payload(item)).decode()
    assert not any(name in serialized for name in forbidden)


def test_sequential_engine_matches_every_legacy_v2_case_result() -> None:
    plan = plan_run(build_default_run_spec(PROJECT_ROOT))
    records = run_sequential(plan)
    assert_legacy_v2_equivalence(records, run_v2_comparison())


def test_invalid_plugin_prediction_fails_contract() -> None:
    default = default_scorer_plugins()
    registry: dict[str, ScorerPlugin] = {
        **default,
        "invalid": InvalidScorer(),
    }
    spec = build_default_run_spec(PROJECT_ROOT)
    invalid_spec = type(spec)(
        schema_version=spec.schema_version,
        corpus_id=spec.corpus_id,
        scorer_ids=("invalid",),
        evidence_conditions=("baseline",),
        seed=spec.seed,
        source_digest=spec.source_digest,
        frozen_lock_digest=spec.frozen_lock_digest,
    )
    plan = plan_run(invalid_spec, plugins=registry)
    with pytest.raises(PluginContractError):
        run_sequential(plan, plugins=registry)
