from agent_eval_mutation_lab.cases import benchmark_cases
from agent_eval_mutation_lab.scorers import (
    attempted_call_scorer,
    final_state_scorer,
    receipt_aware_scorer,
)
from agent_eval_mutation_lab.simulator import execute


def test_scorers_reveal_distinct_contract_failures() -> None:
    cases = {case.case_id: case for case in benchmark_cases()}

    _, denied = execute(cases["privilege-denied"].scenario)
    assert attempted_call_scorer(denied) is True
    assert final_state_scorer(denied) is False
    assert receipt_aware_scorer(denied) is False

    _, transient = execute(cases["share-then-revoke"].scenario)
    assert attempted_call_scorer(transient) is True
    assert final_state_scorer(transient) is False
    assert receipt_aware_scorer(transient) is True

    _, missing = execute(cases["privilege-no-receipt"].scenario)
    assert receipt_aware_scorer(missing) is None


def test_scorer_view_has_no_ground_truth_fields() -> None:
    scenario = benchmark_cases()[0].scenario
    _, observation = execute(scenario)
    assert not hasattr(observation, "attack_success")
    assert all(not hasattr(action, "actual_status") for action in observation.actions)
    assert all(not hasattr(action, "actual_effects") for action in observation.actions)

