"""Load and expand the checksum-verified frozen model-study protocol."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from agent_eval_mutation_lab.model_study.contracts import (
    LicenseEvidence,
    ModelConfig,
    ModelIdentity,
    StudyArm,
    TrialIdentity,
    build_trial_identity,
)
from agent_eval_mutation_lab.model_study.projection import JSONPayload


@dataclass(frozen=True, slots=True, kw_only=True)
class FrozenTrial:
    ordinal: int
    input_ref: str
    payload: JSONPayload
    prompt: str
    response_schema: dict[str, object]
    identity: TrialIdentity


@dataclass(frozen=True, slots=True, kw_only=True)
class FrozenStudyPlan:
    study_id: str
    protocol_digest: str
    config: ModelConfig
    models: tuple[ModelIdentity, ...]
    trials: tuple[FrozenTrial, ...]


def load_frozen_study(
    *,
    project_root: Path,
    frozen_dir: Path,
) -> FrozenStudyPlan:
    """Verify every frozen byte and expand the deterministic 624-trial order."""

    project_root = project_root.resolve()
    frozen_dir = frozen_dir.resolve()
    _verify_sums(frozen_dir)
    plan_payload = _read_object(frozen_dir / "plan.json")
    study_id = _string(plan_payload, "study_id")
    if plan_payload.get("status") != "frozen_before_benchmark_inference":
        raise ValueError("study plan is not frozen before benchmark inference")
    adapter_version = _string(plan_payload, "adapter_version")
    config = _config(_object(plan_payload.get("config"), "config"))
    seeds = _int_array(plan_payload.get("seeds"), "seeds")
    arms = tuple(
        StudyArm(value)
        for value in _string_array(plan_payload.get("arms"), "arms")
    )
    if arms != tuple(StudyArm):
        raise ValueError("frozen study arms are incomplete or out of order")

    model_manifest = _read_object(frozen_dir / "model-manifest.json")
    raw_models = model_manifest.get("models")
    if not isinstance(raw_models, list):
        raise ValueError("model manifest models must be an array")
    models = tuple(_model_identity(_object(item, "model")) for item in raw_models)
    if len(models) != 2:
        raise ValueError("frozen model manifest must contain exactly two models")

    input_records = _read_jsonl(frozen_dir / "inputs.jsonl")
    if len(input_records) != 52:
        raise ValueError("frozen model study must contain 52 inputs")
    inputs = tuple(_input_record(item) for item in input_records)

    prompt_manifest = _read_object(frozen_dir / "prompt-manifest.json")
    prompt_entries = _object(prompt_manifest.get("prompts"), "prompts")
    prompts: dict[StudyArm, tuple[str, str]] = {}
    for arm in arms:
        entry = _object(prompt_entries.get(arm.value), f"prompt {arm.value}")
        relative = _safe_relative(_string(entry, "path"))
        content = (project_root / relative).read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        digest_matches = digest == _string(entry, "sha256")
        size_matches = len(content) == _integer(entry, "size")
        if not digest_matches or not size_matches:
            raise ValueError(f"prompt bytes do not match frozen {arm.value} identity")
        prompts[arm] = (content.decode("utf-8"), digest)

    schema_manifest = _read_object(frozen_dir / "response-schemas.json")
    schema_entries = _object(schema_manifest.get("schemas"), "schemas")
    schemas: dict[StudyArm, tuple[dict[str, object], str]] = {}
    for arm in arms:
        schema = _object(schema_entries.get(arm.value), f"schema {arm.value}")
        schemas[arm] = (schema, hashlib.sha256(_canonical_json(schema)).hexdigest())

    trials: list[FrozenTrial] = []
    ordinal = 0
    for model in models:
        for replicate_index, seed in enumerate(seeds):
            indices = list(range(len(inputs)))
            random.Random(_order_seed(study_id, model, seed)).shuffle(indices)
            for index in indices:
                input_ref, input_digest, payload = inputs[index]
                for arm in arms:
                    prompt, prompt_digest = prompts[arm]
                    schema, schema_digest = schemas[arm]
                    identity = build_trial_identity(
                        study_id=study_id,
                        arm=arm,
                        model=model,
                        config=config,
                        input_ref=input_ref,
                        input_digest=input_digest,
                        prompt_digest=prompt_digest,
                        response_schema_digest=schema_digest,
                        seed=seed,
                        replicate_index=replicate_index,
                        adapter_version=adapter_version,
                    )
                    trials.append(
                        FrozenTrial(
                            ordinal=ordinal,
                            input_ref=input_ref,
                            payload=payload,
                            prompt=prompt,
                            response_schema=schema,
                            identity=identity,
                        )
                    )
                    ordinal += 1
    expected_trials = _integer(plan_payload, "planned_terminal_trials")
    if len(trials) != expected_trials or expected_trials != 624:
        raise ValueError("expanded trial count does not match frozen plan")
    return FrozenStudyPlan(
        study_id=study_id,
        protocol_digest=_sha256(frozen_dir / "MANIFEST.json"),
        config=config,
        models=models,
        trials=tuple(trials),
    )


def _verify_sums(root: Path) -> None:
    lines = (root / "SHA256SUMS").read_text(encoding="ascii").splitlines()
    if not lines:
        raise ValueError("frozen SHA256SUMS is empty")
    seen: set[str] = set()
    for line in lines:
        parts = line.split("  ", maxsplit=1)
        if len(parts) != 2:
            raise ValueError("invalid SHA256SUMS line")
        digest, filename = parts
        relative = _safe_relative(filename)
        if filename in seen:
            raise ValueError("duplicate SHA256SUMS filename")
        seen.add(filename)
        if _sha256(root / relative) != digest:
            raise ValueError(f"frozen checksum mismatch: {filename}")


def _input_record(value: dict[str, object]) -> tuple[str, str, JSONPayload]:
    input_ref = _string(value, "input_ref")
    digest = _string(value, "payload_digest")
    payload = _json_payload(value.get("payload"), "payload")
    if hashlib.sha256(_canonical_json(payload)).hexdigest() != digest:
        raise ValueError(f"input payload digest mismatch: {input_ref}")
    return input_ref, digest, payload


def _model_identity(payload: dict[str, object]) -> ModelIdentity:
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


def _config(payload: dict[str, object]) -> ModelConfig:
    return ModelConfig(
        temperature=_number(payload, "temperature"),
        top_p=_number(payload, "top_p"),
        presence_penalty=_number(payload, "presence_penalty"),
        repeat_penalty=_number(payload, "repeat_penalty"),
        context_tokens=_integer(payload, "context_tokens"),
        max_output_tokens=_integer(payload, "max_output_tokens"),
        thinking=_boolean(payload, "thinking"),
        streaming=_boolean(payload, "streaming"),
        tools_enabled=_boolean(payload, "tools_enabled"),
        response_schema_version=_integer(payload, "response_schema_version"),
    )


def _order_seed(study_id: str, model: ModelIdentity, seed: int) -> int:
    material = f"{study_id}:{model.blob_digest}:{seed}".encode()
    return int(hashlib.sha256(material).hexdigest()[:16], 16)


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        _object(json.loads(line), path.name)
        for line in path.read_text().splitlines()
    ]


def _read_object(path: Path) -> dict[str, object]:
    return _object(json.loads(path.read_text(encoding="utf-8")), path.name)


def _json_payload(value: object, context: str) -> JSONPayload:
    payload = _object(value, context)
    json.dumps(payload, allow_nan=False)
    return payload  # type: ignore[return-value]


def _object(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{context} must be an object with string keys")
    return value


def _safe_relative(value: str) -> Path:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("protocol path must be safe and repository-relative")
    return Path(*path.parts)


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


def _number(payload: dict[str, object], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")
    return float(value)


def _boolean(payload: dict[str, object], key: str) -> bool:
    value = payload.get(key)
    if type(value) is not bool:
        raise ValueError(f"{key} must be a boolean")
    return value


def _string_array(value: object, context: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{context} must be an array of strings")
    return tuple(value)


def _int_array(value: object, context: str) -> tuple[int, ...]:
    if not isinstance(value, list) or not all(type(item) is int for item in value):
        raise ValueError(f"{context} must be an array of integers")
    return tuple(value)


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, allow_nan=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
