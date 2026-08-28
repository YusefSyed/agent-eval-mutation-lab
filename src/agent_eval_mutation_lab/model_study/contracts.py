"""Immutable contracts for the isolated model-study boundary."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum


class StudyArm(StrEnum):
    """Prompting protocols evaluated against the same projected input."""

    DIRECT = "direct"
    EVIDENCE_FIRST = "evidence_first"


class TerminalStatus(StrEnum):
    """Mutually exclusive terminal result of one external model trial."""

    COMPLETE = "complete"
    INVALID_RESPONSE = "invalid_response"
    TRANSPORT_ERROR = "transport_error"
    TIMED_OUT = "timed_out"
    INTERRUPTED = "interrupted"


class LicenseEvidence(StrEnum):
    """Where the model-license assertion was observed."""

    LOCAL_MANIFEST = "local_manifest"
    UPSTREAM_MODEL_CARD = "upstream_model_card"


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelIdentity:
    """Content-pinned local model identity; a mutable tag is not sufficient."""

    provider: str
    tag: str
    blob_digest: str
    parameter_count: int
    quantization: str
    license: str
    license_evidence: LicenseEvidence
    license_source: str
    runtime_version: str
    template_digest: str

    def __post_init__(self) -> None:
        _sha256(self.blob_digest, "blob_digest")
        _sha256(self.template_digest, "template_digest")
        if self.parameter_count < 1:
            raise ValueError("parameter_count must be positive")
        for name in (
            "provider",
            "tag",
            "quantization",
            "license",
            "license_source",
            "runtime_version",
        ):
            if not getattr(self, name):
                raise ValueError(f"{name} must be non-empty")


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelConfig:
    """Replay-relevant decoding settings, excluding credentials and prompts."""

    temperature: float
    top_p: float
    presence_penalty: float
    repeat_penalty: float
    context_tokens: int
    max_output_tokens: int
    thinking: bool = False
    streaming: bool = False
    tools_enabled: bool = False
    response_schema_version: int = 1

    def __post_init__(self) -> None:
        if self.temperature < 0:
            raise ValueError("temperature must be non-negative")
        if not 0 < self.top_p <= 1:
            raise ValueError("top_p must be in (0, 1]")
        if self.repeat_penalty <= 0:
            raise ValueError("repeat_penalty must be positive")
        if self.context_tokens < 1 or self.max_output_tokens < 1:
            raise ValueError("token limits must be positive")
        if self.response_schema_version != 1:
            raise ValueError("unsupported response schema version")


@dataclass(frozen=True, slots=True, kw_only=True)
class TrialIdentity:
    """Complete semantic identity for one planned study trial."""

    study_id: str
    trial_id: str
    arm: StudyArm
    model: ModelIdentity
    config: ModelConfig
    input_ref: str
    input_digest: str
    prompt_digest: str
    response_schema_digest: str
    seed: int
    replicate_index: int
    adapter_version: str

    def __post_init__(self) -> None:
        for name in (
            "trial_id",
            "input_digest",
            "prompt_digest",
            "response_schema_digest",
        ):
            _sha256(getattr(self, name), name)
        if not self.study_id or not self.adapter_version:
            raise ValueError("study_id and adapter_version must be non-empty")
        if not self.input_ref:
            raise ValueError("input_ref must be non-empty")
        if self.seed < 0 or self.replicate_index < 0:
            raise ValueError("seed and replicate_index must be non-negative")


@dataclass(frozen=True, slots=True, kw_only=True)
class TrialTerminal:
    """Coordinator-owned terminal metadata, never model-visible input."""

    identity: TrialIdentity
    status: TerminalStatus
    response_digest: str | None = None
    error_type: str | None = None

    def __post_init__(self) -> None:
        has_response = self.status in {
            TerminalStatus.COMPLETE,
            TerminalStatus.INVALID_RESPONSE,
        }
        if has_response != (self.response_digest is not None):
            raise ValueError("response digest must match response-bearing status")
        if self.response_digest is not None:
            _sha256(self.response_digest, "response_digest")
        has_error = self.status in {
            TerminalStatus.TRANSPORT_ERROR,
            TerminalStatus.TIMED_OUT,
        }
        if has_error and not self.error_type:
            raise ValueError("transport and timeout statuses require an error type")


def build_trial_identity(
    *,
    study_id: str,
    arm: StudyArm,
    model: ModelIdentity,
    config: ModelConfig,
    input_ref: str,
    input_digest: str,
    prompt_digest: str,
    response_schema_digest: str,
    seed: int,
    replicate_index: int,
    adapter_version: str,
) -> TrialIdentity:
    """Derive the trial ID from all replay-relevant inputs."""

    payload = {
        "study_id": study_id,
        "arm": arm.value,
        "model": asdict(model),
        "config": asdict(config),
        "input_ref": input_ref,
        "input_digest": input_digest,
        "prompt_digest": prompt_digest,
        "response_schema_digest": response_schema_digest,
        "seed": seed,
        "replicate_index": replicate_index,
        "adapter_version": adapter_version,
    }
    trial_id = hashlib.sha256(_canonical_json(payload)).hexdigest()
    return TrialIdentity(
        study_id=study_id,
        trial_id=trial_id,
        arm=arm,
        model=model,
        config=config,
        input_ref=input_ref,
        input_digest=input_digest,
        prompt_digest=prompt_digest,
        response_schema_digest=response_schema_digest,
        seed=seed,
        replicate_index=replicate_index,
        adapter_version=adapter_version,
    )


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, allow_nan=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode()


def _sha256(value: str, field: str) -> None:
    is_lower_hex = all(character in "0123456789abcdef" for character in value)
    if len(value) != 64 or not is_lower_hex:
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
