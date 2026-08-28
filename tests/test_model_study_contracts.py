from __future__ import annotations

import pytest

from agent_eval_mutation_lab.model_study.contracts import (
    LicenseEvidence,
    ModelConfig,
    ModelIdentity,
    StudyArm,
    TerminalStatus,
    TrialTerminal,
    build_trial_identity,
)


def _identity() -> ModelIdentity:
    return ModelIdentity(
        provider="ollama",
        tag="model:tag",
        blob_digest="a" * 64,
        parameter_count=1,
        quantization="Q4_K_M",
        license="Apache-2.0",
        license_evidence=LicenseEvidence.LOCAL_MANIFEST,
        license_source="ollama:/api/show",
        runtime_version="0.33.1",
        template_digest="b" * 64,
    )


def _config(**changes: object) -> ModelConfig:
    values = {
        "temperature": 0.2,
        "top_p": 0.95,
        "presence_penalty": 0.0,
        "repeat_penalty": 1.0,
        "context_tokens": 8192,
        "max_output_tokens": 512,
        **changes,
    }
    return ModelConfig(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "changes",
    [
        {"temperature": -1.0},
        {"top_p": 0.0},
        {"repeat_penalty": 0.0},
        {"context_tokens": 0},
        {"max_output_tokens": 0},
        {"response_schema_version": 2},
    ],
)
def test_model_config_rejects_invalid_protocol_values(changes: dict) -> None:
    with pytest.raises(ValueError):
        _config(**changes)


def test_model_identity_rejects_unpinned_or_empty_values() -> None:
    with pytest.raises(ValueError, match="blob_digest"):
        ModelIdentity(
            provider="ollama",
            tag="model:tag",
            blob_digest="not-a-digest",
            parameter_count=1,
            quantization="Q4_K_M",
            license="Apache-2.0",
            license_evidence=LicenseEvidence.LOCAL_MANIFEST,
            license_source="ollama:/api/show",
            runtime_version="0.33.1",
            template_digest="b" * 64,
        )
    with pytest.raises(ValueError, match="parameter_count"):
        ModelIdentity(
            provider="ollama",
            tag="model:tag",
            blob_digest="a" * 64,
            parameter_count=0,
            quantization="Q4_K_M",
            license="Apache-2.0",
            license_evidence=LicenseEvidence.LOCAL_MANIFEST,
            license_source="ollama:/api/show",
            runtime_version="0.33.1",
            template_digest="b" * 64,
        )


def test_terminal_status_requires_matching_receipt_and_error_metadata() -> None:
    identity = build_trial_identity(
        study_id="study",
        arm=StudyArm.DIRECT,
        model=_identity(),
        config=_config(),
        input_ref="input-0000",
        input_digest="c" * 64,
        prompt_digest="d" * 64,
        response_schema_digest="e" * 64,
        seed=101,
        replicate_index=0,
        adapter_version="1",
    )
    complete = TrialTerminal(
        identity=identity,
        status=TerminalStatus.COMPLETE,
        response_digest="f" * 64,
    )
    assert complete.response_digest == "f" * 64
    assert (
        TrialTerminal(identity=identity, status=TerminalStatus.INTERRUPTED).status
        is TerminalStatus.INTERRUPTED
    )
    with pytest.raises(ValueError, match="response digest"):
        TrialTerminal(identity=identity, status=TerminalStatus.COMPLETE)
    with pytest.raises(ValueError, match="require an error type"):
        TrialTerminal(identity=identity, status=TerminalStatus.TRANSPORT_ERROR)
