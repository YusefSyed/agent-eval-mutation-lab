"""Validate a separately authored holdout submission without importing it."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agent_eval_mutation_lab.cases import benchmark_cases

STATUSES = {"denied", "failed", "success", "timed_out", "partial"}
OPERATIONS = {"add", "set"}
RELATION_TYPES = {
    "label_changing",
    "label_preserving",
    "evidence_withholding",
}


def _mapping(value: object, context: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
        errors.append(f"{context} must be an object with string keys")
        return {}
    return dict(value)


def _effects(value: object, context: str, errors: list[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        errors.append(f"{context} must be a list")
        return []
    effects: list[dict[str, Any]] = []
    for index, raw_effect in enumerate(value):
        effect = _mapping(raw_effect, f"{context}[{index}]", errors)
        if not isinstance(effect.get("key"), str) or not effect.get("key"):
            errors.append(f"{context}[{index}].key must be a non-empty string")
        if effect.get("operation") not in OPERATIONS:
            errors.append(f"{context}[{index}].operation is invalid")
        if not isinstance(effect.get("value"), int):
            errors.append(f"{context}[{index}].value must be an integer")
        effects.append(effect)
    return effects


def validate_holdout_submission(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    attestation = _mapping(
        payload.get("author_attestation"), "author_attestation", errors
    )
    author_pseudonym = attestation.get("author_pseudonym")
    if not isinstance(author_pseudonym, str) or not author_pseudonym.strip():
        errors.append("author_attestation.author_pseudonym is required")
    if attestation.get("independent_authorship_completed") is not True:
        errors.append("independent_authorship_completed must be true")
    if attestation.get("scorer_source_seen") is not False:
        errors.append("scorer_source_seen must be false")
    if attestation.get("existing_case_labels_seen") is not False:
        errors.append("existing_case_labels_seen must be false")
    if attestation.get("ai_assistance_used") is not False:
        errors.append("ai_assistance_used must be false for a qualifying holdout")

    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or len(raw_cases) < 4:
        errors.append("cases must contain at least four items")
        raw_cases = []

    case_ids: set[str] = set()
    families: set[str] = set()
    semantic_relations: set[str] = set()
    normalized_cases: list[dict[str, Any]] = []
    for case_index, raw_case in enumerate(raw_cases):
        context = f"cases[{case_index}]"
        case = _mapping(raw_case, context, errors)
        case_id = case.get("external_case_id")
        if not isinstance(case_id, str) or not case_id:
            errors.append(f"{context}.external_case_id is required")
        elif case_id in case_ids:
            errors.append(f"duplicate external_case_id: {case_id}")
        else:
            case_ids.add(case_id)

        family = case.get("family")
        if not isinstance(family, str) or not family:
            errors.append(f"{context}.family is required")
        else:
            families.add(family)

        semantic_relation = case.get("semantic_relation")
        if not isinstance(semantic_relation, str) or not semantic_relation:
            errors.append(f"{context}.semantic_relation is required")
        else:
            semantic_relations.add(semantic_relation)
        why = case.get("why_distinct_from_existing")
        if not isinstance(why, str) or len(why.strip()) < 30:
            errors.append(
                f"{context}.why_distinct_from_existing needs at least 30 characters"
            )
        if case.get("expected_relation") not in RELATION_TYPES:
            errors.append(f"{context}.expected_relation is invalid")

        initial_state = _mapping(
            case.get("initial_state"), f"{context}.initial_state", errors
        )
        if not initial_state or not all(
            isinstance(value, int) for value in initial_state.values()
        ):
            errors.append(f"{context}.initial_state must contain integer values")
        if not isinstance(case.get("harm_key"), str) or not case.get("harm_key"):
            errors.append(f"{context}.harm_key is required")
        threshold = case.get("harm_threshold")
        if not isinstance(threshold, int) or threshold < 1:
            errors.append(f"{context}.harm_threshold must be a positive integer")

        raw_actions = case.get("actions")
        if not isinstance(raw_actions, list) or not raw_actions:
            errors.append(f"{context}.actions must be a non-empty list")
            raw_actions = []
        action_ids: set[str] = set()
        normalized_actions: list[dict[str, Any]] = []
        for action_index, raw_action in enumerate(raw_actions):
            action_context = f"{context}.actions[{action_index}]"
            action = _mapping(raw_action, action_context, errors)
            action_id = action.get("action_id")
            if not isinstance(action_id, str) or not action_id:
                errors.append(f"{action_context}.action_id is required")
            elif action_id in action_ids:
                errors.append(f"{action_context}.action_id is duplicated")
            else:
                action_ids.add(action_id)
            if not isinstance(action.get("tool"), str) or not action.get("tool"):
                errors.append(f"{action_context}.tool is required")
            if not isinstance(action.get("prohibited"), bool):
                errors.append(f"{action_context}.prohibited must be boolean")
            status = action.get("actual_status")
            if status not in STATUSES:
                errors.append(f"{action_context}.actual_status is invalid")
            actual_effects = _effects(
                action.get("actual_effects"),
                f"{action_context}.actual_effects",
                errors,
            )
            if status in {"denied", "failed", "timed_out"} and actual_effects:
                errors.append(
                    f"{action_context} non-executing status cannot have actual effects"
                )

            raw_receipt = action.get("receipt")
            receipt: dict[str, Any] | None
            if raw_receipt is None:
                receipt = None
            else:
                receipt = _mapping(raw_receipt, f"{action_context}.receipt", errors)
                if receipt.get("status") not in STATUSES:
                    errors.append(f"{action_context}.receipt.status is invalid")
                receipt_effects = _effects(
                    receipt.get("effects"),
                    f"{action_context}.receipt.effects",
                    errors,
                )
                if (
                    receipt.get("status") in {"denied", "failed", "timed_out"}
                    and receipt_effects
                ):
                    errors.append(
                        f"{action_context}.receipt non-executing status cannot "
                        "contain effects"
                    )
            normalized_actions.append(action)
        normalized_cases.append({**case, "actions": normalized_actions})

    if len(families) < 2:
        errors.append("holdout must contain at least two scenario families")
    existing_relations = {
        case.scenario.family for case in benchmark_cases()
    } | {
        case.mutation
        for case in benchmark_cases()
        if case.mutation is not None
    }
    novel_relations = sorted(semantic_relations - existing_relations)
    if not novel_relations:
        errors.append(
            "at least one semantic_relation must be distinct from existing families "
            "and mutation names"
        )

    return {
        "schema_version": 1,
        "valid": not errors,
        "qualifies_as_independent_holdout": not errors,
        "case_count": len(raw_cases),
        "family_count": len(families),
        "novel_semantic_relations": novel_relations,
        "errors": errors,
        "attestation_is_self_reported": True,
        "distinctness_is_self_reported": True,
        "normalized_case_count": len(normalized_cases),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a separately authored holdout submission."
    )
    parser.add_argument("submission", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("review/holdout-validation.json"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = json.loads(args.submission.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("submission must be a JSON object")
    report = validate_holdout_submission(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {args.output}")
    if not report["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
