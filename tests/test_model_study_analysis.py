from __future__ import annotations

import pytest

from agent_eval_mutation_lab.model_study.analysis import (
    BOOTSTRAP_REPLICATES,
    AnalyzedTrial,
    analyze_trials,
    render_markdown,
)
from agent_eval_mutation_lab.model_study.contracts import StudyArm, TerminalStatus

_FAMILIES = ("a", "b", "c", "d", "e")


def _trial(
    *,
    model: str,
    arm: StudyArm,
    family: str,
    seed: int = 1,
    prediction: bool | None = False,
    expected: bool | None = False,
    status: TerminalStatus = TerminalStatus.COMPLETE,
) -> AnalyzedTrial:
    valid = status is TerminalStatus.COMPLETE
    return AnalyzedTrial(
        trial_id=f"{model}-{arm.value}-{family}-{seed}",
        input_ref=f"input-{family}",
        family=family,
        model=model,
        arm=arm,
        seed=seed,
        status=status,
        prediction=prediction if valid else None,
        expected=expected,
        probability_harm=0.05 if valid else None,
        probability_no_harm=0.9 if valid else None,
        probability_unknown=0.05 if valid else None,
    )


def _corpus(*, evidence_prediction: bool | None = False) -> list[AnalyzedTrial]:
    return [
        _trial(
            model=model,
            arm=arm,
            family=family,
            prediction=(True if arm is StudyArm.DIRECT else evidence_prediction),
            expected=False,
        )
        for model in ("model-a", "model-b")
        for arm in StudyArm
        for family in _FAMILIES
    ]


def test_passing_gate_and_json_markdown_report() -> None:
    report = analyze_trials(_corpus())

    assert report.gates.passed
    assert report.paired_evidence.direct_minus_evidence_first == 1.0
    assert len(report.paired_evidence.bootstrap_differences) == BOOTSTRAP_REPLICATES
    assert report.payload()["schema_version"] == 1
    assert "finite-corpus composition sensitivity" in render_markdown(report)


def test_mixed_failing_gate_includes_invalidity_and_coverage_loss() -> None:
    records = _corpus(evidence_prediction=None)
    records[0] = _trial(
        model="model-a",
        arm=StudyArm.DIRECT,
        family="a",
        status=TerminalStatus.INVALID_RESPONSE,
    )
    report = analyze_trials(records)

    assert not report.gates.passed
    assert not report.gates.checks["validity_at_least_95_percent_each_model_arm"]
    assert not report.gates.checks["coverage_drop_at_most_10pp_each_model"]
    assert report.per_model_arm["model-a/direct"].invalid_count == 1


def test_brier_unknown_metrics_and_seed_disagreement() -> None:
    records = _corpus()
    records.extend(
        [
            _trial(
                model="model-a",
                arm=StudyArm.DIRECT,
                family="a",
                seed=2,
                prediction=None,
                expected=False,
            ),
            _trial(
                model="model-a",
                arm=StudyArm.EVIDENCE_FIRST,
                family="a",
                seed=2,
                prediction=None,
                expected=False,
            ),
        ]
    )
    report = analyze_trials(records)
    summary = report.per_model_arm["model-a/direct"]

    assert summary.multiclass_brier is not None
    assert summary.seed_disagreement == 1.0
    assert summary.unnecessary_abstention > 0


def test_bootstrap_is_deterministic() -> None:
    first = analyze_trials(_corpus()).paired_evidence.bootstrap_differences
    second = analyze_trials(_corpus()).paired_evidence.bootstrap_differences

    assert first == second


def test_empty_and_invalid_inputs_are_rejected() -> None:
    with pytest.raises(ValueError, match="at least one"):
        analyze_trials(())
    with pytest.raises(ValueError, match="probabilities must sum"):
        AnalyzedTrial(
            trial_id="trial",
            input_ref="input",
            family="family",
            model="model",
            arm=StudyArm.DIRECT,
            seed=0,
            status=TerminalStatus.COMPLETE,
            prediction=True,
            expected=True,
            probability_harm=0.4,
            probability_no_harm=0.4,
            probability_unknown=0.4,
        )
