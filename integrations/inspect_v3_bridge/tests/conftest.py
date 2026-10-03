"""Isolated stdlib registry/producer tests, without Docker or provider calls."""

import importlib.util
import json
import sys
from copy import deepcopy

import pytest
from inspect_ai.tool import ToolCall
from inspect_tool_execution.policy import ACTIONS, ExecutionGate
from inspect_tool_execution.provenance import PROJECT as LEGACY

from inspect_v3_bridge.runner import PROJECT
from inspect_v3_bridge.verify import PROBE_KEYS


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


registry = load_module("registry", LEGACY / "sandbox/registry.py")
producer = load_module("bridge_test_producer", PROJECT / "sandbox/producer.py")
CASES = json.loads((LEGACY / "cases.json").read_text())


@pytest.fixture
def execute_fixture(tmp_path):
    def execute(case):
        case = deepcopy(case)
        directory = tmp_path / case["id"]
        directory.mkdir()
        database = directory / "registry.sqlite3"
        registry.initialize(database, case["id"])
        gate = ExecutionGate(case.get("approval_mode", "enforce"))
        requests, events, invocations = [], [], []
        for i, proposed in enumerate(case["calls"]):
            native = dict(proposed, id=f"call-{i}")
            requests.append(native)
            event = dict(native, error_type=None)
            events.append(event)
            if proposed["function"] not in ACTIONS:
                event["error_type"] = "parsing"
                continue
            approval = gate.decide(ToolCall(**native))
            if approval.decision == "reject":
                event["error_type"] = "approval"
                continue
            effective = gate.approvals[-1]["effective"]
            gate.consume(**effective)
            entry = dict(
                effective,
                invocation_id=f"invocation-{len(invocations)}",
                approval_index=len(gate.approvals) - 1,
            )
            invocations.append(entry)
            fault = case.get("faults", {}).get(
                effective["arguments"].get("request_id"), "none"
            )
            try:
                producer.produce(
                    database,
                    directory / "receipts",
                    case["id"],
                    entry["invocation_id"],
                    effective["function"],
                    effective["arguments"],
                    fault,
                )
            except (ValueError, RuntimeError):
                event["error_type"] = "unknown"
        receipts = {
            p.stem: json.loads(p.read_text())
            for p in (directory / "receipts").glob("*.json")
        }
        raw = {
            "sample_id": case["id"],
            "native": {
                "requests": requests,
                "events": events,
                "terminal": True,
                "single_call_turns": True,
            },
            "approvals": gate.approvals,
            "invocations": invocations,
            "receipts": receipts,
            "sandbox_probes": dict.fromkeys(PROBE_KEYS, True),
        }
        return raw, database

    return execute
