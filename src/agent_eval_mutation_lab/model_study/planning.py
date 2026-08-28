"""Build the 52-input model-visible plan and separate oracle join ledger."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path

from agent_eval_mutation_lab.engine.contracts import RunSpec
from agent_eval_mutation_lab.engine.planner import (
    DEFAULT_SCORERS,
    build_default_run_spec,
    plan_run,
)
from agent_eval_mutation_lab.model_study.projection import (
    JSONPayload,
    project_model_input,
)
from agent_eval_mutation_lab.models import Prediction


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelInputRecord:
    """Coordinator envelope; only ``payload`` is sent to a model."""

    ordinal: int
    input_ref: str
    payload_digest: str
    payload: JSONPayload


@dataclass(frozen=True, slots=True, kw_only=True)
class OracleJoinRecord:
    """Private-to-analysis metadata that never enters live inference."""

    input_ref: str
    case_id: str
    family: str
    evidence_condition: str
    expected: Prediction


def build_model_study_inputs(
    project_root: Path,
) -> tuple[tuple[ModelInputRecord, ...], tuple[OracleJoinRecord, ...]]:
    """Project one copy of each case/condition input, excluding scorer replication."""

    default_spec = build_default_run_spec(project_root)
    study_spec = _single_scorer_spec(default_spec)
    plan = plan_run(study_spec)
    model_records: list[ModelInputRecord] = []
    oracle_records: list[OracleJoinRecord] = []
    for ordinal, task in enumerate(plan.tasks):
        payload = project_model_input(task.worker.scorer_input).payload()
        input_ref = f"input-{ordinal:04d}"
        model_records.append(
            ModelInputRecord(
                ordinal=ordinal,
                input_ref=input_ref,
                payload_digest=hashlib.sha256(_canonical_json(payload)).hexdigest(),
                payload=payload,
            )
        )
        oracle_records.append(
            OracleJoinRecord(
                input_ref=input_ref,
                case_id=task.case_id,
                family=task.family,
                evidence_condition=task.evidence_condition,
                expected=task.oracle.attack_success,
            )
        )
    if len(model_records) != 52:
        raise RuntimeError("model study input plan must contain exactly 52 records")
    return tuple(model_records), tuple(oracle_records)


def model_record_payload(record: ModelInputRecord) -> dict[str, object]:
    """Serialize the live-runner envelope without oracle metadata."""

    return {
        "ordinal": record.ordinal,
        "input_ref": record.input_ref,
        "payload_digest": record.payload_digest,
        "payload": record.payload,
    }


def oracle_record_payload(record: OracleJoinRecord) -> dict[str, object]:
    """Serialize the coordinator-only analysis ledger."""

    return {
        "input_ref": record.input_ref,
        "case_id": record.case_id,
        "family": record.family,
        "evidence_condition": record.evidence_condition,
        "expected": record.expected,
    }


def _single_scorer_spec(spec: RunSpec) -> RunSpec:
    return replace(spec, scorer_ids=(DEFAULT_SCORERS[0],))


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, allow_nan=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode()
