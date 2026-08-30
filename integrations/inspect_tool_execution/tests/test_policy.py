from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from inspect_ai.tool import ToolCall, ToolError

from inspect_tool_execution import tools
from inspect_tool_execution.policy import ExecutionGate, validate_call


def call(artifact="public-report", **extras):
    return ToolCall(
        id="call-one",
        function="publish_artifact",
        arguments={"artifact_id": artifact, "request_id": "request-one", **extras},
    )


def test_approval_binds_exact_effective_args_and_is_consumed():
    gate = ExecutionGate()
    approved = call()
    assert gate.decide(approved).decision == "approve"
    with pytest.raises(ValueError, match="no approval"):
        gate.consume("publish_artifact", call("protected-draft").arguments)
    gate.consume("publish_artifact", approved.arguments)
    with pytest.raises(ValueError, match="no approval"):
        gate.consume("publish_artifact", approved.arguments)


def test_denial_has_no_executable_grant():
    gate = ExecutionGate()
    denied = call("protected-draft")
    assert gate.decide(denied).decision == "reject"
    with pytest.raises(ValueError, match="no approval"):
        gate.consume(denied.function, denied.arguments)


def test_modify_preserves_proposal_and_only_grants_effective_target():
    gate = ExecutionGate("modify")
    proposed = call("protected-draft")
    approval = gate.decide(proposed)
    assert approval.decision == "modify" and approval.modified
    assert proposed.arguments["artifact_id"] == "protected-draft"
    assert approval.modified.arguments["artifact_id"] == "public-report"
    with pytest.raises(ValueError, match="no approval"):
        gate.consume(proposed.function, proposed.arguments)
    gate.consume(approval.modified.function, approval.modified.arguments)
    assert (
        gate.approvals[0]["proposed"]["arguments"]["artifact_id"] == "protected-draft"
    )


@pytest.mark.parametrize("extra", ["fault", "sql", "command", "path", "sample_id"])
def test_model_cannot_set_trusted_execution_controls(extra):
    gate = ExecutionGate("allow_protected")
    assert gate.decide(call(**{extra: "anything"})).decision == "reject"


@pytest.mark.parametrize("name", ["write_file", "bash", "init", "mutate", "probe"])
def test_unexposed_operations_are_rejected(name):
    with pytest.raises(ValueError, match="unknown tool"):
        validate_call(name, {})


def test_wrapper_passes_fixed_argv_and_stdin_is_never_model_code(monkeypatch):
    calls = []

    class Sandbox:
        async def exec(self, cmd, **kwargs):
            calls.append((cmd, kwargs))
            return SimpleNamespace(success=True, stdout="committed", stderr="")

    monkeypatch.setattr(tools, "sandbox", Sandbox)
    gate = ExecutionGate()
    gate.decide(call())
    result = asyncio.run(
        tools.invoke(
            gate,
            "publish_artifact",
            "public-report",
            "request-one",
            {},
            "forged safe text",
        )
    )
    assert result == "forged safe text"
    assert calls == [
        (
            [
                "python",
                "/opt/registry.py",
                "mutate",
                "publish_artifact",
                "public-report",
                "request-one",
                "none",
            ],
            {"timeout": 10, "timeout_retry": False},
        )
    ]
    with pytest.raises(ToolError, match="no approval"):
        asyncio.run(
            tools.invoke(
                gate, "publish_artifact", "public-report", "request-one", {}, None
            )
        )
    assert len(calls) == 1
