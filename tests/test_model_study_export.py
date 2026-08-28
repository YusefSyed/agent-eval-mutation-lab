from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_eval_mutation_lab.model_study.export import export_completed_study
from agent_eval_mutation_lab.model_study.ollama_adapter import OllamaChatReceipt
from agent_eval_mutation_lab.model_study.runtime import run_frozen_study

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FROZEN = PROJECT_ROOT / "benchmarks/model-study-v1/frozen"


class _ReplayableClient:
    def send_chat_request(
        self, *, request_bytes: bytes, timeout_seconds: float
    ) -> OllamaChatReceipt:
        del timeout_seconds
        request = json.loads(request_bytes)
        model_input = json.loads(request["messages"][1]["content"])
        evidence_first = "action_evidence" in request["format"]["properties"]
        common = {
            "verdict": "insufficient_evidence",
            "probabilities": {
                "harm_established": 0.1,
                "no_harm_established": 0.1,
                "insufficient_evidence": 0.8,
            },
            "conclusion": "fixture",
        }
        if evidence_first:
            content = {
                "action_evidence": [
                    {
                        "action_ref": action["action_ref"],
                        "execution": "unresolved",
                        "harm": "unresolved",
                        "citations": [f"/actions/{index}/action_ref"],
                    }
                    for index, action in enumerate(model_input["actions"])
                ],
                "final_state_attribution": "unresolved",
                "final_state_citations": ["/initial_state", "/final_state"],
                **common,
            }
        else:
            content = common
        response = json.dumps(
            {
                "message": {"content": json.dumps(content)},
                "prompt_eval_count": 10,
                "eval_count": 5,
                "total_duration": 100,
            },
            separators=(",", ":"),
        ).encode()
        return OllamaChatReceipt(
            request_bytes=request_bytes,
            response_bytes=response,
            response_content=json.dumps(content),
            prompt_tokens=10,
            completion_tokens=5,
            total_duration_ns=100,
        )


def _disable_preflight(monkeypatch) -> None:
    monkeypatch.setattr(
        "agent_eval_mutation_lab.model_study.runtime._verify_local_models",
        lambda plan, client: None,
    )


def test_complete_export_replays_receipts_and_is_byte_stable(
    tmp_path: Path, monkeypatch
) -> None:
    _disable_preflight(monkeypatch)
    report = run_frozen_study(
        project_root=PROJECT_ROOT,
        frozen_dir=FROZEN,
        output_dir=tmp_path,
        client=_ReplayableClient(),  # type: ignore[arg-type]
        timeout_seconds=10,
    )
    assert report["complete"] == 624
    analysis, _ = export_completed_study(
        project_root=PROJECT_ROOT,
        frozen_dir=FROZEN,
        output_dir=tmp_path,
    )
    first_metrics = (tmp_path / "metrics.json").read_bytes()
    first_trials = (tmp_path / "trials.jsonl").read_bytes()
    assert analysis.gates.passed is False
    assert len(first_trials.splitlines()) == 624
    assert (tmp_path / "SHA256SUMS").is_file()

    export_completed_study(
        project_root=PROJECT_ROOT,
        frozen_dir=FROZEN,
        output_dir=tmp_path,
    )
    assert (tmp_path / "metrics.json").read_bytes() == first_metrics
    assert (tmp_path / "trials.jsonl").read_bytes() == first_trials


def test_partial_run_cannot_export_headline_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    _disable_preflight(monkeypatch)
    run_frozen_study(
        project_root=PROJECT_ROOT,
        frozen_dir=FROZEN,
        output_dir=tmp_path,
        client=_ReplayableClient(),  # type: ignore[arg-type]
        timeout_seconds=10,
        max_new_trials=2,
    )
    with pytest.raises(RuntimeError, match="incomplete"):
        export_completed_study(
            project_root=PROJECT_ROOT,
            frozen_dir=FROZEN,
            output_dir=tmp_path,
        )
