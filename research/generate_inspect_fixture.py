"""Generate genuine Inspect JSON logs for adapter compatibility checks.

Run with:
    uv run --with inspect-ai==0.3.260 \
        research/generate_inspect_fixture.py --output tmp/inspect-fixtures
"""

from __future__ import annotations

import argparse
from pathlib import Path

from inspect_ai import Task, eval
from inspect_ai.approval import Approval, ApprovalPolicy, approver
from inspect_ai.dataset import Sample
from inspect_ai.model import (
    ChatCompletionChoice,
    ChatMessageAssistant,
    ModelOutput,
    get_model,
)
from inspect_ai.solver import generate, use_tools
from inspect_ai.tool import ToolCall, tool


@tool
def synthetic_write():
    async def execute(value: int) -> str:
        """Write a synthetic integer.

        Args:
            value: Synthetic value to record.
        """

        return f"wrote:{value}"

    return execute


@approver
def conditional_approver():
    async def approve(message, call, view, history):  # type: ignore[no-untyped-def]
        if call.arguments.get("value") == 99:
            return Approval(
                decision="reject",
                explanation="synthetic policy rejection",
            )
        return Approval(
            decision="approve",
            explanation="synthetic policy approval",
        )

    return approve


def _outputs(value: int) -> list[ModelOutput]:
    call = ToolCall(
        id=f"call-{value}",
        function="synthetic_write",
        arguments={"value": value},
    )
    proposal = ModelOutput(
        model="mockllm/model",
        choices=[
            ChatCompletionChoice(
                message=ChatMessageAssistant(
                    content=f"propose {value}",
                    tool_calls=[call],
                    model="mockllm/model",
                    source="generate",
                ),
                stop_reason="tool_calls",
            )
        ],
    )
    return [
        proposal,
        ModelOutput.from_content("mockllm/model", f"finished {value}"),
    ]


def _run(value: int, name: str, output: Path) -> None:
    task = Task(
        dataset=[Sample(input=f"write {value}", id=name)],
        solver=[use_tools(synthetic_write()), generate()],
        scorer=None,
        name=name,
    )
    eval(
        task,
        model=get_model(
            "mockllm/model",
            custom_outputs=_outputs(value),
            memoize=False,
        ),
        approval=[
            ApprovalPolicy(
                approver=conditional_approver(),
                tools="synthetic_write",
            )
        ],
        log_dir=str(output),
        log_format="json",
        display="none",
        max_samples=1,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    _run(1, "approved", args.output)
    _run(99, "rejected", args.output)
    print(args.output)


if __name__ == "__main__":
    main()

