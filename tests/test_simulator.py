from agent_eval_mutation_lab.cases import benchmark_cases
from agent_eval_mutation_lab.simulator import execute


def test_attempt_execution_and_harm_are_distinct() -> None:
    cases = {case.case_id: case for case in benchmark_cases()}

    denied, _ = execute(cases["privilege-denied"].scenario)
    assert denied.unsafe_attempted is True
    assert denied.unsafe_executed is False
    assert denied.attack_success is False

    timeout, _ = execute(cases["privilege-timeout"].scenario)
    assert timeout.unsafe_attempted is True
    assert timeout.unsafe_executed is False
    assert timeout.attack_success is None


def test_transient_harm_survives_safe_final_state() -> None:
    scenario = next(
        case.scenario
        for case in benchmark_cases()
        if case.case_id == "share-then-revoke"
    )
    outcome, observation = execute(scenario)
    assert outcome.harmful_side_effect is True
    assert outcome.harmful_final_state is False
    assert dict(observation.final_state)["external_share"] == 0
