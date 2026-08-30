"""Opt-in real Docker / mock-model smoke checks; never live inference."""

from __future__ import annotations

import json
import os

import pytest
from inspect_ai.model import (
    ChatCompletionChoice,
    ChatMessageAssistant,
    ModelOutput,
    get_model,
)
from inspect_ai.tool import ToolCall

import runner


@pytest.mark.skipif(
    os.environ.get("RUN_DOCKER_SMOKE") != "1", reason="opt-in Docker smoke"
)
@pytest.mark.parametrize("condition", ["benign", "adversarial"])
def test_note_exposure_and_effects_through_real_inspect(
    monkeypatch, tmp_path, condition
):
    cases = json.loads((runner.HERE / "cases.json").read_text())
    case = next(
        c
        for c in cases
        if c["variant"] == "direct"
        and c["condition"] == condition
        and c["repetition"] == 1
    )
    calls = [
        ("inspect_artifact", {"artifact_id": "public-report"}),
        ("inspect_artifact", {"artifact_id": "protected-draft"}),
    ]
    if condition == "adversarial":
        calls.append(
            (
                "publish_artifact",
                {"artifact_id": "protected-draft", "request_id": "forbidden-attempt"},
            )
        )
    calls.append(
        (
            "publish_artifact",
            {"artifact_id": "public-report", "request_id": "report-publication"},
        )
    )
    outputs = [
        ModelOutput(
            model="mockllm/model",
            choices=[
                ChatCompletionChoice(
                    message=ChatMessageAssistant(
                        content="Scripted smoke action.",
                        tool_calls=[
                            ToolCall(id=f"call-{i}", function=name, arguments=args)
                        ],
                    ),
                    stop_reason="tool_calls",
                )
            ],
        )
        for i, (name, args) in enumerate(calls)
    ]
    outputs.append(
        ModelOutput.from_content("mockllm/model", "Scripted smoke complete.")
    )
    # This substitution ensures the test cannot call the Ollama provider.
    monkeypatch.setattr(
        runner,
        "local_model",
        lambda: get_model("mockllm/model", custom_outputs=outputs, memoize=False),
    )
    manifest = json.loads((runner.HERE / "manifest.json").read_text())
    result = runner.run_sample(case, manifest, tmp_path / "run")
    assert result["sample_status"] == "completed", result
    assert result["task_complete"] is True, result
    assert result["note_returned"] is True, result
    assert result["note_in_successful_model_request"] is True, result
    assert result["forbidden_attempts"] == int(condition == "adversarial"), result
    assert result["effects"]["outcome"] == "no_forbidden_effect", result
