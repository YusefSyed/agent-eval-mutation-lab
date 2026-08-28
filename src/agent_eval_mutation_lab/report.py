"""Deterministic JSON and Markdown report rendering."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Agent Eval Mutation Lab — finite benchmark report",
        "",
        f"**Research question:** {report['research_question']}",
        "",
        f"**Scope:** {report['scope']}",
        "",
        f"**Cases:** {report['case_count']}",
        "",
        "## Scorer summary",
        "",
        "| Scorer | Accuracy | False success | False safe | Abstain | "
        "Label-changing | Invariance |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, summary in report["scorers"].items():
        lines.append(
            "| {name} | {accuracy:.3f} | {false_success_rate:.3f} | "
            "{false_safe_rate:.3f} | {abstention_rate:.3f} | "
            "{label_changing_semantic_score:.3f} | "
            "{label_preserving_invariance:.3f} |".format(name=name, **summary)
        )

    lines.extend(
        [
            "",
            "## Case results",
            "",
            "| Case | Family | Source | Mutation | Expected | Attempt | Final state | "
            "Receipt aware |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for case in report["cases"]:
        predictions = case["predictions"]
        lines.append(
            f"| {case['case_id']} | {case['family']} | {case['source']} | "
            f"{case['mutation'] or '—'} | {case['expected_attack_success']} | "
            f"{predictions['attempted_call']} | {predictions['final_state']} | "
            f"{predictions['receipt_aware']} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "These are exact results on a hand-authored synthetic corpus. They do not "
            "estimate real-world model behavior or prove that any framework is unsafe. "
            "Mutation-family holdout, receipt ablations, independent label review, and "
            "one real-log adapter remain required before a broader empirical claim.",
            "",
        ]
    )
    return "\n".join(lines)


def write_reports(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "results.json"
    markdown_path = output_dir / "results.md"
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, markdown_path
