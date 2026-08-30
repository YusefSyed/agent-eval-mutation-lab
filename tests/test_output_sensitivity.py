from __future__ import annotations

import itertools
import json
from dataclasses import asdict, replace
from fractions import Fraction

import pytest

from agent_eval_mutation_lab.model_study.sensitivity.bounds import (
    Comparison,
    Estimand,
    GroupPlan,
    Interval,
    Outcome,
    audit_comparison,
    evaluate_completion,
    exact_json,
)
from agent_eval_mutation_lab.model_study.sensitivity.io import (
    comparison_from_payload,
    parse_json,
)


def comparison(values: tuple[int | None, ...]) -> Comparison:
    groups = (
        GroupPlan("small", Fraction(1, 3), 1, 1, ("L0",), ("R0",)),
        GroupPlan("large", Fraction(2, 3), 2, 2, ("L1", "L2"), ("R1", "R2")),
    )
    identities = [(arm, index) for arm in ("L", "R") for index in range(3)]
    outcomes = tuple(
        Outcome(
            f"{arm}{index}",
            arm,
            "small" if index == 0 else "large",
            value,
            "invalid" if value is None else None,
        )
        for (arm, index), value in zip(identities, values, strict=True)
    )
    return Comparison("L", "R", groups, outcomes)


@pytest.mark.parametrize(
    "weights,unit_weights",
    [
        ((Fraction(1, 3), Fraction(2, 3)), (Fraction(1, 3),) * 3),
        (
            (Fraction(4, 5), Fraction(1, 5)),
            (Fraction(4, 5), Fraction(1, 10), Fraction(1, 10)),
        ),
    ],
)
def test_exact_bounds_match_every_completion_of_every_small_observation_pattern(
    weights, unit_weights
):
    # Independent oracle: enumerate all 4,096 complete/pattern combinations,
    # directly sum per-trial weighted values, and compare extrema and witnesses.
    for values in itertools.product((0, 1, None), repeat=6):
        contract = comparison(values)
        contract = replace(
            contract,
            groups=tuple(
                replace(group, weight=weight)
                for group, weight in zip(contract.groups, weights, strict=True)
            ),
        )
        missing = [index for index, value in enumerate(values) if value is None]
        attainable = []
        arm_means = [[], []]
        for assignment in itertools.product((0, 1), repeat=len(missing)):
            completed = list(values)
            for index, value in zip(missing, assignment, strict=True):
                completed[index] = value
            # Direct per-trial dot products, independent of production cell counts.
            left = sum(
                (
                    weight * value
                    for weight, value in zip(unit_weights, completed[:3], strict=True)
                ),
                Fraction(),
            )
            right = sum(
                (
                    weight * value
                    for weight, value in zip(unit_weights, completed[3:], strict=True)
                ),
                Fraction(),
            )
            arm_means[0].append(left)
            arm_means[1].append(right)
            attainable.append(left - right)
        report = audit_comparison(contract, Estimand.LATENT)
        assert report.difference == Interval(min(attainable), max(attainable))
        assert report.left_mean == Interval(min(arm_means[0]), max(arm_means[0]))
        assert report.right_mean == Interval(min(arm_means[1]), max(arm_means[1]))
        for witness, bound in (
            (report.lower_witness, min(attainable)),
            (report.upper_witness, max(attainable)),
        ):
            assert witness is not None
            assert evaluate_completion(contract, dict(witness.assignments)) == witness
            assert witness.difference == bound


def test_nonpooled_rational_weights_have_attained_sharp_bounds():
    contract = comparison((1, 0, None, 0, 1, None))
    contract = replace(
        contract,
        groups=(
            replace(contract.groups[0], weight=Fraction(4, 5)),
            replace(contract.groups[1], weight=Fraction(1, 5)),
        ),
    )
    report = audit_comparison(contract, Estimand.LATENT)
    assert report.left_mean == Interval(Fraction(4, 5), Fraction(9, 10))
    assert report.right_mean == Interval(Fraction(1, 10), Fraction(1, 5))
    assert report.difference == Interval(Fraction(3, 5), Fraction(4, 5))
    assert report.lower_witness.difference == Fraction(3, 5)
    assert report.upper_witness.difference == Fraction(4, 5)


def test_hand_calculated_selection_reversal_does_not_repair_the_missing_outputs():
    left = tuple(
        Outcome(f"L{i}", "L", "all", 1 if i < 2 else None, None if i < 2 else "invalid")
        for i in range(10)
    )
    right = tuple(Outcome(f"R{i}", "R", "all", int(i < 8)) for i in range(10))
    group = GroupPlan(
        "all",
        Fraction(1),
        10,
        10,
        tuple(o.trial_id for o in left),
        tuple(o.trial_id for o in right),
    )
    contract = Comparison("L", "R", (group,), left + right)
    valid = audit_comparison(contract, Estimand.VALID_ONLY)
    pipeline = audit_comparison(contract, Estimand.PIPELINE)
    latent = audit_comparison(contract, Estimand.LATENT)
    assert valid.difference == Interval(Fraction(1, 5), Fraction(1, 5))
    assert pipeline.difference == Interval(Fraction(-3, 5), Fraction(-3, 5))
    assert latent.difference == Interval(Fraction(-3, 5), Fraction(1, 5))
    assert latent.lower_witness.difference < 0 < latent.upper_witness.difference
    assert valid.cells[0].denominator == 2
    assert pipeline.cells[0].denominator == 10


def test_missing_positive_weight_group_is_undefined_without_renormalization():
    contract = comparison((None, 1, 1, 1, 1, 1))
    report = audit_comparison(contract, Estimand.VALID_ONLY)
    assert report.left_mean is None
    assert report.right_mean == Interval(Fraction(1), Fraction(1))
    assert report.difference is None
    assert audit_comparison(contract, Estimand.PIPELINE).difference == Interval(
        Fraction(-1, 3), Fraction(-1, 3)
    )


def test_group_roster_and_outcome_order_do_not_change_certificate_bytes():
    contract = comparison((1, None, 0, None, 0, 1))
    reordered = replace(
        contract,
        groups=tuple(
            replace(
                g,
                left_trial_ids=tuple(reversed(g.left_trial_ids)),
                right_trial_ids=tuple(reversed(g.right_trial_ids)),
            )
            for g in reversed(contract.groups)
        ),
        outcomes=tuple(reversed(contract.outcomes)),
    )
    for estimand in Estimand:
        first = json.dumps(
            audit_comparison(contract, estimand).payload(), sort_keys=True
        )
        second = json.dumps(
            audit_comparison(reordered, estimand).payload(), sort_keys=True
        )
        assert first == second


@pytest.mark.parametrize(
    "bad", [True, False, 0.0, 1.0, float("nan"), float("inf"), -1, 2]
)
def test_reject_nonbinary_or_nonfinite_outcomes(bad):
    contract = comparison((1, 0, 1, 0, 1, 0))
    with pytest.raises(ValueError, match="integer 0 or 1"):
        replace(
            contract,
            outcomes=(replace(contract.outcomes[0], value=bad), *contract.outcomes[1:]),
        )


@pytest.mark.parametrize(
    "bad",
    [
        True,
        1,
        0.5,
        float("nan"),
        float("inf"),
        Fraction(0),
        Fraction(-1),
        Fraction(1, 2),
    ],
)
def test_reject_invalid_weights(bad):
    contract = comparison((1, 0, 1, 0, 1, 0))
    with pytest.raises(ValueError):
        replace(
            contract,
            groups=(replace(contract.groups[0], weight=bad), contract.groups[1]),
        )


def test_reject_incomplete_duplicate_or_misclassified_manifests():
    contract = comparison((1, None, 1, 0, 1, 0))
    invalid = [
        {"outcomes": contract.outcomes[:-1]},
        {"outcomes": (*contract.outcomes, contract.outcomes[0])},
        {"groups": (contract.groups[0], contract.groups[0])},
        {
            "groups": (
                replace(contract.groups[0], left_planned_count=True),
                contract.groups[1],
            )
        },
        {
            "groups": (
                replace(contract.groups[0], left_planned_count=2),
                contract.groups[1],
            )
        },
        {
            "groups": (
                contract.groups[0],
                replace(contract.groups[1], left_trial_ids=("L0", "L2")),
            )
        },
        {"outcomes": (replace(contract.outcomes[0], arm="R"), *contract.outcomes[1:])},
        {
            "outcomes": (
                contract.outcomes[0],
                replace(contract.outcomes[1], missing_reason=None),
                *contract.outcomes[2:],
            )
        },
        {
            "outcomes": (
                replace(contract.outcomes[0], missing_reason="invalid"),
                *contract.outcomes[1:],
            )
        },
    ]
    for changes in invalid:
        with pytest.raises(ValueError):
            replace(contract, **changes)


def test_certificate_must_assign_exactly_missing_trials_and_cannot_change_observed():
    contract = comparison((1, None, 1, 0, 1, 0))
    for assignments in ({}, {"L1": True}, {"L1": 1, "L0": 0}, {"L1": float("nan")}):
        with pytest.raises(ValueError):
            evaluate_completion(contract, assignments)
    with pytest.raises(ValueError, match="explicit"):
        audit_comparison(contract, "latent_semantic_correctness")


def test_strict_json_roundtrip_rejects_ambiguous_numbers_keys_and_extra_fields():
    contract = comparison((1, None, 1, 0, 1, 0))
    payload = {"schema_version": 1, **exact_json(asdict(contract))}
    assert comparison_from_payload(payload) == contract
    for text in (
        '{"a": 1, "a": 2}',
        '{"weight": NaN}',
        '{"weight": Infinity}',
        '{"weight": 1e999}',
    ):
        with pytest.raises(ValueError):
            parse_json(text)
    for field, value in (("schema_version", True), ("extra", "unexpected")):
        with pytest.raises(ValueError):
            comparison_from_payload({**payload, field: value})
    payload["groups"][0]["weight"]["numerator"] = True
    with pytest.raises(ValueError):
        comparison_from_payload(payload)
