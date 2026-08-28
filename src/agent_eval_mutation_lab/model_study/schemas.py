"""Strict structured-output schemas and parsers for both study arms."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from agent_eval_mutation_lab.models import Prediction

type JSONResponse = dict[str, object]


class Verdict(StrEnum):
    HARM_ESTABLISHED = "harm_established"
    NO_HARM_ESTABLISHED = "no_harm_established"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class ExecutionAssessment(StrEnum):
    EXECUTED = "executed"
    NOT_EXECUTED = "not_executed"
    UNRESOLVED = "unresolved"


class HarmAssessment(StrEnum):
    CAUSED_HARM = "caused_harm"
    NO_HARM_OBSERVED = "no_harm_observed"
    UNRESOLVED = "unresolved"


class FinalStateAttribution(StrEnum):
    ATTRIBUTABLE = "attributable"
    NOT_ATTRIBUTABLE = "not_attributable"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True, kw_only=True)
class ProbabilityVector:
    harm_established: float
    no_harm_established: float
    insufficient_evidence: float


@dataclass(frozen=True, slots=True, kw_only=True)
class ActionEvidence:
    action_ref: str
    execution: ExecutionAssessment
    harm: HarmAssessment
    citations: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class DirectResponse:
    verdict: Verdict
    probabilities: ProbabilityVector
    conclusion: str

    @property
    def prediction(self) -> Prediction:
        return _prediction(self.verdict)


@dataclass(frozen=True, slots=True, kw_only=True)
class EvidenceFirstResponse:
    action_evidence: tuple[ActionEvidence, ...]
    final_state_attribution: FinalStateAttribution
    final_state_citations: tuple[str, ...]
    verdict: Verdict
    probabilities: ProbabilityVector
    conclusion: str

    @property
    def prediction(self) -> Prediction:
        return _prediction(self.verdict)


_PROBABILITIES_SCHEMA: JSONResponse = {
    "type": "object",
    "additionalProperties": False,
    "required": [item.value for item in Verdict],
    "properties": {
        verdict.value: {"type": "number", "minimum": 0, "maximum": 1}
        for verdict in Verdict
    },
}

_COMMON_PROPERTIES: JSONResponse = {
    "verdict": {"type": "string", "enum": [verdict.value for verdict in Verdict]},
    "probabilities": _PROBABILITIES_SCHEMA,
    "conclusion": {"type": "string", "minLength": 1},
}

DIRECT_RESPONSE_SCHEMA: JSONResponse = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict", "probabilities", "conclusion"],
    "properties": _COMMON_PROPERTIES,
}

EVIDENCE_FIRST_RESPONSE_SCHEMA: JSONResponse = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "action_evidence",
        "final_state_attribution",
        "final_state_citations",
        "verdict",
        "probabilities",
        "conclusion",
    ],
    "properties": {
        "action_evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["action_ref", "execution", "harm", "citations"],
                "properties": {
                    "action_ref": {
                        "type": "string",
                        "minLength": 1,
                        "description": (
                            "Literal opaque action_ref value copied from the input; "
                            "not a JSON pointer"
                        ),
                    },
                    "execution": {
                        "type": "string",
                        "enum": [item.value for item in ExecutionAssessment],
                    },
                    "harm": {
                        "type": "string",
                        "enum": [item.value for item in HarmAssessment],
                    },
                    "citations": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "string",
                            "pattern": "^/",
                            "description": (
                                "Absolute RFC 6901 JSON pointer, for example "
                                "/actions/0/receipt/status"
                            ),
                        },
                    },
                },
            },
        },
        "final_state_attribution": {
            "type": "string",
            "enum": [item.value for item in FinalStateAttribution],
        },
        "final_state_citations": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "string",
                "pattern": "^/",
                "description": "Absolute RFC 6901 JSON pointer beginning with /",
            },
        },
        **_COMMON_PROPERTIES,
    },
}


def parse_direct_response(value: object) -> DirectResponse:
    payload = _strict_object(value, {"verdict", "probabilities", "conclusion"})
    return DirectResponse(
        verdict=_enum(Verdict, payload["verdict"], "verdict"),
        probabilities=_probabilities(payload["probabilities"]),
        conclusion=_text(payload["conclusion"], "conclusion"),
    )


def parse_evidence_first_response(value: object) -> EvidenceFirstResponse:
    required = {
        "action_evidence",
        "final_state_attribution",
        "final_state_citations",
        "verdict",
        "probabilities",
        "conclusion",
    }
    payload = _strict_object(value, required)
    raw_actions = payload["action_evidence"]
    if not isinstance(raw_actions, list):
        raise ValueError("action_evidence must be an array")
    return EvidenceFirstResponse(
        action_evidence=tuple(_action_evidence(item) for item in raw_actions),
        final_state_attribution=_enum(
            FinalStateAttribution,
            payload["final_state_attribution"],
            "final_state_attribution",
        ),
        final_state_citations=_citations(
            payload["final_state_citations"], "final_state_citations"
        ),
        verdict=_enum(Verdict, payload["verdict"], "verdict"),
        probabilities=_probabilities(payload["probabilities"]),
        conclusion=_text(payload["conclusion"], "conclusion"),
    )


def _action_evidence(value: object) -> ActionEvidence:
    payload = _strict_object(
        value, {"action_ref", "execution", "harm", "citations"}
    )
    return ActionEvidence(
        action_ref=_text(payload["action_ref"], "action_ref"),
        execution=_enum(
            ExecutionAssessment, payload["execution"], "execution"
        ),
        harm=_enum(HarmAssessment, payload["harm"], "harm"),
        citations=_citations(payload["citations"], "citations"),
    )


def _probabilities(value: object) -> ProbabilityVector:
    payload = _strict_object(value, {item.value for item in Verdict})
    values = tuple(_probability(payload[item.value], item.value) for item in Verdict)
    if not math.isclose(sum(values), 1.0, abs_tol=1e-6):
        raise ValueError("probabilities must sum to one")
    return ProbabilityVector(
        harm_established=values[0],
        no_harm_established=values[1],
        insufficient_evidence=values[2],
    )


def _probability(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} probability must be numeric")
    result = float(value)
    if not math.isfinite(result) or not 0 <= result <= 1:
        raise ValueError(f"{field} probability must be finite and in [0, 1]")
    return result


def _citations(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be a non-empty array")
    citations = tuple(_text(item, field) for item in value)
    if not all(item.startswith("/") for item in citations):
        raise ValueError(f"{field} entries must be JSON pointers")
    return citations


def _strict_object(value: object, required: set[str]) -> JSONResponse:
    if not isinstance(value, dict):
        raise ValueError("response must be an object")
    if set(value) != required:
        raise ValueError("response has missing or unknown fields")
    return value


def _enum[T: StrEnum](kind: type[T], value: object, field: str) -> T:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    try:
        return kind(value)
    except ValueError as error:
        raise ValueError(f"{field} is not recognized") from error


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _prediction(verdict: Verdict) -> Prediction:
    if verdict is Verdict.HARM_ESTABLISHED:
        return True
    if verdict is Verdict.NO_HARM_ESTABLISHED:
        return False
    return None
