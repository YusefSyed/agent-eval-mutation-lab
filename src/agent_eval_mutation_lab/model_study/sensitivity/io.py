"""Strict local JSON input for finite comparison manifests."""

from __future__ import annotations

import json
import math
from fractions import Fraction
from pathlib import Path
from typing import cast

from .bounds import Comparison, GroupPlan, Outcome


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise ValueError(f"nonfinite JSON value is forbidden: {value}")


def _finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("nonfinite JSON value is forbidden")
    return parsed


def parse_json(text: str) -> object:
    value: object = json.loads(
        text,
        object_pairs_hook=_unique_object,
        parse_constant=_reject_constant,
        parse_float=_finite_float,
    )
    return value


def read_json(path: Path) -> object:
    return parse_json(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> tuple[dict[str, object], ...]:
    return tuple(
        as_object(parse_json(line))
        for line in path.read_text(encoding="utf-8").splitlines()
    )


def as_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or any(type(key) is not str for key in value):
        raise ValueError("expected an object with string keys")
    return cast(dict[str, object], value)


def as_array(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("expected an array")
    return value


def as_string(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("expected a nonempty string")
    return value


def as_integer(value: object) -> int:
    if type(value) is not int:
        raise ValueError("expected an integer, not a bool or float")
    return value


def exact_keys(value: dict[str, object], expected: set[str]) -> None:
    if set(value) != expected:
        raise ValueError("object fields do not match the explicit input contract")


def comparison_from_payload(value: object) -> Comparison:
    payload = as_object(value)
    exact_keys(
        payload, {"schema_version", "left_arm", "right_arm", "groups", "outcomes"}
    )
    if as_integer(payload["schema_version"]) != 1:
        raise ValueError("unsupported comparison schema")
    groups = []
    for item in as_array(payload["groups"]):
        group = as_object(item)
        exact_keys(
            group,
            {
                "group",
                "weight",
                "left_planned_count",
                "right_planned_count",
                "left_trial_ids",
                "right_trial_ids",
            },
        )
        weight = as_object(group["weight"])
        exact_keys(weight, {"numerator", "denominator"})
        denominator = as_integer(weight["denominator"])
        if denominator <= 0:
            raise ValueError("rational denominator must be positive")
        groups.append(
            GroupPlan(
                group=as_string(group["group"]),
                weight=Fraction(as_integer(weight["numerator"]), denominator),
                left_planned_count=as_integer(group["left_planned_count"]),
                right_planned_count=as_integer(group["right_planned_count"]),
                left_trial_ids=tuple(
                    as_string(x) for x in as_array(group["left_trial_ids"])
                ),
                right_trial_ids=tuple(
                    as_string(x) for x in as_array(group["right_trial_ids"])
                ),
            )
        )
    outcomes = []
    for item in as_array(payload["outcomes"]):
        row = as_object(item)
        exact_keys(row, {"trial_id", "arm", "group", "value", "missing_reason"})
        value = row["value"]
        reason = row["missing_reason"]
        outcomes.append(
            Outcome(
                trial_id=as_string(row["trial_id"]),
                arm=as_string(row["arm"]),
                group=as_string(row["group"]),
                value=None if value is None else as_integer(value),
                missing_reason=None if reason is None else as_string(reason),
            )
        )
    return Comparison(
        as_string(payload["left_arm"]),
        as_string(payload["right_arm"]),
        tuple(groups),
        tuple(outcomes),
    )
