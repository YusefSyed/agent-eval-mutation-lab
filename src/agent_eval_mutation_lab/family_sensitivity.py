"""Leave-one-scenario-family-out sensitivity for v1/v2 comparisons."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agent_eval_mutation_lab.v2_evaluation import _metrics, run_v2_comparison


def run_family_sensitivity() -> dict[str, Any]:
    comparison = run_v2_comparison()
    results: dict[str, Any] = {}
    for condition, scorer_results in comparison["conditions"].items():
        condition_result: dict[str, Any] = {}
        for scorer_name, scorer_result in scorer_results.items():
            rows = scorer_result["cases"]
            families = sorted({row["family"] for row in rows})
            omissions = {
                family: _metrics(
                    [row for row in rows if row["family"] != family]
                )
                for family in families
            }
            condition_result[scorer_name] = {
                "full_metrics": scorer_result["metrics"],
                "omissions": omissions,
                "tri_state_accuracy_range": [
                    min(
                        metric["tri_state_accuracy"]
                        for metric in omissions.values()
                    ),
                    max(
                        metric["tri_state_accuracy"]
                        for metric in omissions.values()
                    ),
                ],
                "coverage_range": [
                    min(metric["coverage_rate"] for metric in omissions.values()),
                    max(metric["coverage_rate"] for metric in omissions.values()),
                ],
                "max_false_safe_count": max(
                    metric["false_safe_count"] for metric in omissions.values()
                ),
                "max_false_success_count": max(
                    metric["false_success_count"] for metric in omissions.values()
                ),
                "max_unsupported_overclaim_count": max(
                    metric["unsupported_safe_count"]
                    + metric["unsupported_success_count"]
                    for metric in omissions.values()
                ),
            }
        results[condition] = condition_result
    return {
        "schema_version": 1,
        "unit": "scenario family",
        "interpretation": (
            "Exact leave-one-family-out sensitivity on the finite corpus; "
            "not a population uncertainty interval."
        ),
        "conditions": results,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Leave-one-scenario-family-out sensitivity",
        "",
        f"**Interpretation:** {report['interpretation']}",
        "",
        "| Condition | Scorer | Accuracy range | Coverage range | "
        "Max false safe | Max false success | Max unknown overclaim |",
        "| --- | --- | --- | --- | ---: | ---: | ---: |",
    ]
    for condition, scorer_results in report["conditions"].items():
        for scorer_name, result in scorer_results.items():
            accuracy = result["tri_state_accuracy_range"]
            coverage = result["coverage_range"]
            lines.append(
                f"| {condition.replace('_', ' ')} | {scorer_name} | "
                f"{accuracy[0]:.3f}-{accuracy[1]:.3f} | "
                f"{coverage[0]:.3f}-{coverage[1]:.3f} | "
                f"{result['max_false_safe_count']} | "
                f"{result['max_false_success_count']} | "
                f"{result['max_unsupported_overclaim_count']} |"
            )
    lines.extend(
        [
            "",
            "Ranges show dependence on the included scenario families. They do "
            "not justify confidence intervals or broad generalization.",
            "",
        ]
    )
    return "\n".join(lines)


def write_family_reports(
    report: dict[str, Any], output_dir: Path
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "family-sensitivity.json"
    markdown_path = output_dir / "family-sensitivity.md"
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run leave-one-family-out sensitivity."
    )
    parser.add_argument("--output", type=Path, default=Path("artifacts/v2"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    json_path, markdown_path = write_family_reports(
        run_family_sensitivity(), args.output
    )
    print(f"Wrote {json_path}")
    print(f"Wrote {markdown_path}")


if __name__ == "__main__":
    main()

