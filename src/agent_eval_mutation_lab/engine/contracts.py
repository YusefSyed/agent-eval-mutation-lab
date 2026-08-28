"""Immutable public contracts for deterministic evaluation runs.

The scorer-visible types in this module are deliberately distinct from the
simulator models. Oracle truth is stored beside, never inside, the worker task.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from agent_eval_mutation_lab.models import (
    ActionStatus,
    EffectOperation,
    Prediction,
)


class PluginKind(StrEnum):
    SCORER = "scorer"
    EVIDENCE_TRANSFORM = "evidence_transform"


@dataclass(frozen=True, slots=True, kw_only=True)
class PluginDescriptor:
    plugin_id: str
    version: str
    kind: PluginKind
    implementation_digest: str


@dataclass(frozen=True, slots=True, kw_only=True)
class VisibleEffect:
    key: str
    operation: EffectOperation
    value: int


@dataclass(frozen=True, slots=True, kw_only=True)
class VisibleReceipt:
    status: ActionStatus
    effects: tuple[VisibleEffect, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class VisibleAction:
    action_id: str
    tool: str
    prohibited: bool
    receipt: VisibleReceipt | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ScorerInput:
    """Whitelist projection passed to scorers.

    No actual execution status, actual effects, expected label, outcome, store,
    or full benchmark case can be reached through this object.
    """

    scenario_id: str
    initial_state: tuple[tuple[str, int], ...]
    final_state: tuple[tuple[str, int], ...]
    harm_key: str
    harm_threshold: int
    actions: tuple[VisibleAction, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class OracleTruth:
    attack_success: Prediction


@dataclass(frozen=True, slots=True, kw_only=True)
class RunSpec:
    schema_version: int
    corpus_id: str
    scorer_ids: tuple[str, ...]
    evidence_conditions: tuple[str, ...]
    seed: int
    source_digest: str
    frozen_lock_digest: str


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskContext:
    task_key: str
    ordinal: int
    seed: int


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkerTask:
    """The complete object available to a scorer worker."""

    context: TaskContext
    scorer_id: str
    scorer_input: ScorerInput


@dataclass(frozen=True, slots=True, kw_only=True)
class PlannedTask:
    """Coordinator-owned task containing a worker projection and oracle truth."""

    worker: WorkerTask
    case_id: str
    family: str
    evidence_condition: str
    oracle: OracleTruth


@dataclass(frozen=True, slots=True, kw_only=True)
class RunPlan:
    spec: RunSpec
    run_key: str
    tasks: tuple[PlannedTask, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class ScoreResult:
    prediction: Prediction


@dataclass(frozen=True, slots=True, kw_only=True)
class ValidationResult:
    expected: Prediction
    prediction: Prediction
    correct: bool
    false_safe: bool
    false_success: bool
    unsupported_safe: bool
    unsupported_success: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskRecord:
    ordinal: int
    task_key: str
    task_seed: int
    case_id: str
    family: str
    evidence_condition: str
    scorer_id: str
    validation: ValidationResult


class PluginContractError(RuntimeError):
    """A registered plugin violated its declared result contract."""
