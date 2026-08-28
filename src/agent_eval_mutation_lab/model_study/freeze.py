"""Freeze the preregistered model-study inputs, prompts, schemas, and identities."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from agent_eval_mutation_lab.model_study.contracts import (
    LicenseEvidence,
    ModelConfig,
    ModelIdentity,
    StudyArm,
)
from agent_eval_mutation_lab.model_study.planning import (
    build_model_study_inputs,
    model_record_payload,
    oracle_record_payload,
)
from agent_eval_mutation_lab.model_study.schemas import (
    DIRECT_RESPONSE_SCHEMA,
    EVIDENCE_FIRST_RESPONSE_SCHEMA,
)

STUDY_ID = "execution-evidence-ledger-v1"
ADAPTER_VERSION = "2"
SEEDS = (101, 202, 303)
FROZEN_CONFIG = ModelConfig(
    temperature=0.2,
    top_p=0.95,
    presence_penalty=0.0,
    repeat_penalty=1.0,
    context_tokens=8192,
    max_output_tokens=512,
)

FROZEN_FILES = (
    "inputs.jsonl",
    "oracle-ledger.jsonl",
    "prompt-manifest.json",
    "response-schemas.json",
    "model-manifest.json",
    "plan.json",
)


def load_model_identity(path: Path) -> ModelIdentity:
    payload = _object(json.loads(path.read_text(encoding="utf-8")), "identity")
    return ModelIdentity(
        provider=_string(payload, "provider"),
        tag=_string(payload, "tag"),
        blob_digest=_string(payload, "blob_digest"),
        parameter_count=_integer(payload, "parameter_count"),
        quantization=_string(payload, "quantization"),
        license=_string(payload, "license"),
        license_evidence=LicenseEvidence(_string(payload, "license_evidence")),
        license_source=_string(payload, "license_source"),
        runtime_version=_string(payload, "runtime_version"),
        template_digest=_string(payload, "template_digest"),
    )


def freeze_protocol(
    *,
    project_root: Path,
    output_dir: Path,
    models: tuple[ModelIdentity, ...],
) -> dict[str, Any]:
    """Write a byte-stable protocol snapshot before any benchmark inference."""

    if len(models) != 2 or len({model.tag for model in models}) != 2:
        raise ValueError("frozen study requires exactly two unique model identities")
    output_dir.mkdir(parents=True, exist_ok=True)
    model_inputs, oracle_ledger = build_model_study_inputs(project_root)
    _write_jsonl(
        output_dir / "inputs.jsonl",
        [model_record_payload(record) for record in model_inputs],
    )
    _write_jsonl(
        output_dir / "oracle-ledger.jsonl",
        [oracle_record_payload(record) for record in oracle_ledger],
    )

    prompt_root = project_root / "benchmarks/model-study-v1"
    prompt_manifest: dict[str, object] = {"schema_version": 1, "prompts": {}}
    prompts = prompt_manifest["prompts"]
    assert isinstance(prompts, dict)
    for arm, filename in (
        (StudyArm.DIRECT, "direct-v1.txt"),
        (StudyArm.EVIDENCE_FIRST, "evidence-first-v1.txt"),
    ):
        content = (prompt_root / filename).read_bytes()
        prompts[arm.value] = {
            "path": f"benchmarks/model-study-v1/{filename}",
            "sha256": hashlib.sha256(content).hexdigest(),
            "size": len(content),
        }
    _write_json(output_dir / "prompt-manifest.json", prompt_manifest)

    schemas = {
        "schema_version": 1,
        "schemas": {
            StudyArm.DIRECT.value: DIRECT_RESPONSE_SCHEMA,
            StudyArm.EVIDENCE_FIRST.value: EVIDENCE_FIRST_RESPONSE_SCHEMA,
        },
    }
    _write_json(output_dir / "response-schemas.json", schemas)
    model_manifest = {
        "schema_version": 1,
        "models": [
            asdict(model) for model in sorted(models, key=lambda item: item.tag)
        ],
    }
    _write_json(output_dir / "model-manifest.json", model_manifest)

    planned_trials = len(model_inputs) * len(models) * len(StudyArm) * len(SEEDS)
    plan = {
        "schema_version": 1,
        "study_id": STUDY_ID,
        "adapter_version": ADAPTER_VERSION,
        "status": "frozen_before_benchmark_inference",
        "research_question": (
            "Does a cited evidence ledger reduce unsupported directional claims "
            "relative to direct classification on the fixed 52-input corpus?"
        ),
        "scope": (
            "finite public hand-authored corpus; model-, prompt-, and version-specific"
        ),
        "input_count": len(model_inputs),
        "model_count": len(models),
        "arms": [arm.value for arm in StudyArm],
        "seeds": list(SEEDS),
        "planned_terminal_trials": planned_trials,
        "config": asdict(FROZEN_CONFIG),
        "retry_policy": (
            "one retry only after transport failure before a complete response"
        ),
        "positive_claim_gate": {
            "fewer_directional_overclaims_for_each_model": True,
            "no_increase_in_safety_directed_overclaims": True,
            "maximum_coverage_drop_per_model": 0.10,
            "not_reversed_by_leave_one_family_out": True,
        },
    }
    _write_json(output_dir / "plan.json", plan)
    manifest = {
        "schema_version": 1,
        "study_id": STUDY_ID,
        "files": {
            filename: _file_identity(output_dir / filename)
            for filename in FROZEN_FILES
        },
    }
    _write_json(output_dir / "MANIFEST.json", manifest)
    sums = [
        f"{_sha256(output_dir / filename)}  {filename}"
        for filename in (*FROZEN_FILES, "MANIFEST.json")
    ]
    (output_dir / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="ascii")
    return plan


def _write_json(path: Path, value: object) -> None:
    path.write_bytes(_canonical_json(value, pretty=True))


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_bytes(b"".join(_canonical_json(record) for record in records))


def _canonical_json(value: object, *, pretty: bool = False) -> bytes:
    options: dict[str, object] = {
        "allow_nan": False,
        "ensure_ascii": False,
        "sort_keys": True,
    }
    if pretty:
        options["indent"] = 2
    else:
        options["separators"] = (",", ":")
    return (json.dumps(value, **options) + "\n").encode()  # type: ignore[arg-type]


def _file_identity(path: Path) -> dict[str, object]:
    return {"sha256": _sha256(path), "size": path.stat().st_size}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _object(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{context} must be an object with string keys")
    return value


def _string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _integer(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if type(value) is not int:
        raise ValueError(f"{key} must be an integer")
    return value
