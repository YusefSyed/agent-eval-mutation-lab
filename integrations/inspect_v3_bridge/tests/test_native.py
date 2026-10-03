"""Native Inspect mock-loop contract tests with isolated local tool stubs."""

import json
from types import SimpleNamespace

import pytest
from conftest import CASES, producer, registry
from inspect_ai import Task, eval
from inspect_ai.approval import ApprovalPolicy
from inspect_ai.dataset import Sample
from inspect_ai.model import get_model
from inspect_ai.solver import generate, use_tools
from inspect_ai.tool import ToolError
from inspect_tool_execution.policy import ExecutionGate, bound_approver
from inspect_tool_execution.task import mock_outputs

from inspect_v3_bridge import runner
from inspect_v3_bridge.projection import views
from inspect_v3_bridge.verify import PROBE_KEYS


def run_native_fixture(case, tmp_path):
    tmp_path.mkdir(exist_ok=True)
    database = tmp_path / "registry.sqlite3"
    registry.initialize(database, case["id"])
    gate = ExecutionGate(case.get("approval_mode", "enforce"))

    class LocalCapture(runner.Capture):
        async def invoke(self, function, arguments):
            self.gate.consume(function, arguments)
            entry = {
                "invocation_id": f"invocation-{len(self.entries)}",
                "approval_index": len(self.gate.approvals) - 1,
                "function": function,
                "arguments": arguments,
            }
            self.entries.append(entry)
            try:
                result = producer.produce(
                    database,
                    tmp_path / "receipts",
                    self.sample,
                    entry["invocation_id"],
                    function,
                    arguments,
                    self.faults.get(arguments.get("request_id", ""), "none"),
                )
            except Exception as error:
                raise ToolError(str(error)) from error
            return self.override if self.override is not None else json.dumps(result)

    capture = LocalCapture(
        case["id"], gate, case.get("faults", {}), case.get("tool_response_override")
    )
    task = Task(
        dataset=[Sample(id=case["id"], input=case["input"])],
        solver=[
            use_tools(
                runner.inspect_artifact(capture),
                runner.publish_artifact(capture),
                runner.revoke_publication(capture),
            ),
            generate(),
        ],
    )
    logs = eval(
        task,
        model=get_model(
            "mockllm/model", custom_outputs=mock_outputs(case), memoize=False
        ),
        approval=[ApprovalPolicy(approver=bound_approver(gate), tools="*")],
        log_dir=str(tmp_path / "native-unit-logs"),
        log_format="json",
        display="none",
        max_samples=1,
        max_tasks=1,
    )
    assert logs[0].status == "success"
    sample = logs[0].samples[0]
    native = runner.native_capture(sample)
    raw = {
        "sample_id": case["id"],
        "native": native,
        "approvals": gate.approvals,
        "invocations": capture.entries,
        "receipts": {
            p.stem: json.loads(p.read_text())
            for p in (tmp_path / "receipts").glob("*.json")
        },
        "sandbox_probes": dict.fromkeys(PROBE_KEYS, True),
    }
    expected = case["expected_outcome"] == "forbidden_effect"
    assert views(raw)["complete"]["prediction"] is (
        None if case["id"] == "conflicting-reuse" else expected
    )
    assert [e["error_type"] for e in native["events"]] == case["expected_tool_errors"]

    metadata = {
        "bridge_approvals": gate.approvals,
        "bridge_invocations": capture.entries,
        "private_receipts": raw["receipts"],
        "sandbox_probes": raw["sandbox_probes"],
    }
    log_path = next((tmp_path / "native-unit-logs").glob("*.json"))
    document = json.loads(log_path.read_text())
    document["samples"][0]["metadata"].update(metadata)
    log_path.write_text(json.dumps(document))
    return raw, database, log_path


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_native_mock_loop_reconciles_local_stub(case, tmp_path):
    run_native_fixture(case, tmp_path)


def test_unfinished_limit_and_overlap_never_certify():
    sample = SimpleNamespace(messages=[], events=[], error=None, limit=None)
    assert runner.native_capture(sample)["terminal"] is False
