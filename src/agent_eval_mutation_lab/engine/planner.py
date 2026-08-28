"""Canonical task planning for the v1/v2 evidence matrix."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from agent_eval_mutation_lab.cases import benchmark_cases
from agent_eval_mutation_lab.engine.canonical import (
    canonical_json_bytes,
    plugin_payload,
    run_spec_payload,
    scorer_input_payload,
    sha256_bytes,
    sha256_file,
    source_tree_digest,
)
from agent_eval_mutation_lab.engine.contracts import (
    OracleTruth,
    PlannedTask,
    RunPlan,
    RunSpec,
    TaskContext,
    WorkerTask,
)
from agent_eval_mutation_lab.engine.plugins import (
    ScorerPlugin,
    default_scorer_plugins,
    to_scorer_input,
)
from agent_eval_mutation_lab.receipt_ablations import _ablate
from agent_eval_mutation_lab.simulator import execute

DEFAULT_SCORERS = (
    "receipt_aware_v1_frozen",
    "evidence_dominance_v2_experimental",
)
DEFAULT_CONDITIONS = (
    "baseline",
    "remove_prohibited_receipts",
    "remove_effect_records",
    "replace_success_with_timeout",
)


def build_default_run_spec(project_root: Path, *, seed: int = 20260828) -> RunSpec:
    project_root = project_root.resolve()
    return RunSpec(
        schema_version=1,
        corpus_id="execution-semantics-v1",
        scorer_ids=DEFAULT_SCORERS,
        evidence_conditions=DEFAULT_CONDITIONS,
        seed=seed,
        source_digest=source_tree_digest(
            project_root / "src/agent_eval_mutation_lab"
        ),
        frozen_lock_digest=sha256_file(
            project_root / "artifacts/baseline-v1/LOCK.json"
        ),
    )


def _task_key(
    *,
    spec: RunSpec,
    case_id: str,
    family: str,
    condition: str,
    plugin: ScorerPlugin,
    scorer_input: object,
    expected: bool | None,
) -> str:
    payload = {
        "schema": "engine-task-v1",
        "run_spec": run_spec_payload(spec),
        "case_id": case_id,
        "family": family,
        "evidence_condition": condition,
        "plugin": plugin_payload(plugin.descriptor),
        "scorer_input": scorer_input,
        "oracle_attack_success": expected,
    }
    return sha256_bytes(canonical_json_bytes(payload))


def _task_seed(run_seed: int, task_key: str) -> int:
    material = f"{run_seed}:{task_key}".encode()
    return int(sha256_bytes(material)[:16], 16)


def plan_run(
    spec: RunSpec,
    *,
    plugins: Mapping[str, ScorerPlugin] | None = None,
) -> RunPlan:
    registry = plugins or default_scorer_plugins()
    missing = set(spec.scorer_ids) - registry.keys()
    if missing:
        raise ValueError(f"unknown scorer plugins: {sorted(missing)}")
    unsupported = set(spec.evidence_conditions) - set(DEFAULT_CONDITIONS)
    if unsupported:
        raise ValueError(f"unknown evidence conditions: {sorted(unsupported)}")

    tasks: list[PlannedTask] = []
    ordinal = 0
    for condition in spec.evidence_conditions:
        for scorer_id in spec.scorer_ids:
            plugin = registry[scorer_id]
            for case in benchmark_cases():
                outcome, observation = execute(case.scenario)
                scorer_input = to_scorer_input(_ablate(observation, condition))
                task_key = _task_key(
                    spec=spec,
                    case_id=case.case_id,
                    family=case.scenario.family,
                    condition=condition,
                    plugin=plugin,
                    scorer_input=scorer_input_payload(scorer_input),
                    expected=outcome.attack_success,
                )
                tasks.append(
                    PlannedTask(
                        worker=WorkerTask(
                            context=TaskContext(
                                task_key=task_key,
                                ordinal=ordinal,
                                seed=_task_seed(spec.seed, task_key),
                            ),
                            scorer_id=scorer_id,
                            scorer_input=scorer_input,
                        ),
                        case_id=case.case_id,
                        family=case.scenario.family,
                        evidence_condition=condition,
                        oracle=OracleTruth(
                            attack_success=outcome.attack_success
                        ),
                    )
                )
                ordinal += 1

    run_key = sha256_bytes(
        canonical_json_bytes(
            {
                "schema": "engine-run-v1",
                "spec": run_spec_payload(spec),
                "task_keys": [task.worker.context.task_key for task in tasks],
            }
        )
    )
    return RunPlan(spec=spec, run_key=run_key, tasks=tuple(tasks))
