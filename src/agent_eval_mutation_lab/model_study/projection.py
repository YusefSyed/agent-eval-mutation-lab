"""One-way, identifier-hiding projection from engine scorer inputs."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from agent_eval_mutation_lab.engine.contracts import ScorerInput, VisibleAction
from agent_eval_mutation_lab.models import ActionStatus, EffectOperation

type JSONScalar = str | int | float | bool | None
type JSONValue = JSONScalar | list[JSONValue] | dict[str, JSONValue]
type JSONPayload = dict[str, JSONValue]

_HASH_DOMAIN = "agent-eval-mutation-lab:model-input:v1\x00"


def opaque_id(identifier: str) -> str:
    """Return a deterministic, domain-separated opaque identifier."""

    return sha256(f"{_HASH_DOMAIN}{identifier}".encode()).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelEffect:
    key: str
    operation: EffectOperation
    value: int

    def payload(self) -> JSONPayload:
        return {
            "key": self.key,
            "operation": self.operation.value,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelReceipt:
    status: ActionStatus
    effects: tuple[ModelEffect, ...]

    def payload(self) -> JSONPayload:
        return {
            "status": self.status.value,
            "effects": [effect.payload() for effect in self.effects],
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelAction:
    action_ref: str
    tool: str
    prohibited: bool
    receipt: ModelReceipt | None

    def payload(self) -> JSONPayload:
        return {
            "action_ref": self.action_ref,
            "tool": self.tool,
            "prohibited": self.prohibited,
            "receipt": None if self.receipt is None else self.receipt.payload(),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelInput:
    """The complete JSON-compatible input visible to a studied model.

    ``scenario_ref`` and every ``action_ref`` are opaque hashes.  The type has
    no family, mutation, evidence-condition, oracle, or expected-label fields.
    """

    schema_version: int
    scenario_ref: str
    initial_state: tuple[tuple[str, int], ...]
    final_state: tuple[tuple[str, int], ...]
    harm_key: str
    harm_threshold: int
    actions: tuple[ModelAction, ...]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported model input schema version")

    def payload(self) -> JSONPayload:
        """Return a fresh JSON-compatible payload in a stable field order."""

        return {
            "schema_version": self.schema_version,
            "scenario_ref": self.scenario_ref,
            "initial_state": [[key, value] for key, value in self.initial_state],
            "final_state": [[key, value] for key, value in self.final_state],
            "harm_key": self.harm_key,
            "harm_threshold": self.harm_threshold,
            "actions": [action.payload() for action in self.actions],
        }


def project_model_input(source: ScorerInput) -> ModelInput:
    """Project only scorer-visible facts into the studied-model protocol."""

    return ModelInput(
        schema_version=1,
        scenario_ref=opaque_id(source.scenario_id),
        initial_state=source.initial_state,
        final_state=source.final_state,
        harm_key=source.harm_key,
        harm_threshold=source.harm_threshold,
        actions=tuple(_project_action(action) for action in source.actions),
    )


def _project_action(source: VisibleAction) -> ModelAction:
    receipt = source.receipt
    model_receipt = (
        None
        if receipt is None
        else ModelReceipt(
            status=receipt.status,
            effects=tuple(
                ModelEffect(
                    key=effect.key,
                    operation=effect.operation,
                    value=effect.value,
                )
                for effect in receipt.effects
            ),
        )
    )
    return ModelAction(
        action_ref=opaque_id(source.action_id),
        tool=source.tool,
        prohibited=source.prohibited,
        receipt=model_receipt,
    )
