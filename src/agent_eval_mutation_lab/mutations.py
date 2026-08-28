"""Execution-semantic mutations used by the finite benchmark."""

from __future__ import annotations

from dataclasses import replace

from agent_eval_mutation_lab.models import Action, ActionStatus, Receipt, Scenario


def _replace_action(scenario: Scenario, index: int, action: Action) -> Scenario:
    actions = list(scenario.actions)
    actions[index] = action
    return replace(scenario, actions=tuple(actions))


def deny_execution(scenario: Scenario, index: int = 0) -> Scenario:
    action = scenario.actions[index]
    return _replace_action(
        scenario,
        index,
        replace(
            action,
            actual_status=ActionStatus.DENIED,
            actual_effects=(),
            receipt=Receipt(ActionStatus.DENIED),
        ),
    )


def fail_execution(scenario: Scenario, index: int = 0) -> Scenario:
    action = scenario.actions[index]
    return _replace_action(
        scenario,
        index,
        replace(
            action,
            actual_status=ActionStatus.FAILED,
            actual_effects=(),
            receipt=Receipt(ActionStatus.FAILED),
        ),
    )


def timeout_execution(scenario: Scenario, index: int = 0) -> Scenario:
    action = scenario.actions[index]
    return _replace_action(
        scenario,
        index,
        replace(
            action,
            actual_status=ActionStatus.TIMED_OUT,
            actual_effects=(),
            receipt=Receipt(ActionStatus.TIMED_OUT),
        ),
    )


def drop_receipt(scenario: Scenario, index: int = 0) -> Scenario:
    return _replace_action(
        scenario,
        index,
        replace(scenario.actions[index], receipt=None),
    )


def duplicate_execution(scenario: Scenario, index: int = 0) -> Scenario:
    source = scenario.actions[index]
    duplicate = replace(source, action_id=f"{source.action_id}-duplicate")
    actions = list(scenario.actions)
    actions.insert(index + 1, duplicate)
    return replace(scenario, actions=tuple(actions))


def reorder_executions(scenario: Scenario) -> Scenario:
    if len(scenario.actions) < 2:
        raise ValueError("reorder_executions requires at least two actions")
    actions = list(scenario.actions)
    actions[0], actions[1] = actions[1], actions[0]
    return replace(scenario, actions=tuple(actions))


def partial_execution(scenario: Scenario, index: int = 0) -> Scenario:
    action = scenario.actions[index]
    if len(action.actual_effects) < 2:
        raise ValueError("partial_execution requires at least two effects")
    retained_effects = (action.actual_effects[0],)
    return _replace_action(
        scenario,
        index,
        replace(
            action,
            actual_status=ActionStatus.PARTIAL,
            actual_effects=retained_effects,
            receipt=Receipt(ActionStatus.PARTIAL, retained_effects),
        ),
    )

