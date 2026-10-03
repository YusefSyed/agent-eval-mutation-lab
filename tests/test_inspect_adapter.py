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


@pytest.mark.parametrize(
    "completed", ["", "not-a-time", "2026-13-01T00:00:00Z", 1, True, {}]
)
def test_synthetic_malformed_completion_is_rejected(completed: object) -> None:
    payload = _fixture("approved.json")
    payload["samples"][0]["events"][1]["completed"] = completed
    with pytest.raises(ValueError, match="tool.completed"):
        adapt_inspect_log(payload)


@pytest.mark.parametrize("failed", ["true", "false", 0, 1, [], {}])
def test_synthetic_malformed_failure_marker_is_rejected(failed: object) -> None:
    payload = _fixture("approved.json")
    payload["samples"][0]["events"][1]["failed"] = failed
    with pytest.raises(ValueError, match="tool.failed"):
        adapt_inspect_log(payload)


@pytest.mark.parametrize("decision", ["not-a-decision", "", True, None])
def test_synthetic_unsupported_approval_decision_is_rejected(decision: object) -> None:
    payload = _fixture("approved.json")
    payload["samples"][0]["events"][0]["decision"] = decision
    with pytest.raises(ValueError, match="approval.decision"):
        adapt_inspect_log(payload)


def test_synthetic_duplicate_tool_id_is_rejected() -> None:
    payload = _fixture("approved.json")
    events = payload["samples"][0]["events"]
    duplicate = dict(events[1])
    duplicate["arguments"] = {"value": 2}
    events.append(duplicate)
    with pytest.raises(ValueError, match="duplicate tool.id"):
        adapt_inspect_log(payload)


@pytest.mark.parametrize(
    "field,value", [("function", "other_tool"), ("arguments", {"value": 2})]
)
def test_synthetic_mismatched_approval_payload_is_rejected(
    field: str, value: object
) -> None:
    payload = _fixture("approved.json")
    payload["samples"][0]["events"][0]["call"][field] = value
    with pytest.raises(ValueError, match="approval.call does not match"):
        adapt_inspect_log(payload)


@pytest.mark.parametrize(
    "modified",
    [
        None,
        {"id": "call-1", "arguments": {"value": 2}},
        {"id": "call-1", "function": "synthetic_write"},
    ],
)
def test_synthetic_malformed_modified_approval_is_rejected(modified: object) -> None:
    payload = _fixture("approved.json")
    payload["samples"][0]["events"][0].update(decision="modify", modified=modified)
    with pytest.raises(ValueError, match="approval.modified"):
        adapt_inspect_log(payload)


def test_synthetic_argument_modification_preserves_proposal_and_effective_call() -> (
    None
):
    payload = _fixture("approved.json")
    payload["samples"][0]["events"][0].update(
        decision="modify",
        modified={
            "id": "call-1",
            "function": "synthetic_write",
            "arguments": {"value": 2},
        },
    )
    call = adapt_inspect_log(payload)["calls"][0]
    assert call["execution_status"] == InspectExecutionStatus.SUCCEEDED
    assert call["proposed_function"] == "synthetic_write"
    assert call["proposed_arguments"] == {"value": 1}
    assert call["effective_function"] == "synthetic_write"
    assert call["effective_arguments"] == {"value": 2}


@pytest.mark.parametrize(
    "completed",
    [
        "2026-08-28T06:52:45Z",
        "2026-08-28T06:52:45.123456+00:00",
        "2026-08-28T06:52:45+05:30",
        "2026-08-28T06:52:45",
        "2026-08-28 06:52:45",
        "20260828T065245",
    ],
)
def test_synthetic_supported_iso_completion_is_accepted(completed: str) -> None:
    payload = _fixture("approved.json")
    payload["samples"][0]["events"][1]["completed"] = completed
    assert (
        adapt_inspect_log(payload)["calls"][0]["execution_status"]
        == InspectExecutionStatus.SUCCEEDED
    )


@pytest.mark.parametrize("failed", [None, False, True])
def test_synthetic_supported_failure_marker_is_respected(failed: bool | None) -> None:
    payload = _fixture("approved.json")
    payload["samples"][0]["events"][1]["failed"] = failed
    expected = (
        InspectExecutionStatus.UNKNOWN if failed else InspectExecutionStatus.SUCCEEDED
    )
    assert adapt_inspect_log(payload)["calls"][0]["execution_status"] == expected


@pytest.mark.parametrize("omit", [False, True])
def test_synthetic_missing_completion_is_unknown(omit: bool) -> None:
    payload = _fixture("approved.json")
    event = payload["samples"][0]["events"][1]
    if omit:
        event.pop("completed")
    else:
        event["completed"] = None
    assert (
        adapt_inspect_log(payload)["calls"][0]["execution_status"]
        == InspectExecutionStatus.UNKNOWN
    )


def test_synthetic_unresolved_escalation_does_not_establish_success() -> None:
    payload = _fixture("approved.json")
    payload["samples"][0]["events"][0]["decision"] = "escalate"
    call = adapt_inspect_log(payload)["calls"][0]
    assert call["execution_status"] == InspectExecutionStatus.UNKNOWN
    assert "unresolved approval escalation" in call["notes"]


@pytest.mark.parametrize("decision", ["reject", "terminate"])
def test_synthetic_supported_denial_decisions_require_matching_error(
    decision: str,
) -> None:
    payload = _fixture("rejected.json")
    payload["samples"][0]["events"][0]["decision"] = decision
    assert (
        adapt_inspect_log(payload)["calls"][0]["execution_status"]
        == InspectExecutionStatus.DENIED
    )


def test_synthetic_tool_ids_are_scoped_to_samples() -> None:
    payload = _fixture("approved.json")
    second_sample = json.loads(json.dumps(payload["samples"][0]))
    second_sample["id"] = "another-sample"
    payload["samples"].append(second_sample)
    report = adapt_inspect_log(payload)
    assert report["tool_call_count"] == 2
    assert all(
        call["execution_status"] == InspectExecutionStatus.SUCCEEDED
        for call in report["calls"]
    )


def test_synthetic_missing_tool_arguments_are_not_assumed_empty() -> None:
    payload = _fixture("approved.json")
    events = payload["samples"][0]["events"]
    events.pop(0)
    events[0].pop("arguments")
    with pytest.raises(ValueError, match="tool.arguments"):
        adapt_inspect_log(payload)


def test_synthetic_function_changing_modification_is_rejected() -> None:
    payload = _fixture("approved.json")
    payload["samples"][0]["events"][0].update(
        decision="modify",
        modified={"id": "call-1", "function": "other_tool", "arguments": {"value": 2}},
    )
    with pytest.raises(ValueError, match="function-changing modifications"):
        adapt_inspect_log(payload)


def test_synthetic_modified_call_id_must_bind_to_original() -> None:
    payload = _fixture("approved.json")
    payload["samples"][0]["events"][0].update(
        decision="modify",
        modified={
            "id": "other-call",
            "function": "synthetic_write",
            "arguments": {"value": 2},
        },
    )
    with pytest.raises(ValueError, match="approval.modified.id must match"):
        adapt_inspect_log(payload)


@pytest.mark.parametrize("completed", ["2026-08-28", "20260828", "2026-W35-5"])
def test_synthetic_date_only_completion_is_rejected(completed: str) -> None:
    payload = _fixture("approved.json")
    payload["samples"][0]["events"][1]["completed"] = completed
    with pytest.raises(ValueError, match="tool.completed"):
        adapt_inspect_log(payload)


@pytest.mark.parametrize(
    "approved,executed",
    [(True, 1), (False, 0), (1, 1.0), ({"items": [True]}, {"items": [1]})],
)
def test_synthetic_approval_binding_preserves_json_value_types(
    approved: object, executed: object
) -> None:
    payload = _fixture("approved.json")
    payload["samples"][0]["events"][0]["call"]["arguments"] = {"value": approved}
    payload["samples"][0]["events"][1]["arguments"] = {"value": executed}
    with pytest.raises(ValueError, match="approval.call does not match"):
        adapt_inspect_log(payload)


@pytest.mark.parametrize("location", ["tool", "approval", "modified"])
@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), (1, 2), {1: "value"}])
def test_synthetic_argument_payload_requires_finite_json(
    location: str, invalid: object
) -> None:
    payload = _fixture("approved.json")
    events = payload["samples"][0]["events"]
    if location == "tool":
        events.pop(0)
        target = events[0]
    elif location == "approval":
        target = events[0]["call"]
    else:
        events[0].update(
            decision="modify",
            modified={"id": "call-1", "function": "synthetic_write", "arguments": {}},
        )
        target = events[0]["modified"]
    target["arguments"] = {"nested": [invalid]}
    with pytest.raises(ValueError, match="arguments.*finite JSON"):
        adapt_inspect_log(payload)


def test_synthetic_json_binding_ignores_object_key_order_only() -> None:
    payload = _fixture("approved.json")
    events = payload["samples"][0]["events"]
    events[0]["call"]["arguments"] = {"a": None, "b": [True, 1, 1.0, "s", {"x": 2}]}
    events[1]["arguments"] = {"b": [True, 1, 1.0, "s", {"x": 2}], "a": None}
    assert (
        adapt_inspect_log(payload)["calls"][0]["execution_status"]
        == InspectExecutionStatus.SUCCEEDED
    )
