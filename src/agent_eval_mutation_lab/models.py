"""Typed benchmark contracts.

Scorers receive :class:`ObservedTrajectory`, which deliberately excludes actual
execution fields and expected labels. Ground truth is derived separately from
the scenario's private execution record.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ActionStatus(StrEnum):
    DENIED = "denied"
    FAILED = "failed"
    SUCCESS = "success"
    TIMED_OUT = "timed_out"
    PARTIAL = "partial"


class EffectOperation(StrEnum):
    ADD = "add"
    SET = "set"


class MutationExpectation(StrEnum):
    LABEL_CHANGING = "label_changing"
    LABEL_PRESERVING = "label_preserving"
    EVIDENCE_WITHHOLDING = "evidence_withholding"


type Prediction = bool | None


@dataclass(frozen=True)
class Effect:
    key: str
    operation: EffectOperation
    value: int

    def apply(self, state: dict[str, int]) -> None:
        if self.operation is EffectOperation.ADD:
            state[self.key] = state.get(self.key, 0) + self.value
        else:
            state[self.key] = self.value


@dataclass(frozen=True)
class Receipt:
    """Evidence visible to a scorer, not authoritative ground truth."""

    status: ActionStatus
    effects: tuple[Effect, ...] = ()


@dataclass(frozen=True)
class Action:
    action_id: str
    tool: str
    prohibited: bool
    actual_status: ActionStatus
    actual_effects: tuple[Effect, ...] = ()
    receipt: Receipt | None = None

    def __post_init__(self) -> None:
        if self.actual_status in {
            ActionStatus.DENIED,
            ActionStatus.FAILED,
            ActionStatus.TIMED_OUT,
        } and self.actual_effects:
            raise ValueError(
                f"{self.action_id}: non-executing status cannot have actual effects"
            )


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    family: str
    initial_state: tuple[tuple[str, int], ...]
    harm_key: str
    harm_threshold: int
    actions: tuple[Action, ...]

    def __post_init__(self) -> None:
        action_ids = [action.action_id for action in self.actions]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError(f"{self.scenario_id}: action IDs must be unique")
        if self.harm_threshold < 1:
            raise ValueError("harm_threshold must be positive")


@dataclass(frozen=True)
class ObservedAction:
    action_id: str
    tool: str
    prohibited: bool
    receipt: Receipt | None


@dataclass(frozen=True)
class ObservedTrajectory:
    scenario_id: str
    initial_state: tuple[tuple[str, int], ...]
    final_state: tuple[tuple[str, int], ...]
    harm_key: str
    harm_threshold: int
    actions: tuple[ObservedAction, ...]


@dataclass(frozen=True)
class Outcome:
    unsafe_attempted: bool
    unsafe_executed: bool
    harmful_side_effect: bool
    harmful_final_state: bool
    attack_success: Prediction


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    scenario: Scenario
    source: str
    base_case_id: str | None = None
    mutation: str | None = None
    mutation_expectation: MutationExpectation | None = None


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    family: str
    source: str
    base_case_id: str | None
    mutation: str | None
    mutation_expectation: MutationExpectation | None
    expected: Prediction
    predictions: tuple[tuple[str, Prediction], ...]
