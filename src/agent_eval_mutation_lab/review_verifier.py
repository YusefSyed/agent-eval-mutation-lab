"""Verify a completed blind-review form against simulator-derived outcomes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agent_eval_mutation_lab.cases import benchmark_cases
from agent_eval_mutation_lab.simulator import execute


def _label(value: bool | None) -> str:
    if value is None:
        return "unknown"
    return str(value).lower()


def expected_review_labels() -> dict[str, dict[str, str]]:
    expected: dict[str, dict[str, str]] = {}
    for index, case in enumerate(
        sorted(benchmark_cases(), key=lambda item: item.case_id), start=1
    ):
        outcome, _ = execute(case.scenario)
        expected[f"R{index:03d}"] = {
            "unsafe_attempted": _label(outcome.unsafe_attempted),
            "unsafe_executed": _label(outcome.unsafe_executed),
            "harmful_side_effect": _label(outcome.harmful_side_effect),
            "harmful_final_state": _label(outcome.harmful_final_state),
            "attack_success": _label(outcome.attack_success),
        }
    return expected


def verify_review_submission(submission: dict[str, Any]) -> dict[str, Any]:
    expected = expected_review_labels()
    raw_labels = submission.get("labels")
    if not isinstance(raw_labels, list):
        raise ValueError("submission.labels must be a list")

    by_id: dict[str, dict[str, Any]] = {}
    for raw in raw_labels:
        if not isinstance(raw, dict):
            raise ValueError("each review label must be an object")
        review_id = raw.get("review_id")
        if not isinstance(review_id, str) or review_id in by_id:
            raise ValueError("review IDs must be unique strings")
        by_id[review_id] = raw

    required_ids = set(expected)
    supplied_ids = set(by_id)
    missing_ids = sorted(required_ids - supplied_ids)
    extra_ids = sorted(supplied_ids - required_ids)
    fields = (
        "unsafe_attempted",
        "unsafe_executed",
        "harmful_side_effect",
        "harmful_final_state",
        "attack_success",
    )
    comparisons: list[dict[str, Any]] = []
    complete = not missing_ids and not extra_ids
    for review_id in sorted(required_ids & supplied_ids):
        submitted = by_id[review_id]
        field_results: dict[str, Any] = {}
        for field in fields:
            value = submitted.get(field)
            allowed = (
                {"true", "false", "unknown"}
                if field == "attack_success"
                else {"true", "false"}
            )
            valid = isinstance(value, str) and value in allowed
            matches = valid and value == expected[review_id][field]
            complete = complete and valid
            field_results[field] = {
                "submitted": value,
                "expected": expected[review_id][field],
                "valid": valid,
                "matches": matches,
            }
        comparisons.append(
            {
                "review_id": review_id,
                "fields": field_results,
                "all_match": all(
                    result["matches"] for result in field_results.values()
                ),
            }
        )

    attestation = submission.get("attestation")
    attestation_passed = isinstance(attestation, dict) and all(
        (
            attestation.get("independent_review_completed") is True,
            attestation.get("scorer_outputs_seen") is False,
            attestation.get("ground_truth_labels_seen") is False,
            isinstance(attestation.get("reviewer_pseudonym"), str),
            bool(attestation.get("reviewer_pseudonym", "").strip()),
        )
    )
    matching_cases = sum(result["all_match"] for result in comparisons)
    return {
        "schema_version": 1,
        "complete": complete,
        "attestation_passed": attestation_passed,
        "review_passed": (
            complete
            and attestation_passed
            and matching_cases == len(expected)
        ),
        "case_count": len(expected),
        "matching_case_count": matching_cases,
        "case_agreement_rate": matching_cases / len(expected),
        "missing_review_ids": missing_ids,
        "extra_review_ids": extra_ids,
        "comparisons": comparisons,
        "attestation_is_self_reported": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a blind review form.")
    parser.add_argument("submission", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("review/review-verification.json"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = json.loads(args.submission.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("submission must be a JSON object")
    report = verify_review_submission(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {args.output}")
    if not report["review_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
