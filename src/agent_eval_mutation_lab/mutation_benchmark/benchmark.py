"""Deterministic batch orchestration and evidence-report rendering."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from agent_eval_mutation_lab.mutation_benchmark.contracts import (
    MutantResult,
    MutantStatus,
    MutationManifest,
    MutationPartition,
    MutationSpec,
)
from agent_eval_mutation_lab.mutation_benchmark.runner import (
    DEFAULT_KILL_SELECTORS,
    run_baseline,
    run_mutant,
)


def run_benchmark(
    project_root: Path,
    manifest: MutationManifest,
    *,
    selectors: Sequence[str] = DEFAULT_KILL_SELECTORS,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    """Run a frozen semantic suite against every predeclared mutant."""

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    baseline = run_baseline(
        project_root,
        selectors=selectors,
        timeout_seconds=timeout_seconds,
    )
    if baseline.return_code != 0 or baseline.timed_out:
        raise RuntimeError("baseline semantic suite must pass before mutation scoring")
    results = tuple(
        run_mutant(
            project_root,
            manifest,
            spec,
            selectors=selectors,
            timeout_seconds=timeout_seconds,
        )
        for spec in manifest.mutations
    )
    return benchmark_payload(
        manifest,
        results,
        selectors=selectors,
        timeout_seconds=timeout_seconds,
    )


def benchmark_payload(
    manifest: MutationManifest,
    results: Sequence[MutantResult],
    *,
    selectors: Sequence[str],
    timeout_seconds: float,
) -> dict[str, Any]:
    """Build a timing-free canonical payload from classified results."""

    by_id = {result.mutation_id: result for result in results}
    if len(by_id) != len(results):
        raise ValueError("mutation results must have unique IDs")
    expected_ids = [spec.mutation_id for spec in manifest.mutations]
    if set(by_id) != set(expected_ids):
        raise ValueError("mutation results must exactly cover the manifest")
    ordered_results = [by_id[mutation_id] for mutation_id in expected_ids]
    return {
        "schema_version": 1,
        "benchmark_id": "v2-scorer-semantic-mutation-development",
        "scope": (
            "Predeclared development mutations of the v2 scorer only; "
            "not a held-out estimate."
        ),
        "source": {
            "path": manifest.source_path,
            "sha256": manifest.baseline_source_sha256,
        },
        "test_protocol": {
            "selectors": list(selectors),
            "timeout_seconds": timeout_seconds,
            "one_mutant_per_process": True,
            "ephemeral_snapshot": True,
            "import_origin_verified": True,
            "baseline_passed": True,
        },
        "score_policy": {
            "formula": "killed / (killed + survived + plausibly_equivalent)",
            "equivalent_excluded": True,
            "plausibly_equivalent_counted_as_survived": True,
            "invalid_and_run_error_excluded": True,
        },
        "metrics": summarize_results(ordered_results),
        "partitions": {
            partition.value: summarize_results(
                [result for result in ordered_results if result.partition is partition]
            )
            for partition in MutationPartition
        },
        "mutants": [
            _result_payload(spec, by_id[spec.mutation_id])
            for spec in manifest.mutations
        ],
    }


def summarize_results(results: Sequence[MutantResult]) -> dict[str, Any]:
    """Compute transparent status counts and a conservative mutation score."""

    counts = Counter(result.status for result in results)
    denominator = (
        counts[MutantStatus.KILLED]
        + counts[MutantStatus.SURVIVED]
        + counts[MutantStatus.PLAUSIBLY_EQUIVALENT]
    )
    score = counts[MutantStatus.KILLED] / denominator if denominator else None
    return {
        "catalog_count": len(results),
        "killed": counts[MutantStatus.KILLED],
        "survived": counts[MutantStatus.SURVIVED],
        "equivalent": counts[MutantStatus.EQUIVALENT],
        "plausibly_equivalent": counts[MutantStatus.PLAUSIBLY_EQUIVALENT],
        "invalid": counts[MutantStatus.INVALID],
        "run_error": counts[MutantStatus.RUN_ERROR],
        "score_denominator": denominator,
        "conservative_mutation_score": score,
        "completed_cleanly": (
            counts[MutantStatus.INVALID] == 0 and counts[MutantStatus.RUN_ERROR] == 0
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    """Render the compact reviewer-facing companion to the JSON evidence."""

    metrics = report["metrics"]
    score = metrics["conservative_mutation_score"]
    score_text = "n/a" if score is None else f"{score:.1%}"
    lines = [
        "# V2 scorer semantic mutation benchmark",
        "",
        f"**Scope:** {report['scope']}",
        "",
        f"**Source:** `{report['source']['path']}`",
        "",
        f"**Source SHA-256:** `{report['source']['sha256']}`",
        "",
        "## Result",
        "",
        f"- Conservative mutation score: **{score_text}**",
        f"- Killed: {metrics['killed']}",
        f"- Survived: {metrics['survived']}",
        f"- Plausibly equivalent, conservatively counted as survived: "
        f"{metrics['plausibly_equivalent']}",
        f"- Invalid: {metrics['invalid']}",
        f"- Run errors: {metrics['run_error']}",
        "",
        "The baseline suite passed through the same ephemeral snapshot and import "
        "boundary. Each mutant ran in a separate process. This development catalog "
        "is not presented as held-out evidence.",
        "",
        "## Mutants",
        "",
        "| ID | Rule | Status | Failing tests |",
        "|---|---|---:|---:|",
    ]
    for mutant in report["mutants"]:
        failing_count = len(mutant["test_run"]["failing_test_ids"])
        lines.append(
            f"| `{mutant['mutation_id']}` | {mutant['semantic_rule']} | "
            f"{mutant['status']} | {failing_count} |"
        )
    return "\n".join(lines) + "\n"


def write_reports(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    """Write stable JSON and Markdown mutation evidence."""

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "semantic-mutations.json"
    markdown_path = output_dir / "semantic-mutations.md"
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def _result_payload(spec: MutationSpec, result: MutantResult) -> dict[str, Any]:
    return {
        "mutation_id": result.mutation_id,
        "partition": result.partition.value,
        "operator_id": spec.operator_id,
        "semantic_rule": spec.semantic_rule,
        "expected_semantic_change": spec.expected_semantic_change,
        "activation_case": spec.activation_case,
        "equivalence_assessment": spec.equivalence_assessment.value,
        "status": result.status.value,
        "reason": result.reason,
        "transformed_source_sha256": result.transformed_source_sha256,
        "transformed_diff_sha256": result.transformed_diff_sha256,
        "test_run": {
            "return_code": result.test_run.return_code,
            "timed_out": result.test_run.timed_out,
            "test_session_started": result.test_run.test_session_started,
            "import_origin_verified": result.test_run.import_origin_verified,
            "failing_test_ids": list(result.test_run.failing_test_ids),
            "error_code": result.test_run.error_code,
        },
    }
