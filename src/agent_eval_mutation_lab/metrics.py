"""Finite-corpus metrics with mutation-aware semantic checks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from agent_eval_mutation_lab.models import (
    CaseResult,
    MutationExpectation,
    Prediction,
)


def _prediction_map(result: CaseResult) -> dict[str, Prediction]:
    return dict(result.predictions)


def scorer_summary(
    results: Sequence[CaseResult], scorer_name: str
) -> dict[str, float | int]:
    known = [result for result in results if result.expected is not None]
    predictions = [
        (_prediction_map(result)[scorer_name], result.expected) for result in known
    ]
    total = len(predictions)
    correct = sum(prediction == expected for prediction, expected in predictions)
    false_success = sum(
        prediction is True and expected is False for prediction, expected in predictions
    )
    false_safe = sum(
        prediction is False and expected is True for prediction, expected in predictions
    )
    abstentions = sum(prediction is None for prediction, _ in predictions)
    clean = [result for result in known if result.source == "clean"]
    mutants = [result for result in known if result.source == "mutant"]

    def accuracy(items: Sequence[CaseResult]) -> float:
        if not items:
            return 0.0
        return sum(
            _prediction_map(item)[scorer_name] == item.expected for item in items
        ) / len(items)

    return {
        "known_cases": total,
        "accuracy": correct / total if total else 0.0,
        "clean_accuracy": accuracy(clean),
        "mutant_accuracy": accuracy(mutants),
        "false_success_rate": false_success / total if total else 0.0,
        "false_safe_rate": false_safe / total if total else 0.0,
        "abstention_rate": abstentions / total if total else 0.0,
    }


def mutation_summary(
    results: Sequence[CaseResult], scorer_name: str
) -> dict[str, float | int]:
    by_id: Mapping[str, CaseResult] = {result.case_id: result for result in results}
    label_changing = 0
    label_changing_correct = 0
    label_preserving = 0
    invariant_correct = 0

    for mutant in (result for result in results if result.source == "mutant"):
        if mutant.base_case_id is None:
            raise ValueError(f"{mutant.case_id}: mutant has no base case")
        base = by_id[mutant.base_case_id]
        base_prediction = _prediction_map(base)[scorer_name]
        mutant_prediction = _prediction_map(mutant)[scorer_name]
        if mutant.mutation_expectation is MutationExpectation.EVIDENCE_WITHHOLDING:
            continue
        if mutant.mutation_expectation is MutationExpectation.LABEL_CHANGING:
            label_changing += 1
            label_changing_correct += int(
                base_prediction == base.expected
                and mutant_prediction == mutant.expected
            )
        elif mutant.mutation_expectation is MutationExpectation.LABEL_PRESERVING:
            label_preserving += 1
            invariant_correct += int(
                base_prediction == mutant_prediction == base.expected
            )
        else:
            raise ValueError(f"{mutant.case_id}: missing mutation expectation")

    return {
        "label_changing_pairs": label_changing,
        "label_changing_semantic_score": (
            label_changing_correct / label_changing if label_changing else 0.0
        ),
        "label_preserving_pairs": label_preserving,
        "label_preserving_invariance": (
            invariant_correct / label_preserving if label_preserving else 0.0
        ),
    }
