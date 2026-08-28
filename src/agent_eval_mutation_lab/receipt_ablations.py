"""Predeclared evidence ablations for the receipt-aware scorer."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from agent_eval_mutation_lab.cases import benchmark_cases
from agent_eval_mutation_lab.models import (
    ActionStatus,
    ObservedAction,
    ObservedTrajectory,
    Receipt,
)
from agent_eval_mutation_lab.scorers import receipt_aware_scorer
from agent_eval_mutation_lab.simulator import execute


def _ablate(
    trajectory: ObservedTrajectory, mode: str
) -> ObservedTrajectory:
    actions: list[ObservedAction] = []
    for action in trajectory.actions:
        receipt = action.receipt
        if receipt is None or not action.prohibited:
            actions.append(action)
            continue
        if mode == "baseline":
            actions.append(action)
        elif mode == "remove_prohibited_receipts":
            actions.append(replace(action, receipt=None))
        elif mode == "remove_effect_records":
            actions.append(replace(action, receipt=replace(receipt, effects=())))
        elif mode == "replace_success_with_timeout":
            if receipt.status in {ActionStatus.SUCCESS, ActionStatus.PARTIAL}:
                actions.append(
                    replace(
                        action,
                        receipt=Receipt(status=ActionStatus.TIMED_OUT),
                    )
                )
            else:
                actions.append(action)
        else:
            raise ValueError(f"unknown ablation mode: {mode}")
    return replace(trajectory, actions=tuple(actions))


def run_receipt_ablations() -> dict[str, Any]:
    modes = (
        "baseline",
        "remove_prohibited_receipts",
        "remove_effect_records",
        "replace_success_with_timeout",
    )
    results: dict[str, Any] = {}
    for mode in modes:
        rows: list[dict[str, Any]] = []
        for case in benchmark_cases():
            outcome, observation = execute(case.scenario)
            prediction = receipt_aware_scorer(_ablate(observation, mode))
            rows.append(
                {
                    "case_id": case.case_id,
                    "expected": outcome.attack_success,
                    "prediction": prediction,
                }
            )
        known = [row for row in rows if row["expected"] is not None]
        total = len(known)
        results[mode] = {
            "known_cases": total,
            "accuracy": sum(
                row["prediction"] == row["expected"] for row in known
            )
            / total,
            "false_success_rate": sum(
                row["prediction"] is True and row["expected"] is False
                for row in known
            )
            / total,
            "false_safe_rate": sum(
                row["prediction"] is False and row["expected"] is True
                for row in known
            )
            / total,
            "abstention_rate": sum(
                row["prediction"] is None for row in known
            )
            / total,
            "cases": rows,
        }
    return {
        "schema_version": 1,
        "scope": "receipt-evidence ablations on the finite synthetic corpus",
        "interpretation": (
            "Ablations measure dependence on scorer-visible evidence; they do "
            "not estimate real-world reliability."
        ),
        "ablations": results,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Receipt-evidence ablations",
        "",
        f"**Scope:** {report['scope']}",
        "",
        f"**Interpretation:** {report['interpretation']}",
        "",
        "| Ablation | Accuracy | False success | False safe | Abstain |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name, result in report["ablations"].items():
        lines.append(
            f"| {name.replace('_', ' ')} | {result['accuracy']:.3f} | "
            f"{result['false_success_rate']:.3f} | "
            f"{result['false_safe_rate']:.3f} | "
            f"{result['abstention_rate']:.3f} |"
        )
    lines.extend(
        [
            "",
            "Removing effect records is the critical circularity check: a scorer "
            "must not treat a successful prohibited call with missing effect "
            "evidence as established safety.",
            "",
        ]
    )
    return "\n".join(lines)


def write_ablation_reports(
    report: dict[str, Any], output_dir: Path
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "receipt-ablations.json"
    markdown_path = output_dir / "receipt-ablations.md"
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run receipt-evidence ablations.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/ablations"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    json_path, markdown_path = write_ablation_reports(
        run_receipt_ablations(), args.output
    )
    print(f"Wrote {json_path}")
    print(f"Wrote {markdown_path}")


if __name__ == "__main__":
    main()

