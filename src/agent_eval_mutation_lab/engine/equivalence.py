"""Legacy-result equivalence checks for the typed engine."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from agent_eval_mutation_lab.engine.contracts import TaskRecord


def assert_legacy_v2_equivalence(
    records: Sequence[TaskRecord], legacy_report: dict[str, Any]
) -> None:
    """Raise when any engine case result differs from the legacy v2 report."""

    actual = {
        (
            record.evidence_condition,
            record.scorer_id,
            record.case_id,
        ): (
            record.family,
            record.validation.expected,
            record.validation.prediction,
        )
        for record in records
    }
    expected: dict[tuple[str, str, str], tuple[str, object, object]] = {}
    for condition, scorers in legacy_report["conditions"].items():
        for scorer_id, scorer_result in scorers.items():
            for row in scorer_result["cases"]:
                expected[(condition, scorer_id, row["case_id"])] = (
                    row["family"],
                    row["expected"],
                    row["prediction"],
                )
    if actual != expected:
        missing = sorted(expected.keys() - actual.keys())
        extra = sorted(actual.keys() - expected.keys())
        changed = sorted(
            key
            for key in expected.keys() & actual.keys()
            if expected[key] != actual[key]
        )
        raise AssertionError(
            "typed engine diverged from legacy v2 matrix: "
            f"missing={missing}, extra={extra}, changed={changed}"
        )
