"""Deterministic mock-model / actual-tool Inspect acceptance harness."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from inspect_ai import Task, eval
from inspect_ai.approval import ApprovalPolicy
from inspect_ai.dataset import Sample
from inspect_ai.model import (
    ChatCompletionChoice,
    ChatMessageAssistant,
    ModelOutput,
    get_model,
)
from inspect_ai.scorer import Score, Scorer, Target, scorer
from inspect_ai.solver import Generate, Solver, TaskState, generate, solver, use_tools
from inspect_ai.tool import ToolCall
from inspect_ai.util import sandbox

from .effect_scorer import read_effects
from .policy import ExecutionGate, bound_approver
from .provenance import PROJECT, source_hashes
from .tools import HELPER, inspect_artifact, publish_artifact, revoke_publication


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2) + "\n"


@solver
def initialize_registry(sample_id: str) -> Solver:
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        result = await sandbox().exec(
            HELPER + ["init", sample_id], timeout=10, timeout_retry=False
        )
        if not result.success:
            raise RuntimeError("registry initialization failed: " + result.stderr)
        result = await sandbox().exec(
            HELPER + ["probe"], timeout=10, timeout_retry=False
        )
        if not result.success:
            raise RuntimeError("sandbox probe failed")
        probes = json.loads(result.stdout)
        state.metadata["sandbox_probes"] = probes
        if not probes or not all(value is True for value in probes.values()):
            raise RuntimeError("sandbox isolation probe failed: " + str(probes))
        return state

    return solve


@scorer(metrics=[])
def persisted_effects(case: dict[str, Any], output: str, gate: ExecutionGate) -> Scorer:
    async def score(state: TaskState, target: Target) -> Score:
        path = Path(output) / "databases" / f"{case['id']}.sqlite3"
        path.parent.mkdir(parents=True, exist_ok=True)
        export_error = None
        try:
            # Docker Desktop's cp path cannot see this tmpfs file. Export raw
            # bytes through fixed harness-only commands, never a model tool.
            snapshot = await sandbox().exec(
                ["python", "/opt/snapshot.py"], timeout=10, timeout_retry=False
            )
            if not snapshot.success:
                raise RuntimeError("consistent database snapshot failed")
            encoded = await sandbox().exec(
                ["base64", "/state/evidence.sqlite3"], timeout=10, timeout_retry=False
            )
            checksum = await sandbox().exec(
                ["sha256sum", "/state/evidence.sqlite3"],
                timeout=10,
                timeout_retry=False,
            )
            if not encoded.success or not checksum.success:
                raise RuntimeError("raw database export failed")
            content = base64.b64decode("".join(encoded.stdout.split()), validate=True)
            if (
                len(content) > 1024 * 1024
                or hashlib.sha256(content).hexdigest() != checksum.stdout.split()[0]
            ):
                raise RuntimeError("raw database transport integrity failed")
            path.write_bytes(content)
        except Exception as error:
            export_error = type(error).__name__
            state.metadata["export_error_detail"] = str(error)
        effects = read_effects(path, case["id"])
        if export_error:
            effects = {
                "outcome": "unknown",
                "sample_id": case["id"],
                "error": "database_export_failed",
            }
        passed = (
            effects["outcome"] == case["expected_outcome"]
            and len(effects.get("events", [])) == case["expected_events"]
            and effects.get("final_published") == case["expected_final"]
        )
        report = {
            "case_id": case["id"],
            "expected_effects_match": passed,
            "effects": effects,
            "approvals": gate.approvals,
            "sandbox_probes": state.metadata["sandbox_probes"],
        }
        state.metadata["effect_report"] = report
        return Score(value=int(passed), explanation=effects["outcome"], metadata=report)

    return score


def mock_outputs(case: dict[str, Any]) -> list[ModelOutput]:
    outputs = []
    for index, call in enumerate(case["calls"]):
        message = ChatMessageAssistant(
            content=case.get("assistant_text", "Execute the next requested action."),
            tool_calls=[
                ToolCall(
                    id=f"call-{index}",
                    function=call["function"],
                    arguments=call["arguments"],
                )
            ],
            model="mockllm/model",
            source="generate",
        )
        outputs.append(
            ModelOutput(
                model="mockllm/model",
                choices=[
                    ChatCompletionChoice(message=message, stop_reason="tool_calls")
                ],
            )
        )
    outputs.append(
        ModelOutput.from_content(
            "mockllm/model", case.get("final_text", "Fixture complete.")
        )
    )
    return outputs


def run_case(case: dict[str, Any], output: Path) -> dict[str, Any]:
    gate = ExecutionGate(case.get("approval_mode", "enforce"))
    task = Task(
        dataset=[Sample(id=case["id"], input=case["input"])],
        solver=[
            initialize_registry(case["id"]),
            use_tools(
                inspect_artifact(gate),
                publish_artifact(
                    gate, case.get("faults", {}), case.get("tool_response_override")
                ),
                revoke_publication(gate),
            ),
            generate(),
        ],
        scorer=persisted_effects(case, str(output), gate),
        sandbox=("docker", str(PROJECT / "sandbox" / "compose.yaml")),
        message_limit=30,
        name=f"effects-{case['id']}",
    )
    logs = eval(
        task,
        model=get_model(
            "mockllm/model", custom_outputs=mock_outputs(case), memoize=False
        ),
        approval=[ApprovalPolicy(approver=bound_approver(gate), tools="*")],
        log_dir=str(output / "inspect-logs"),
        log_format="json",
        display="none",
        max_samples=1,
        max_tasks=1,
    )
    log = logs[0]
    if log.status != "success" or not log.samples or log.samples[0].error:
        error = log.error or (log.samples[0].error if log.samples else None)
        raise RuntimeError(
            f"Inspect failed for {case['id']}: {error.message if error else 'unknown'}"
        )
    sample = log.samples[0]
    report = sample.metadata["effect_report"]
    tool_events = [event for event in sample.events if event.event == "tool"]
    report["tool_execution"] = [
        {
            "function": event.function,
            "error_type": event.error.type if event.error else None,
        }
        for event in tool_events
    ]
    report["expected_dispatch_match"] = (
        [event["error_type"] for event in report["tool_execution"]]
        == case["expected_tool_errors"]
        and [event["function"] for event in report["tool_execution"]]
        == [call["function"] for call in case["calls"]]
        and report["approvals"] == case["expected_approval_records"]
    )
    return report


def run(output: Path, selected: set[str] | None = None) -> dict[str, Any]:
    if output.exists() and any(output.iterdir()):
        raise ValueError("output directory must be new or empty; never reuse evidence")
    output.mkdir(parents=True, exist_ok=True)
    execution_sources = source_hashes()
    cases_bytes = (PROJECT / "cases.json").read_bytes()
    cases = json.loads(cases_bytes)
    if selected:
        cases = [case for case in cases if case["id"] in selected]
        if {case["id"] for case in cases} != selected:
            raise ValueError("unknown selected case")
    results = [run_case(case, output) for case in cases]
    if execution_sources != source_hashes():
        raise RuntimeError("execution source changed during the run")
    report = {
        "schema_version": 1,
        "source_sha256": execution_sources,
        "execution": "mock_model_actual_docker_tools",
        "inspect_version": "0.3.260",
        "live_model_evidence": False,
        "full_suite": not bool(selected),
        "cases_sha256": hashlib.sha256(cases_bytes).hexdigest(),
        "all_expected_effects_match": all(r["expected_effects_match"] for r in results),
        "all_expected_dispatch_match": all(
            r["expected_dispatch_match"] for r in results
        ),
        "all_acceptance_checks_pass": all(
            r["expected_effects_match"] and r["expected_dispatch_match"]
            for r in results
        ),
        "results": results,
    }
    (output / "normalized-report.json").write_text(canonical(report))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--case", action="append", default=[])
    args = parser.parse_args()
    report = run(args.output.resolve(), set(args.case) or None)
    print(
        canonical(
            {
                "cases": len(report["results"]),
                "all_expected_effects_match": report["all_expected_effects_match"],
                "all_acceptance_checks_pass": report["all_acceptance_checks_pass"],
                "output": str(args.output),
            }
        )
    )
    if not report["all_acceptance_checks_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
