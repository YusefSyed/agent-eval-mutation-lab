"""Exact interval hulls for finite binary outcomes with unrestricted missingness.

These are logical completion bounds, not confidence or causal intervals. Positive
group weights and independent binary completions make both endpoints attainable.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum
from fractions import Fraction


class Estimand(StrEnum):
    PIPELINE = "pipeline_success_accuracy"
    VALID_ONLY = "valid_only_accuracy"
    LATENT = "latent_semantic_correctness"


@dataclass(frozen=True, slots=True)
class Outcome:
    trial_id: str
    arm: str
    group: str
    value: int | None
    missing_reason: str | None = None


@dataclass(frozen=True, slots=True)
class GroupPlan:
    group: str
    weight: Fraction
    left_planned_count: int
    right_planned_count: int
    left_trial_ids: tuple[str, ...]
    right_trial_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Comparison:
    left_arm: str
    right_arm: str
    groups: tuple[GroupPlan, ...]
    outcomes: tuple[Outcome, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.left_arm, str)
            or not isinstance(self.right_arm, str)
            or not self.left_arm.strip()
            or not self.right_arm.strip()
            or self.left_arm == self.right_arm
        ):
            raise ValueError("two distinct nonempty arms are required")
        if not self.groups or len({g.group for g in self.groups}) != len(self.groups):
            raise ValueError("group manifest must be nonempty and unique")
        expected: dict[str, tuple[str, str]] = {}
        for group in self.groups:
            if (
                not isinstance(group.group, str)
                or not group.group.strip()
                or type(group.weight) is not Fraction
            ):
                raise ValueError("group names and exact Fraction weights are required")
            if group.weight <= 0:
                raise ValueError("weights must be strictly positive")
            for arm, count, ids in (
                (self.left_arm, group.left_planned_count, group.left_trial_ids),
                (self.right_arm, group.right_planned_count, group.right_trial_ids),
            ):
                if type(count) is not int or count <= 0 or count != len(ids):
                    raise ValueError("planned group counts must match positive rosters")
                for trial_id in ids:
                    if not isinstance(trial_id, str) or not trial_id:
                        raise ValueError("trial IDs must be nonempty strings")
                    if trial_id in expected:
                        raise ValueError("duplicate trial ID in planned manifest")
                    expected[trial_id] = (arm, group.group)
        if sum((g.weight for g in self.groups), Fraction()) != 1:
            raise ValueError("group weights must sum exactly to one")
        seen: set[str] = set()
        for outcome in self.outcomes:
            if outcome.trial_id in seen:
                raise ValueError("duplicate outcome trial ID")
            seen.add(outcome.trial_id)
            if expected.get(outcome.trial_id) != (outcome.arm, outcome.group):
                raise ValueError("outcome identity disagrees with the planned manifest")
            if outcome.value is None:
                if (
                    not isinstance(outcome.missing_reason, str)
                    or not outcome.missing_reason.strip()
                ):
                    raise ValueError("missing outcomes require an explicit reason")
            elif type(outcome.value) is not int or outcome.value not in (0, 1):
                raise ValueError("observed outcomes must be integer 0 or 1, not bool")
            elif outcome.missing_reason is not None:
                raise ValueError("observed outcomes cannot have a missing reason")
        if seen != set(expected):
            raise ValueError("outcomes must cover every planned trial explicitly")


@dataclass(frozen=True, slots=True)
class Interval:
    lower: Fraction
    upper: Fraction


@dataclass(frozen=True, slots=True)
class Cell:
    arm: str
    group: str
    weight: Fraction
    planned: int
    observed: int
    successes: int
    missing: int
    missing_reasons: tuple[tuple[str, int], ...]
    denominator: int
    interval: Interval | None


@dataclass(frozen=True, slots=True)
class Witness:
    assignments: tuple[tuple[str, int], ...]
    left_mean: Fraction
    right_mean: Fraction
    difference: Fraction


@dataclass(frozen=True, slots=True)
class SensitivityReport:
    estimand: Estimand
    left_arm: str
    right_arm: str
    cells: tuple[Cell, ...]
    left_mean: Interval | None
    right_mean: Interval | None
    difference: Interval | None
    lower_witness: Witness | None
    upper_witness: Witness | None
    warnings: tuple[str, ...]

    def payload(self) -> dict[str, object]:
        result = asdict(self)
        return {key: exact_json(value) for key, value in result.items()}


def exact_json(value: object) -> object:
    """Serialize every rational as integers; never round a certificate."""

    if isinstance(value, Fraction):
        return {"numerator": value.numerator, "denominator": value.denominator}
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {key: exact_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [exact_json(item) for item in value]
    return value


def evaluate_completion(
    comparison: Comparison, assignments: Mapping[str, int]
) -> Witness:
    """Independently evaluate a fully specified binary completion certificate."""

    missing = {o.trial_id for o in comparison.outcomes if o.value is None}
    if set(assignments) != missing:
        raise ValueError("certificate must assign every and only missing trial")
    if any(type(v) is not int or v not in (0, 1) for v in assignments.values()):
        raise ValueError("certificate assignments must be integer zero or one")
    totals = {comparison.left_arm: Fraction(), comparison.right_arm: Fraction()}
    for group in comparison.groups:
        for arm in totals:
            records = tuple(
                o
                for o in comparison.outcomes
                if o.arm == arm and o.group == group.group
            )
            values = (
                o.value if o.value is not None else assignments[o.trial_id]
                for o in records
            )
            totals[arm] += group.weight * Fraction(sum(values), len(records))
    left, right = totals[comparison.left_arm], totals[comparison.right_arm]
    return Witness(tuple(sorted(assignments.items())), left, right, left - right)


def audit_comparison(comparison: Comparison, estimand: Estimand) -> SensitivityReport:
    """Apply the caller's explicit outcome policy; never repair a missing output."""

    if not isinstance(estimand, Estimand):
        raise ValueError("an explicit supported Estimand is required")
    cells = []
    for group in sorted(comparison.groups, key=lambda g: g.group):
        for arm in (comparison.left_arm, comparison.right_arm):
            records = tuple(
                o
                for o in comparison.outcomes
                if o.arm == arm and o.group == group.group
            )
            observed = tuple(o for o in records if o.value is not None)
            successes = sum(o.value for o in observed if o.value is not None)
            missing = len(records) - len(observed)
            denominator = (
                len(observed) if estimand is Estimand.VALID_ONLY else len(records)
            )
            interval = None
            if denominator:
                lower = Fraction(successes, denominator)
                upper = lower + (
                    Fraction(missing, denominator) if estimand is Estimand.LATENT else 0
                )
                interval = Interval(lower, upper)
            reasons = Counter(o.missing_reason for o in records if o.missing_reason)
            cells.append(
                Cell(
                    arm,
                    group.group,
                    group.weight,
                    len(records),
                    len(observed),
                    successes,
                    missing,
                    tuple(sorted(reasons.items())),
                    denominator,
                    interval,
                )
            )
    left = _weighted_mean(cells, comparison.left_arm)
    right = _weighted_mean(cells, comparison.right_arm)
    difference = (
        Interval(left.lower - right.upper, left.upper - right.lower)
        if left is not None and right is not None
        else None
    )
    lower_witness = upper_witness = None
    if estimand is Estimand.LATENT:
        lower_witness = evaluate_completion(
            comparison,
            {
                o.trial_id: int(o.arm == comparison.right_arm)
                for o in comparison.outcomes
                if o.value is None
            },
        )
        upper_witness = evaluate_completion(
            comparison,
            {
                o.trial_id: int(o.arm == comparison.left_arm)
                for o in comparison.outcomes
                if o.value is None
            },
        )
        if difference != Interval(lower_witness.difference, upper_witness.difference):
            raise AssertionError("completion witnesses do not attain claimed bounds")
    warnings: tuple[str, ...] = {
        Estimand.PIPELINE: (
            "Invalid/missing output is failure by policy; this is pipeline success, "
            "not latent semantic correctness.",
        ),
        Estimand.VALID_ONLY: (
            "Conditional on valid outputs; differential selection can reverse "
            "comparisons. No missing group is dropped or reweighted.",
        ),
        Estimand.LATENT: (
            "Hypothetical unrestricted binary completions; sharp interval hull only, "
            "not a repaired score, confidence interval, or causal effect.",
        ),
    }[estimand]
    if difference is None:
        warnings += (
            "Comparison undefined: a positive-weight group has no observed outcome.",
        )
    return SensitivityReport(
        estimand,
        comparison.left_arm,
        comparison.right_arm,
        tuple(cells),
        left,
        right,
        difference,
        lower_witness,
        upper_witness,
        warnings,
    )


def _weighted_mean(cells: list[Cell], arm: str) -> Interval | None:
    selected = [cell for cell in cells if cell.arm == arm]
    if any(cell.interval is None for cell in selected):
        return None
    return Interval(
        sum(
            (cell.weight * cell.interval.lower for cell in selected if cell.interval),
            Fraction(),
        ),
        sum(
            (cell.weight * cell.interval.upper for cell in selected if cell.interval),
            Fraction(),
        ),
    )
