"""Explicit in-process plugin registry for existing benchmark scorers."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from agent_eval_mutation_lab.engine.canonical import sha256_file
from agent_eval_mutation_lab.engine.contracts import (
    PluginContractError,
    PluginDescriptor,
    PluginKind,
    ScoreResult,
    ScorerInput,
    TaskContext,
    VisibleAction,
    VisibleEffect,
    VisibleReceipt,
)
from agent_eval_mutation_lab.models import (
    Effect,
    ObservedAction,
    ObservedTrajectory,
    Prediction,
    Receipt,
)
from agent_eval_mutation_lab.scorers import receipt_aware_scorer
from agent_eval_mutation_lab.scorers_v2 import synthetic_benchmark_v2_scorer


class ScorerPlugin(Protocol):
    @property
    def descriptor(self) -> PluginDescriptor: ...

    def score(
        self, item: ScorerInput, *, context: TaskContext
    ) -> ScoreResult: ...


@dataclass(frozen=True, slots=True)
class FunctionScorerPlugin:
    descriptor: PluginDescriptor
    function: Callable[[ObservedTrajectory], Prediction]

    def score(
        self, item: ScorerInput, *, context: TaskContext
    ) -> ScoreResult:
        del context
        prediction = self.function(to_observed_trajectory(item))
        if prediction is not None and type(prediction) is not bool:
            raise PluginContractError(
                f"{self.descriptor.plugin_id} returned invalid prediction "
                f"{prediction!r}"
            )
        return ScoreResult(prediction=prediction)


def _source_digest(function: Callable[..., object]) -> str:
    module = __import__(function.__module__, fromlist=["__name__"])
    module_path = Path(module.__file__ or "")
    if not module_path.is_file():
        raise RuntimeError(f"cannot locate source for {function.__module__}")
    return sha256_file(module_path)


def to_scorer_input(trajectory: ObservedTrajectory) -> ScorerInput:
    return ScorerInput(
        scenario_id=trajectory.scenario_id,
        initial_state=tuple(trajectory.initial_state),
        final_state=tuple(trajectory.final_state),
        harm_key=trajectory.harm_key,
        harm_threshold=trajectory.harm_threshold,
        actions=tuple(
            VisibleAction(
                action_id=action.action_id,
                tool=action.tool,
                prohibited=action.prohibited,
                receipt=None
                if action.receipt is None
                else VisibleReceipt(
                    status=action.receipt.status,
                    effects=tuple(
                        VisibleEffect(
                            key=effect.key,
                            operation=effect.operation,
                            value=effect.value,
                        )
                        for effect in action.receipt.effects
                    ),
                ),
            )
            for action in trajectory.actions
        ),
    )


def to_observed_trajectory(item: ScorerInput) -> ObservedTrajectory:
    return ObservedTrajectory(
        scenario_id=item.scenario_id,
        initial_state=item.initial_state,
        final_state=item.final_state,
        harm_key=item.harm_key,
        harm_threshold=item.harm_threshold,
        actions=tuple(
            ObservedAction(
                action_id=action.action_id,
                tool=action.tool,
                prohibited=action.prohibited,
                receipt=None
                if action.receipt is None
                else Receipt(
                    status=action.receipt.status,
                    effects=tuple(
                        Effect(
                            key=effect.key,
                            operation=effect.operation,
                            value=effect.value,
                        )
                        for effect in action.receipt.effects
                    ),
                ),
            )
            for action in item.actions
        ),
    )


def default_scorer_plugins() -> Mapping[str, ScorerPlugin]:
    plugins: tuple[FunctionScorerPlugin, ...] = (
        FunctionScorerPlugin(
            descriptor=PluginDescriptor(
                plugin_id="receipt_aware_v1_frozen",
                version="1",
                kind=PluginKind.SCORER,
                implementation_digest=_source_digest(receipt_aware_scorer),
            ),
            function=receipt_aware_scorer,
        ),
        FunctionScorerPlugin(
            descriptor=PluginDescriptor(
                plugin_id="evidence_dominance_v2_experimental",
                version="2",
                kind=PluginKind.SCORER,
                implementation_digest=_source_digest(
                    synthetic_benchmark_v2_scorer
                ),
            ),
            function=synthetic_benchmark_v2_scorer,
        ),
    )
    return {plugin.descriptor.plugin_id: plugin for plugin in plugins}
