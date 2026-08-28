"""Fail-closed adapter for plain JSON Inspect AI evaluation logs.

The adapter normalizes proposal, approval, and coarse execution evidence. It
does not infer side effects, transient harm, final environment state, or attack
success because generic Inspect tool events do not establish those facts.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class InspectExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    DENIED = "denied"
    FAILED_PRE_EXECUTION = "failed_pre_execution"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class InspectCallEvidence:
    sample_id: str
    call_id: str
    proposed_function: str
    proposed_arguments: dict[str, Any]
    effective_function: str
    effective_arguments: dict[str, Any]
    approval_decisions: tuple[str, ...]
    execution_status: InspectExecutionStatus
    error_type: str | None
    completed: bool
    result_present: bool
    notes: tuple[str, ...]


def _mapping(value: object, context: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
        raise ValueError(f"{context} must be an object with string keys")
    return dict(value)


def _events(sample: dict[str, Any]) -> list[dict[str, Any]]:
    value = sample.get("events")
    if not isinstance(value, list):
        raise ValueError("sample.events must be a list")
    return [_mapping(event, "sample event") for event in value]


def _approval_call(event: dict[str, Any]) -> dict[str, Any]:
    return _mapping(event.get("call"), "approval.call")


def _call_id(value: object, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} must be a non-empty string")
    return value


def _decision(event: dict[str, Any]) -> str:
    value = event.get("decision")
    if not isinstance(value, str):
        raise ValueError("approval.decision must be a string")
    return value


def _status_for(
    *,
    decisions: tuple[str, ...],
    error_type: str | None,
    completed: bool,
    failed: object,
) -> tuple[InspectExecutionStatus, tuple[str, ...]]:
    notes: list[str] = []
    unique_decisions = set(decisions)
    if len(unique_decisions) > 1:
        notes.append("conflicting approval decisions")
        return InspectExecutionStatus.UNKNOWN, tuple(notes)

    decision = decisions[-1] if decisions else None
    if decision in {"reject", "terminate"}:
        if error_type == "approval":
            return InspectExecutionStatus.DENIED, tuple(notes)
        notes.append("rejection lacks matching approval error")
        return InspectExecutionStatus.UNKNOWN, tuple(notes)

    if error_type == "approval":
        if decision in {None, "reject", "terminate"}:
            notes.append("denial inferred from structured approval error")
            return InspectExecutionStatus.DENIED, tuple(notes)
        notes.append("approval decision contradicts approval error")
        return InspectExecutionStatus.UNKNOWN, tuple(notes)

    if error_type == "parsing":
        return InspectExecutionStatus.FAILED_PRE_EXECUTION, tuple(notes)

    if error_type is None and completed and failed is not True:
        return InspectExecutionStatus.SUCCEEDED, tuple(notes)

    if error_type in {"timeout", "cancelled"}:
        notes.append("completion or side effects may be uncertain")
    elif error_type is not None:
        notes.append(f"generic error '{error_type}' does not prove no side effects")
    elif not completed:
        notes.append("tool event has no completion marker")
    elif failed is True:
        notes.append("hard failure does not establish side-effect rollback")
    return InspectExecutionStatus.UNKNOWN, tuple(notes)


def adapt_inspect_log(payload: dict[str, Any]) -> dict[str, Any]:
    samples_value = payload.get("samples")
    if not isinstance(samples_value, list):
        raise ValueError("Inspect log must contain a samples list")

    calls: list[InspectCallEvidence] = []
    approval_event_count = 0
    for raw_sample in samples_value:
        sample = _mapping(raw_sample, "sample")
        sample_id = str(sample.get("id", ""))
        if not sample_id:
            raise ValueError("sample.id is required")
        events = _events(sample)
        approvals: dict[str, list[dict[str, Any]]] = {}
        for event in events:
            if event.get("event") != "approval":
                continue
            approval_event_count += 1
            call = _approval_call(event)
            identifier = _call_id(call.get("id"), "approval.call.id")
            approvals.setdefault(identifier, []).append(event)

        for event in events:
            if event.get("event") != "tool":
                continue
            identifier = _call_id(event.get("id"), "tool.id")
            function = event.get("function")
            if not isinstance(function, str) or not function:
                raise ValueError("tool.function must be a non-empty string")
            arguments = _mapping(event.get("arguments", {}), "tool.arguments")
            correlated = approvals.get(identifier, [])
            decisions = tuple(_decision(approval) for approval in correlated)

            effective_function = function
            effective_arguments = arguments
            for approval in correlated:
                modified_value = approval.get("modified")
                if modified_value is None:
                    continue
                modified = _mapping(modified_value, "approval.modified")
                modified_function = modified.get("function")
                if isinstance(modified_function, str) and modified_function:
                    effective_function = modified_function
                effective_arguments = _mapping(
                    modified.get("arguments", {}), "approval.modified.arguments"
                )

            error_value = event.get("error")
            error_type: str | None = None
            if error_value is not None:
                error = _mapping(error_value, "tool.error")
                raw_error_type = error.get("type")
                if not isinstance(raw_error_type, str):
                    raise ValueError("tool.error.type must be a string")
                error_type = raw_error_type
            completed = isinstance(event.get("completed"), str)
            status, notes = _status_for(
                decisions=decisions,
                error_type=error_type,
                completed=completed,
                failed=event.get("failed"),
            )
            result = event.get("result")
            result_present = result is not None and result != ""
            calls.append(
                InspectCallEvidence(
                    sample_id=sample_id,
                    call_id=identifier,
                    proposed_function=function,
                    proposed_arguments=arguments,
                    effective_function=effective_function,
                    effective_arguments=effective_arguments,
                    approval_decisions=decisions,
                    execution_status=status,
                    error_type=error_type,
                    completed=completed,
                    result_present=result_present,
                    notes=notes,
                )
            )

    return {
        "schema_version": 1,
        "source_format": "inspect_ai_json_log",
        "source_log_status": payload.get("status"),
        "sample_count": len(samples_value),
        "tool_call_count": len(calls),
        "approval_event_count": approval_event_count,
        "evidence_coverage": {
            "proposal": True,
            "approval_decision": approval_event_count > 0,
            "coarse_execution_status": True,
            "partial_execution": False,
            "domain_side_effect_receipt": False,
            "transient_harm": False,
            "final_environment_state": False,
        },
        "attack_success_ready": False,
        "attack_success_blocker": (
            "Generic Inspect tool events do not establish domain side effects, "
            "transient harm, partial execution, or final environment state."
        ),
        "calls": [
            {
                "sample_id": call.sample_id,
                "call_id": call.call_id,
                "proposed_function": call.proposed_function,
                "proposed_arguments": call.proposed_arguments,
                "effective_function": call.effective_function,
                "effective_arguments": call.effective_arguments,
                "approval_decisions": list(call.approval_decisions),
                "execution_status": call.execution_status.value,
                "error_type": call.error_type,
                "completed": call.completed,
                "result_present": call.result_present,
                "notes": list(call.notes),
            }
            for call in calls
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Inspect execution-evidence adapter",
        "",
        f"- Samples: {report['sample_count']}",
        f"- Tool calls: {report['tool_call_count']}",
        f"- Approval events: {report['approval_event_count']}",
        f"- Attack-success ready: {str(report['attack_success_ready']).lower()}",
        "",
        f"**Blocker:** {report['attack_success_blocker']}",
        "",
        "## Evidence coverage",
        "",
        "| Field | Supported |",
        "| --- | --- |",
    ]
    for name, supported in report["evidence_coverage"].items():
        lines.append(f"| {name.replace('_', ' ')} | {str(supported).lower()} |")
    lines.extend(
        [
            "",
            "## Normalized calls",
            "",
            "| Sample | Call | Function | Approval | Status | Error | Result |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for call in report["calls"]:
        decisions = ", ".join(call["approval_decisions"]) or "none"
        lines.append(
            f"| {call['sample_id']} | {call['call_id']} | "
            f"{call['effective_function']} | {decisions} | "
            f"{call['execution_status']} | {call['error_type'] or 'none'} | "
            f"{str(call['result_present']).lower()} |"
        )
    lines.extend(
        [
            "",
            "This adapter intentionally stops at execution-evidence coverage. It "
            "does not convert generic tool logs into attack-success labels.",
            "",
        ]
    )
    return "\n".join(lines)


def write_adapter_reports(
    report: dict[str, Any], output_dir: Path
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "inspect-evidence.json"
    markdown_path = output_dir / "inspect-evidence.md"
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize execution evidence from a plain JSON Inspect log."
    )
    parser.add_argument("log", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts/inspect"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    raw = json.loads(args.log.read_text(encoding="utf-8"))
    payload = _mapping(raw, "Inspect log")
    json_path, markdown_path = write_adapter_reports(
        adapt_inspect_log(payload), args.output
    )
    print(f"Wrote {json_path}")
    print(f"Wrote {markdown_path}")


if __name__ == "__main__":
    main()
