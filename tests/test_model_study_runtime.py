from __future__ import annotations

import json
from pathlib import Path

from agent_eval_mutation_lab.model_study.ollama_adapter import (
    OllamaChatReceipt,
    OllamaTransportError,
)
from agent_eval_mutation_lab.model_study.run_plan import load_frozen_study
from agent_eval_mutation_lab.model_study.runtime import run_frozen_study
from agent_eval_mutation_lab.model_study.store import SqliteModelStudyStore

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FROZEN = PROJECT_ROOT / "benchmarks/model-study-v1/frozen"


class _FakeClient:
    def __init__(self, *, fail_first: bool = False) -> None:
        self.fail_first = fail_first
        self.calls = 0

    def send_chat_request(
        self, *, request_bytes: bytes, timeout_seconds: float
    ) -> OllamaChatReceipt:
        del timeout_seconds
        self.calls += 1
        if self.fail_first and self.calls == 1:
            raise OllamaTransportError("retryable fixture")
        request = json.loads(request_bytes)
        model_input = json.loads(request["messages"][1]["content"])
        properties = request["format"]["properties"]
        if "action_evidence" in properties:
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
                "verdict": "insufficient_evidence",
                "probabilities": {
                    "harm_established": 0.1,
                    "no_harm_established": 0.1,
                    "insufficient_evidence": 0.8,
                },
                "conclusion": "fixture",
            }
        else:
            content = {
                "verdict": "insufficient_evidence",
                "probabilities": {
                    "harm_established": 0.1,
                    "no_harm_established": 0.1,
                    "insufficient_evidence": 0.8,
                },
                "conclusion": "fixture",
            }
        response_bytes = json.dumps(
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
            response_bytes=response_bytes,
            response_content=json.dumps(content),
            prompt_tokens=10,
            completion_tokens=5,
            total_duration_ns=100,
        )


def test_runner_resumes_frozen_order_and_preserves_receipts(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "agent_eval_mutation_lab.model_study.runtime._verify_local_models",
        lambda plan, client: None,
    )
    client = _FakeClient()
    first = run_frozen_study(
        project_root=PROJECT_ROOT,
        frozen_dir=FROZEN,
        output_dir=tmp_path,
        client=client,  # type: ignore[arg-type]
        timeout_seconds=10,
        max_new_trials=4,
    )
    assert first["executed_this_run"] == 4
    assert first["complete"] == 4
    assert first["pending"] == 620

    second = run_frozen_study(
        project_root=PROJECT_ROOT,
        frozen_dir=FROZEN,
        output_dir=tmp_path,
        client=client,  # type: ignore[arg-type]
        timeout_seconds=10,
        max_new_trials=2,
    )
    assert second["resumed_before_run"] == 4
    assert second["complete"] == 6
    assert second["pending"] == 618
    assert len(list((tmp_path / "objects/sha256").rglob("*.json"))) >= 6


def test_runner_retries_one_transport_failure_before_finalizing(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "agent_eval_mutation_lab.model_study.runtime._verify_local_models",
        lambda plan, client: None,
    )
    client = _FakeClient(fail_first=True)
    report = run_frozen_study(
        project_root=PROJECT_ROOT,
        frozen_dir=FROZEN,
        output_dir=tmp_path,
        client=client,  # type: ignore[arg-type]
        timeout_seconds=10,
        max_new_trials=1,
    )
    assert report["complete"] == 1
    assert report["attempts"] == 2
    plan = load_frozen_study(project_root=PROJECT_ROOT, frozen_dir=FROZEN)
    store = SqliteModelStudyStore(tmp_path / "run.sqlite3")
    attempts = store.attempts_for(
        plan_digest=plan.protocol_digest,
        trial_id=plan.trials[0].identity.trial_id,
    )
    assert [attempt.status.value for attempt in attempts] == [
        "transport_error",
        "complete",
    ]
