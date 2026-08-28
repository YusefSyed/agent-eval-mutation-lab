"""Cross-field validation of evidence-ledger responses against model input."""

from __future__ import annotations

from agent_eval_mutation_lab.model_study.projection import JSONPayload, JSONValue
from agent_eval_mutation_lab.model_study.schemas import EvidenceFirstResponse


def validate_evidence_ledger(
    response: EvidenceFirstResponse,
    model_input: JSONPayload,
) -> None:
    """Reject missing/duplicate actions and citations outside the visible record."""

    actions = model_input.get("actions")
    if not isinstance(actions, list):
        raise ValueError("model input actions must be an array")
    expected_refs = tuple(_action_ref(item) for item in actions)
    actual_refs = tuple(item.action_ref for item in response.action_evidence)
    if len(actual_refs) != len(set(actual_refs)):
        raise ValueError("evidence ledger contains duplicate action references")
    if set(actual_refs) != set(expected_refs):
        raise ValueError("evidence ledger must cover exactly the visible actions")
    for item in response.action_evidence:
        for citation in item.citations:
            resolve_json_pointer(model_input, citation)
    for citation in response.final_state_citations:
        resolve_json_pointer(model_input, citation)


def resolve_json_pointer(document: JSONValue, pointer: str) -> JSONValue:
    """Resolve a strict RFC 6901 JSON pointer or fail closed."""

    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise ValueError("citation must be an absolute JSON pointer")
    current = document
    for raw_token in pointer[1:].split("/"):
        token = _unescape(raw_token)
        if isinstance(current, dict):
            if token not in current:
                raise ValueError(f"citation path does not exist: {pointer}")
            current = current[token]
            continue
        if isinstance(current, list):
            if not token.isdigit() or (len(token) > 1 and token.startswith("0")):
                raise ValueError(f"citation array index is invalid: {pointer}")
            index = int(token)
            if index >= len(current):
                raise ValueError(f"citation array index is out of range: {pointer}")
            current = current[index]
            continue
        raise ValueError(f"citation traverses a scalar value: {pointer}")
    return current


def _action_ref(value: JSONValue) -> str:
    if not isinstance(value, dict):
        raise ValueError("model input action must be an object")
    action_ref = value.get("action_ref")
    if not isinstance(action_ref, str) or not action_ref:
        raise ValueError("model input action_ref must be a non-empty string")
    return action_ref


def _unescape(token: str) -> str:
    result: list[str] = []
    index = 0
    while index < len(token):
        character = token[index]
        if character != "~":
            result.append(character)
            index += 1
            continue
        if index + 1 >= len(token) or token[index + 1] not in {"0", "1"}:
            raise ValueError("citation contains an invalid JSON pointer escape")
        result.append("~" if token[index + 1] == "0" else "/")
        index += 2
    return "".join(result)
