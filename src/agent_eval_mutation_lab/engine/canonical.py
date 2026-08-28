"""Canonical serialization and content identity helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from agent_eval_mutation_lab.engine.contracts import (
    PluginDescriptor,
    RunSpec,
    ScorerInput,
    TaskRecord,
    ValidationResult,
)
from agent_eval_mutation_lab.models import Prediction


def canonical_json_bytes(value: object) -> bytes:
    """Serialize JSON-compatible data without operational whitespace."""

    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_tree_digest(package_root: Path) -> str:
    """Hash Python sources with stable relative names and length framing."""

    digest = hashlib.sha256()
    files = sorted(package_root.rglob("*.py"))
    if not files:
        raise ValueError(f"no Python source files found below {package_root}")
    for path in files:
        relative = path.relative_to(package_root).as_posix().encode()
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def plugin_payload(descriptor: PluginDescriptor) -> dict[str, object]:
    return {
        "plugin_id": descriptor.plugin_id,
        "version": descriptor.version,
        "kind": descriptor.kind.value,
        "implementation_digest": descriptor.implementation_digest,
    }


def scorer_input_payload(item: ScorerInput) -> dict[str, object]:
    return {
        "scenario_id": item.scenario_id,
        "initial_state": [list(entry) for entry in item.initial_state],
        "final_state": [list(entry) for entry in item.final_state],
        "harm_key": item.harm_key,
        "harm_threshold": item.harm_threshold,
        "actions": [
            {
                "action_id": action.action_id,
                "tool": action.tool,
                "prohibited": action.prohibited,
                "receipt": None
                if action.receipt is None
                else {
                    "status": action.receipt.status.value,
                    "effects": [
                        {
                            "key": effect.key,
                            "operation": effect.operation.value,
                            "value": effect.value,
                        }
                        for effect in action.receipt.effects
                    ],
                },
            }
            for action in item.actions
        ],
    }


def run_spec_payload(spec: RunSpec) -> dict[str, object]:
    return {
        "schema_version": spec.schema_version,
        "corpus_id": spec.corpus_id,
        "scorer_ids": list(spec.scorer_ids),
        "evidence_conditions": list(spec.evidence_conditions),
        "seed": spec.seed,
        "source_digest": spec.source_digest,
        "frozen_lock_digest": spec.frozen_lock_digest,
    }


def validation_payload(validation: ValidationResult) -> dict[str, object]:
    return {
        "expected": validation.expected,
        "prediction": validation.prediction,
        "correct": validation.correct,
        "false_safe": validation.false_safe,
        "false_success": validation.false_success,
        "unsupported_safe": validation.unsupported_safe,
        "unsupported_success": validation.unsupported_success,
    }


def task_record_payload(record: TaskRecord) -> dict[str, object]:
    return {
        "ordinal": record.ordinal,
        "task_key": record.task_key,
        "task_seed": record.task_seed,
        "case_id": record.case_id,
        "family": record.family,
        "evidence_condition": record.evidence_condition,
        "scorer_id": record.scorer_id,
        "validation": validation_payload(record.validation),
    }


def _as_prediction(value: object, *, field: str) -> Prediction:
    if value is None or type(value) is bool:
        return value
    raise ValueError(f"{field} must be true, false, or null")


def _as_bool(value: object, *, field: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{field} must be a boolean")
    return value


def _as_int(value: object, *, field: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{field} must be an integer")
    return value


def _as_str(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    return value


def task_record_from_payload(payload: object) -> TaskRecord:
    """Parse a canonical task record with strict primitive validation."""

    if not isinstance(payload, dict):
        raise ValueError("task record must be an object")
    raw_validation = payload.get("validation")
    if not isinstance(raw_validation, dict):
        raise ValueError("validation must be an object")
    validation = ValidationResult(
        expected=_as_prediction(
            raw_validation.get("expected"), field="validation.expected"
        ),
        prediction=_as_prediction(
            raw_validation.get("prediction"), field="validation.prediction"
        ),
        correct=_as_bool(
            raw_validation.get("correct"), field="validation.correct"
        ),
        false_safe=_as_bool(
            raw_validation.get("false_safe"), field="validation.false_safe"
        ),
        false_success=_as_bool(
            raw_validation.get("false_success"),
            field="validation.false_success",
        ),
        unsupported_safe=_as_bool(
            raw_validation.get("unsupported_safe"),
            field="validation.unsupported_safe",
        ),
        unsupported_success=_as_bool(
            raw_validation.get("unsupported_success"),
            field="validation.unsupported_success",
        ),
    )
    return TaskRecord(
        ordinal=_as_int(payload.get("ordinal"), field="ordinal"),
        task_key=_as_str(payload.get("task_key"), field="task_key"),
        task_seed=_as_int(payload.get("task_seed"), field="task_seed"),
        case_id=_as_str(payload.get("case_id"), field="case_id"),
        family=_as_str(payload.get("family"), field="family"),
        evidence_condition=_as_str(
            payload.get("evidence_condition"), field="evidence_condition"
        ),
        scorer_id=_as_str(payload.get("scorer_id"), field="scorer_id"),
        validation=validation,
    )
