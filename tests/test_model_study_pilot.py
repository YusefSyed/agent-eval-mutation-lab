from __future__ import annotations

import json
from pathlib import Path

from agent_eval_mutation_lab.model_study.contracts import (
    LicenseEvidence,
    ModelConfig,
    ModelIdentity,
)
from agent_eval_mutation_lab.model_study.ollama_adapter import (
    OllamaClient,
    OllamaTransportError,
)
from agent_eval_mutation_lab.model_study.pilot import run_format_pilot


class _Transport:
    def __init__(self, responses: list[bytes]) -> None:
        self.responses = responses

    def request(
        self,
        *,
        method: str,
        url: str,
        body: bytes | None,
        timeout_seconds: float,
    ) -> bytes:
        del method, url, body, timeout_seconds
        return self.responses.pop(0)


class _ErrorTransport:
    def request(
        self,
        *,
        method: str,
        url: str,
        body: bytes | None,
        timeout_seconds: float,
    ) -> bytes:
        del method, url, body, timeout_seconds
        raise OllamaTransportError("fixture transport failure")


def _chat_response(content: dict) -> bytes:
    return json.dumps(
        {
            "message": {"content": json.dumps(content)},
            "prompt_eval_count": 50,
            "eval_count": 20,
            "total_duration": 100,
        },
        separators=(",", ":"),
    ).encode()


def test_format_pilot_preserves_receipts_and_validates_both_arms(
    tmp_path: Path,
) -> None:
    direct = {
        "verdict": "harm_established",
        "probabilities": {
            "harm_established": 0.9,
            "no_harm_established": 0.05,
            "insufficient_evidence": 0.05,
        },
        "conclusion": "visible effect reaches the threshold",
    }
    evidence = {
        "action_evidence": [
            {
                "action_ref": "format-action-0001",
                "execution": "executed",
                "harm": "caused_harm",
                "citations": ["/actions/0/receipt/effects/0"],
            }
        ],
        "final_state_attribution": "attributable",
        "final_state_citations": ["/initial_state", "/final_state"],
        "verdict": "harm_established",
        "probabilities": {
            "harm_established": 0.9,
            "no_harm_established": 0.05,
            "insufficient_evidence": 0.05,
        },
        "conclusion": "the executed effect creates new final harm",
    }
    client = OllamaClient(
        transport=_Transport([_chat_response(direct), _chat_response(evidence)])
    )
    identity = ModelIdentity(
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
    config = ModelConfig(
        temperature=0.2,
        top_p=0.95,
        presence_penalty=0.0,
        repeat_penalty=1.0,
        context_tokens=8192,
        max_output_tokens=512,
    )
    report = run_format_pilot(
        project_root=Path(__file__).resolve().parents[1],
        output_dir=tmp_path,
        client=client,
        identity=identity,
        config=config,
        seed=101,
        timeout_seconds=30,
    )
    assert report["passed"] is True
    assert (tmp_path / "direct/request.json").is_file()
    assert (tmp_path / "evidence_first/response.json").is_file()
    round_trip = json.loads(
        (tmp_path / "pilot-summary.json").read_text(encoding="utf-8")
    )
    assert round_trip == report
    assert report["scope"] == "format-only non-benchmark pilot; no benchmark claim"


def test_format_pilot_records_transport_failures_without_receipts(
    tmp_path: Path,
) -> None:
    identity = ModelIdentity(
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
    config = ModelConfig(
        temperature=0.2,
        top_p=0.95,
        presence_penalty=0,
        repeat_penalty=1,
        context_tokens=8192,
        max_output_tokens=512,
    )
    report = run_format_pilot(
        project_root=Path(__file__).resolve().parents[1],
        output_dir=tmp_path,
        client=OllamaClient(transport=_ErrorTransport()),
        identity=identity,
        config=config,
        seed=101,
        timeout_seconds=1,
    )
    assert report["passed"] is False
    assert [item["status"] for item in report["results"]] == [
        "transport_error",
        "transport_error",
    ]
