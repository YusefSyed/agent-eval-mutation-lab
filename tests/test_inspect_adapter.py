import json
from pathlib import Path

import pytest

from agent_eval_mutation_lab.inspect_adapter import (
    InspectExecutionStatus,
    adapt_inspect_log,
    render_markdown,
    write_adapter_reports,
)

FIXTURES = Path(__file__).parent / "fixtures/inspect-0.3.260"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_approved_and_rejected_calls_are_correlated_fail_closed() -> None:
    approved = adapt_inspect_log(_fixture("approved.json"))
    rejected = adapt_inspect_log(_fixture("rejected.json"))

    approved_call = approved["calls"][0]
    rejected_call = rejected["calls"][0]
    assert approved_call["execution_status"] == InspectExecutionStatus.SUCCEEDED
    assert approved_call["result_present"] is True
    assert rejected_call["execution_status"] == InspectExecutionStatus.DENIED
    assert rejected_call["error_type"] == "approval"
    assert rejected_call["result_present"] is False

    assert approved["attack_success_ready"] is False
    assert approved["evidence_coverage"]["domain_side_effect_receipt"] is False
    assert approved["evidence_coverage"]["final_environment_state"] is False


def test_timeout_is_unknown_not_safe() -> None:
    report = adapt_inspect_log(_fixture("timeout.json"))
    call = report["calls"][0]
    assert call["execution_status"] == InspectExecutionStatus.UNKNOWN
    assert "uncertain" in call["notes"][0]


def test_contradictory_rejection_is_unknown() -> None:
    payload = _fixture("rejected.json")
    payload["samples"][0]["events"][1].pop("error")
    report = adapt_inspect_log(payload)
    assert report["calls"][0]["execution_status"] == InspectExecutionStatus.UNKNOWN


def test_adapter_reports_are_deterministic(tmp_path: Path) -> None:
    report = adapt_inspect_log(_fixture("approved.json"))
    json_path, markdown_path = write_adapter_reports(report, tmp_path)
    assert json.loads(json_path.read_text(encoding="utf-8")) == report
    assert markdown_path.read_text(encoding="utf-8") == render_markdown(report)


def test_malformed_log_is_rejected() -> None:
    with pytest.raises(ValueError, match="samples list"):
        adapt_inspect_log({})

