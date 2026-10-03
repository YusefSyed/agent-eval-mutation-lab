"""Native scripted Inspect/Docker execution; no hosted model or inference."""

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
from inspect_ai.model import ChatMessageAssistant, get_model
from inspect_ai.scorer import Score, scorer
from inspect_ai.solver import generate, use_tools
from inspect_ai.tool import ToolError, tool
from inspect_ai.util import sandbox
from inspect_tool_execution.policy import ExecutionGate, bound_approver
from inspect_tool_execution.provenance import PROJECT as LEGACY
from inspect_tool_execution.task import initialize_registry, mock_outputs

from .projection import canonical, views

PROJECT = Path(__file__).resolve().parents[2]
ROOT = PROJECT.parents[1]


def source_hashes() -> dict[str, str]:
    paths = [
        PROJECT / "pyproject.toml",
        PROJECT / "uv.lock",
        LEGACY / "cases.json",
        ROOT / "pyproject.toml",
        LEGACY / "pyproject.toml",
        LEGACY / "uv.lock",
    ]
    paths += sorted((PROJECT / "src").rglob("*.py"))
    paths += sorted((PROJECT / "sandbox").iterdir())
    paths += sorted((LEGACY / "src").rglob("*.py"))
    paths += [LEGACY / "sandbox" / name for name in ("registry.py", "snapshot.py")]
    paths += [
        ROOT / "src/agent_eval_mutation_lab" / name
        for name in ("models.py", "scorers_v3.py")
    ]
    return {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in paths
        if p.is_file()
    }


class Capture:
    def __init__(
        self,
        sample: str,
        gate: ExecutionGate,
        faults: dict[str, str],
        override: str | None,
    ) -> None:
        self.sample, self.gate = sample, gate
        self.faults, self.override = faults, override
        self.entries: list[dict[str, Any]] = []
        self.active = False

    async def invoke(self, function: str, arguments: dict[str, str]) -> str:
        if self.active:
            raise RuntimeError("overlapping wrapper invocation")
        self.active = True
        try:
            self.gate.consume(function, arguments)
            index = len(self.gate.approvals) - 1
            entry = {
                "invocation_id": f"invocation-{len(self.entries)}",
                "approval_index": index,
                "function": function,
                "arguments": dict(arguments),
            }
            self.entries.append(entry)
            fault = (
                self.faults.get(arguments.get("request_id", ""), "none")
                if function == "publish_artifact"
                else "none"
            )
            result = await sandbox().exec(
                [
                    "python",
                    "/opt/producer.py",
                    self.sample,
                    entry["invocation_id"],
                    function,
                    json.dumps(arguments, sort_keys=True),
                    fault,
                ],
                timeout=10,
                timeout_retry=False,
            )
            if not result.success:
                raise ToolError(result.stderr.strip() or "producer command failed")
            return (
                self.override
                if function == "publish_artifact" and self.override is not None
                else result.stdout.strip()
            )
        finally:
            self.active = False


@tool
def inspect_artifact(capture: Capture):
    async def execute(artifact_id: str) -> str:
        """Inspect an artifact.

        Args:
            artifact_id: Synthetic artifact identifier.
        """
        return await capture.invoke("inspect_artifact", {"artifact_id": artifact_id})

    return execute


@tool
def publish_artifact(capture: Capture):
    async def execute(artifact_id: str, request_id: str) -> str:
        """Set the synthetic publication flag.

        Args:
            artifact_id: Synthetic artifact identifier.
            request_id: Logical request identifier.
        """
        return await capture.invoke(
            "publish_artifact", {"artifact_id": artifact_id, "request_id": request_id}
        )

    return execute


@tool
def revoke_publication(capture: Capture):
    async def execute(artifact_id: str, request_id: str) -> str:
        """Clear the synthetic publication flag.

        Args:
            artifact_id: Synthetic artifact identifier.
            request_id: Logical request identifier.
        """
        return await capture.invoke(
            "revoke_publication", {"artifact_id": artifact_id, "request_id": request_id}
        )

    return execute


@scorer(metrics=[])
def export_evidence(sample: str, output: str, capture: Capture):
    async def score(state, target):
        # Transport DB bytes without opening/querying them. Prediction is sealed
        # by run_case before the separate read-only oracle opens this snapshot.
        snapshot = await sandbox().exec(
            ["python", "/opt/snapshot.py"], timeout=10, timeout_retry=False
        )
        if not snapshot.success:
            raise RuntimeError("snapshot export failed")
        encoded = await sandbox().exec(
            ["base64", "/state/evidence.sqlite3"], timeout=10, timeout_retry=False
        )
        checksum = await sandbox().exec(
            ["sha256sum", "/state/evidence.sqlite3"], timeout=10, timeout_retry=False
        )
        if not encoded.success or not checksum.success:
            raise RuntimeError("database transport failed")
        content = base64.b64decode("".join(encoded.stdout.split()), validate=True)
        if (
            len(content) > 1024 * 1024
            or hashlib.sha256(content).hexdigest() != checksum.stdout.split()[0]
        ):
            raise RuntimeError("database transport integrity failure")
        path = Path(output) / "databases" / (sample + ".sqlite3")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        sidecars = await sandbox().exec(
            [
                "python",
                "-c",
                "import json,pathlib; p=pathlib.Path('/state/receipts'); "
                "print(json.dumps({f.stem:json.loads(f.read_text()) "
                "for f in sorted(p.glob('*.json'))}))",
            ],
            timeout=10,
            timeout_retry=False,
        )
        if not sidecars.success or len(sidecars.stdout) > 1024 * 1024:
            raise RuntimeError("receipt transport failed")
        state.metadata["private_receipts"] = json.loads(sidecars.stdout)
        state.metadata["bridge_approvals"] = capture.gate.approvals
        state.metadata["bridge_invocations"] = capture.entries
        return Score(value=0, explanation="export only; no oracle read")

    return score


def native_capture(sample) -> dict[str, Any]:
    requests = []
    sequential = True
    for message in sample.messages:
        if isinstance(message, ChatMessageAssistant) and message.tool_calls:
            sequential &= len(message.tool_calls) == 1
            requests.extend(
                {"id": c.id, "function": c.function, "arguments": c.arguments}
                for c in message.tool_calls
            )
    tool_events = [e for e in sample.events if e.event == "tool"]
    # ToolEvent arguments are the proposed native call, even on modification.
    # Effective arguments are captured at the wrapper after gate.consume.
    events = [
        {
            "id": e.id,
            "function": e.function,
            "arguments": e.arguments,
            "error_type": e.error.type if e.error else None,
        }
        for e in tool_events
    ]
    sequential &= all(e.completed is not None for e in tool_events)
    sequential &= all(
        first.completed <= second.timestamp
        for first, second in zip(tool_events, tool_events[1:], strict=False)
    )
    terminal = bool(
        sample.messages
        and isinstance(sample.messages[-1], ChatMessageAssistant)
        and not sample.messages[-1].tool_calls
        and not sample.error
        and sample.limit is None
    )
    return {
        "requests": requests,
        "events": events,
        "single_call_turns": sequential,
        "terminal": terminal,
    }


def run_case(case: dict[str, Any], output: Path) -> dict[str, Any]:
    gate = ExecutionGate(case.get("approval_mode", "enforce"))
    capture = Capture(
        case["id"], gate, case.get("faults", {}), case.get("tool_response_override")
    )
    task = Task(
        dataset=[Sample(id=case["id"], input=case["input"])],
        solver=[
            initialize_registry(case["id"]),
            use_tools(
                inspect_artifact(capture),
                publish_artifact(capture),
                revoke_publication(capture),
            ),
            generate(),
        ],
        scorer=export_evidence(case["id"], str(output), capture),
        sandbox=("docker", str(PROJECT / "sandbox/compose.yaml")),
        message_limit=30,
        name="bridge-" + case["id"],
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
        raise RuntimeError("native Inspect sample failed")
    sample = log.samples[0]
    raw = {
        "sample_id": case["id"],
        "native": native_capture(sample),
        "approvals": gate.approvals,
        "invocations": capture.entries,
        "receipts": sample.metadata["private_receipts"],
        "sandbox_probes": sample.metadata["sandbox_probes"],
    }
    (output / "raw").mkdir(exist_ok=True)
    (output / "raw" / (case["id"] + ".json")).write_text(canonical(raw))
    sealed = {"sample_id": case["id"], "views": views(raw)}
    (output / "sealed").mkdir(exist_ok=True)
    seal_path = output / "sealed" / (case["id"] + ".json")
    # Exclusive-create seal before opening oracle. Offline verification later
    # checks bytes and recomputes from observations, never normalized effects.
    with seal_path.open("x") as stream:
        stream.write(canonical(sealed))
    from .verify import acceptance

    return acceptance(case, raw, sealed, output)


def run(output: Path) -> dict[str, Any]:
    if output.exists() and any(output.iterdir()):
        raise ValueError("output must be new or empty")
    output.mkdir(parents=True, exist_ok=True)
    identity = source_hashes()
    cases = json.loads((LEGACY / "cases.json").read_text())
    results = [run_case(case, output) for case in cases]
    if source_hashes() != identity:
        raise RuntimeError("sources changed during execution")
    report = {
        "schema_version": 1,
        "execution": "mock_model_actual_docker_tools",
        "live_model_evidence": False,
        "source_sha256": identity,
        "results": results,
        "all_acceptance_checks_pass": True,
    }
    (output / "normalized-report.json").write_text(canonical(report))
    from .verify import verify

    verify(output)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = run(args.output.resolve())
    print(
        canonical(
            {
                "cases": len(report["results"]),
                "all_acceptance_checks_pass": report["all_acceptance_checks_pass"],
            }
        )
    )


if __name__ == "__main__":
    main()
