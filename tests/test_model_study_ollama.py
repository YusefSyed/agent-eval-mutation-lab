from __future__ import annotations

import hashlib
import json

import pytest

from agent_eval_mutation_lab.model_study.contracts import LicenseEvidence, ModelConfig
from agent_eval_mutation_lab.model_study.ollama_adapter import (
    OllamaClient,
    build_chat_request,
    model_identity_from_show,
)


class _Transport:
    def __init__(self, responses: list[bytes]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, bytes | None, float]] = []

    def request(
        self,
        *,
        method: str,
        url: str,
        body: bytes | None,
        timeout_seconds: float,
    ) -> bytes:
        self.calls.append((method, url, body, timeout_seconds))
        return self.responses.pop(0)


def _config() -> ModelConfig:
    return ModelConfig(
        temperature=0.2,
        top_p=0.95,
        presence_penalty=0.0,
        repeat_penalty=1.0,
        context_tokens=8192,
        max_output_tokens=512,
    )


def test_chat_request_is_canonical_and_protocol_bounded() -> None:
    first = build_chat_request(
        tag="model:tag",
        system_prompt="Classify visible evidence.",
        model_input={"schema_version": 1, "scenario_ref": "opaque"},
        response_schema={"type": "object"},
        config=_config(),
        seed=101,
    )
    second = build_chat_request(
        tag="model:tag",
        system_prompt="Classify visible evidence.",
        model_input={"scenario_ref": "opaque", "schema_version": 1},
        response_schema={"type": "object"},
        config=_config(),
        seed=101,
    )
    assert first == second
    payload = json.loads(first)
    assert payload["stream"] is False
    assert payload["think"] is False
    assert "tools" not in payload
    assert payload["options"]["seed"] == 101


def test_model_identity_requires_blob_parameters_quantization_and_license() -> None:
    template = "{{ .Prompt }}"
    identity = model_identity_from_show(
        tag="model:tag",
        runtime_version="0.33.1",
        show_payload={
            "modelfile": f"FROM /models/blobs/sha256-{'a' * 64}\n",
            "template": template,
            "license": "Apache License\nVersion 2.0, January 2004",
            "details": {"quantization_level": "Q4_K_M"},
            "model_info": {"general.parameter_count": 9_653_104_368},
        },
    )
    assert identity.blob_digest == "a" * 64
    assert identity.parameter_count == 9_653_104_368
    assert identity.license_evidence is LicenseEvidence.LOCAL_MANIFEST
    assert identity.template_digest == hashlib.sha256(template.encode()).hexdigest()
    with pytest.raises(ValueError, match="pinned SHA-256"):
        model_identity_from_show(
            tag="model:tag",
            runtime_version="0.33.1",
            show_payload={
                "modelfile": "FROM model:latest\n",
                "template": template,
                "license": "Apache License\nVersion 2.0",
                "details": {"quantization_level": "Q4_K_M"},
                "model_info": {"general.parameter_count": 1},
            },
        )


def test_model_identity_can_record_upstream_license_when_manifest_omits_it() -> None:
    identity = model_identity_from_show(
        tag="model:tag",
        runtime_version="0.33.1",
        declared_license="Apache-2.0",
        license_source="https://example.test/upstream-model-card",
        show_payload={
            "modelfile": f"FROM /models/blobs/sha256-{'a' * 64}\n",
            "template": "{{ .Prompt }}",
            "license": None,
            "details": {"quantization_level": "Q4_K_M"},
            "model_info": {"general.parameter_count": 24_011_361_280},
        },
    )
    assert identity.license == "Apache-2.0"
    assert identity.license_evidence is LicenseEvidence.UPSTREAM_MODEL_CARD
    assert identity.license_source.endswith("upstream-model-card")
    with pytest.raises(ValueError, match="declared license and source"):
        model_identity_from_show(
            tag="model:tag",
            runtime_version="0.33.1",
            show_payload={
                "modelfile": f"FROM /models/blobs/sha256-{'a' * 64}\n",
                "template": "{{ .Prompt }}",
                "license": None,
                "details": {"quantization_level": "Q4_K_M"},
                "model_info": {"general.parameter_count": 24_011_361_280},
            },
        )


def test_client_preserves_exact_request_and_response_receipts() -> None:
    raw_response = json.dumps(
        {
            "message": {"content": '{"verdict":"insufficient_evidence"}'},
            "prompt_eval_count": 123,
            "eval_count": 18,
            "total_duration": 456,
        },
        separators=(",", ":"),
    ).encode()
    transport = _Transport([raw_response])
    client = OllamaClient(transport=transport)
    receipt = client.chat(
        tag="model:tag",
        system_prompt="Classify.",
        model_input={"scenario_ref": "opaque"},
        response_schema={"type": "object"},
        config=_config(),
        seed=101,
        timeout_seconds=30.0,
    )
    assert receipt.response_bytes == raw_response
    assert receipt.request_bytes == transport.calls[0][2]
    assert receipt.prompt_tokens == 123
    assert receipt.completion_tokens == 18


def test_client_version_and_show_are_strict_and_use_expected_endpoints() -> None:
    show = {"modelfile": "FROM pinned"}
    transport = _Transport(
        [json.dumps({"version": "0.33.1"}).encode(), json.dumps(show).encode()]
    )
    client = OllamaClient(base_url="http://localhost:11434/", transport=transport)
    assert client.version() == "0.33.1"
    assert client.show("model:tag") == show
    assert transport.calls[0][1].endswith("/api/version")
    assert transport.calls[1][1].endswith("/api/show")
    assert json.loads(transport.calls[1][2] or b"{}") == {"model": "model:tag"}


def test_chat_request_rejects_tool_use_and_negative_seed() -> None:
    tool_config = ModelConfig(
        temperature=0.2,
        top_p=0.95,
        presence_penalty=0,
        repeat_penalty=1,
        context_tokens=8192,
        max_output_tokens=512,
        tools_enabled=True,
    )
    with pytest.raises(ValueError, match="forbids tool use"):
        build_chat_request(
            tag="model:tag",
            system_prompt="prompt",
            model_input={},
            response_schema={},
            config=tool_config,
            seed=1,
        )
    with pytest.raises(ValueError, match="non-negative"):
        build_chat_request(
            tag="model:tag",
            system_prompt="prompt",
            model_input={},
            response_schema={},
            config=_config(),
            seed=-1,
        )
