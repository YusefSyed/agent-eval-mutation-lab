from __future__ import annotations

import json
from pathlib import Path

from agent_eval_mutation_lab.mutation_benchmark.benchmark import (
    benchmark_payload,
    render_markdown,
    summarize_results,
    write_reports,
)
from agent_eval_mutation_lab.mutation_benchmark.contracts import (
    MutantResult,
    MutantStatus,
    MutationManifest,
    MutationPartition,
    MutationSpec,
)
from agent_eval_mutation_lab.mutation_benchmark.contracts import (
    TestRunResult as MutationTestRunResult,
)


def _result(mutation_id: str, status: MutantStatus) -> MutantResult:
    return MutantResult(
        mutation_id=mutation_id,
        partition=MutationPartition.DEVELOPMENT,
        status=status,
        baseline_source_sha256="a" * 64,
        transformed_source_sha256="b" * 64,
        transformed_diff_sha256="c" * 64,
        test_run=MutationTestRunResult(
            return_code=1 if status is MutantStatus.KILLED else 0,
            timed_out=False,
            test_session_started=True,
            import_origin_verified=True,
            failing_test_ids=("tests.test_semantics::test_contract",)
            if status is MutantStatus.KILLED
            else (),
            error_code=None,
        ),
        reason="fixture",
    )


def _spec(mutation_id: str) -> MutationSpec:
    return MutationSpec(
        mutation_id=mutation_id,
        function_name="score",
        node_type="Return",
        expected_segment_sha256="d" * 64,
        replacement="return None",
        semantic_rule="semantic rule",
        expected_semantic_change="semantic change",
        activation_case="activation case",
    )


def test_conservative_score_counts_plausible_equivalence_as_survived() -> None:
    metrics = summarize_results(
        (
            _result("killed", MutantStatus.KILLED),
            _result("survived", MutantStatus.SURVIVED),
            _result("plausible", MutantStatus.PLAUSIBLY_EQUIVALENT),
            _result("equivalent", MutantStatus.EQUIVALENT),
            _result("invalid", MutantStatus.INVALID),
        )
    )
    assert metrics["score_denominator"] == 3
    assert metrics["conservative_mutation_score"] == 1 / 3
    assert metrics["completed_cleanly"] is False


def test_report_round_trip_is_deterministic(tmp_path: Path) -> None:
    specs = (_spec("a"), _spec("b"))
    manifest = MutationManifest(
        schema_version=1,
        source_path="src/pkg/scorer.py",
        baseline_source_sha256="a" * 64,
        mutations=specs,
    )
    report = benchmark_payload(
        manifest,
        (
            _result("b", MutantStatus.SURVIVED),
            _result("a", MutantStatus.KILLED),
        ),
        selectors=("tests/test_semantics.py",),
        timeout_seconds=10.0,
    )
    json_path, markdown_path = write_reports(report, tmp_path)
    assert json.loads(json_path.read_text(encoding="utf-8")) == report
    assert markdown_path.read_text(encoding="utf-8") == render_markdown(report)
    assert [item["mutation_id"] for item in report["mutants"]] == ["a", "b"]
