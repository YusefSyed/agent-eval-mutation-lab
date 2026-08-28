from __future__ import annotations

import pytest

from agent_eval_mutation_lab.model_study.schemas import (
    ExecutionAssessment,
    FinalStateAttribution,
    HarmAssessment,
    Verdict,
    parse_evidence_first_response,
)
from agent_eval_mutation_lab.model_study.validation import (
    resolve_json_pointer,
    validate_evidence_ledger,
)


def _input() -> dict:
    return {
        "schema_version": 1,
        "scenario_ref": "scenario",
        "initial_state": [["harm", 0]],
        "final_state": [["harm", 1]],
        "harm_key": "harm",
        "harm_threshold": 1,
        "actions": [
            {
                "action_ref": "action-1",
                "tool": "synthetic.tool",
                "prohibited": True,
                "receipt": {"status": "success", "effects": []},
            }
        ],
    }


def _response(action_ref: str = "action-1", citation: str = "/actions/0/receipt"):
    return parse_evidence_first_response(
        {
            "action_evidence": [
                {
                    "action_ref": action_ref,
                    "execution": ExecutionAssessment.UNRESOLVED.value,
                    "harm": HarmAssessment.UNRESOLVED.value,
                    "citations": [citation],
                }
            ],
            "final_state_attribution": FinalStateAttribution.ATTRIBUTABLE.value,
            "final_state_citations": ["/initial_state", "/final_state"],
            "verdict": Verdict.HARM_ESTABLISHED.value,
            "probabilities": {
                "harm_established": 0.8,
                "no_harm_established": 0.05,
                "insufficient_evidence": 0.15,
            },
            "conclusion": "final harm is newly attributable",
        }
    )


def test_ledger_covers_visible_actions_and_citations_resolve() -> None:
    validate_evidence_ledger(_response(), _input())
    assert resolve_json_pointer(_input(), "/actions/0/action_ref") == "action-1"


def test_ledger_rejects_hallucinated_action_and_citation() -> None:
    with pytest.raises(ValueError, match="exactly the visible actions"):
        validate_evidence_ledger(_response(action_ref="invented"), _input())
    with pytest.raises(ValueError, match="does not exist"):
        validate_evidence_ledger(_response(citation="/actions/0/invented"), _input())


@pytest.mark.parametrize("pointer", ["relative", "/actions/01", "/bad~2escape"])
def test_json_pointer_rejects_ambiguous_or_invalid_paths(pointer: str) -> None:
    with pytest.raises(ValueError):
        resolve_json_pointer(_input(), pointer)
