"""Benchmark orchestration."""

from __future__ import annotations

from typing import Any

from agent_eval_mutation_lab.cases import benchmark_cases
from agent_eval_mutation_lab.metrics import mutation_summary, scorer_summary
from agent_eval_mutation_lab.models import CaseResult
from agent_eval_mutation_lab.scorers import SANITY_SCORERS, SUBSTANTIVE_SCORERS
from agent_eval_mutation_lab.simulator import execute


def run_benchmark() -> dict[str, Any]:
    scorers = {**SUBSTANTIVE_SCORERS, **SANITY_SCORERS}
    results: list[CaseResult] = []
    for case in benchmark_cases():
        outcome, observation = execute(case.scenario)
        predictions = tuple(
            (name, scorer(observation)) for name, scorer in scorers.items()
        )
        results.append(
            CaseResult(
                case_id=case.case_id,
                family=case.scenario.family,
                source=case.source,
                base_case_id=case.base_case_id,
                mutation=case.mutation,
                mutation_expectation=case.mutation_expectation,
                expected=outcome.attack_success,
                predictions=predictions,
            )
        )

    summaries = {
        name: {
            **scorer_summary(results, name),
            **mutation_summary(results, name),
        }
        for name in scorers
    }
    return {
        "schema_version": 1,
        "research_question": (
            "Can execution-semantic mutation testing expose tool-agent scorers "
            "that confuse proposed actions, actual execution, and realized harm?"
        ),
        "scope": "finite synthetic benchmark; no model or production-safety claim",
        "case_count": len(results),
        "cases": [
            {
                "case_id": result.case_id,
                "family": result.family,
                "source": result.source,
                "base_case_id": result.base_case_id,
                "mutation": result.mutation,
                "mutation_expectation": result.mutation_expectation,
                "expected_attack_success": result.expected,
                "predictions": dict(result.predictions),
            }
            for result in results
        ],
        "scorers": summaries,
    }
