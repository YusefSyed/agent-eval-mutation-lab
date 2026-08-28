"""Strict JSON catalog loading for predeclared source mutations."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any

from agent_eval_mutation_lab.mutation_benchmark.contracts import (
    EquivalenceAssessment,
    MutationManifest,
    MutationPartition,
    MutationSpec,
)


def load_manifest(path: Path) -> MutationManifest:
    """Load a versioned manifest and reject ambiguous or unsafe values."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("mutation manifest must be an object")
    schema_version = _integer(payload, "schema_version")
    if schema_version != 1:
        raise ValueError("unsupported mutation manifest schema_version")
    source_path = _string(payload, "source_path")
    pure_path = PurePosixPath(source_path)
    if pure_path.is_absolute() or ".." in pure_path.parts:
        raise ValueError("source_path must be a safe repository-relative path")
    raw_mutations = payload.get("mutations")
    if not isinstance(raw_mutations, list) or not raw_mutations:
        raise ValueError("mutations must be a non-empty array")
    mutations = tuple(_mutation(item) for item in raw_mutations)
    mutation_ids = [item.mutation_id for item in mutations]
    if len(mutation_ids) != len(set(mutation_ids)):
        raise ValueError("mutation IDs must be unique")
    return MutationManifest(
        schema_version=schema_version,
        source_path=source_path,
        baseline_source_sha256=_sha256_string(payload, "baseline_source_sha256"),
        mutations=mutations,
    )


def _mutation(value: object) -> MutationSpec:
    if not isinstance(value, dict):
        raise ValueError("each mutation must be an object")
    partition_value = _string(value, "partition")
    try:
        partition = MutationPartition(partition_value)
    except ValueError as error:
        raise ValueError(f"invalid mutation partition: {partition_value}") from error
    equivalence_value = _string(value, "equivalence_assessment")
    try:
        equivalence = EquivalenceAssessment(equivalence_value)
    except ValueError as error:
        raise ValueError(
            f"invalid equivalence assessment: {equivalence_value}"
        ) from error
    return MutationSpec(
        mutation_id=_string(value, "mutation_id"),
        function_name=_string(value, "function_name"),
        node_type=_string(value, "node_type"),
        expected_segment_sha256=_sha256_string(value, "expected_segment_sha256"),
        replacement=_string(value, "replacement"),
        partition=partition,
        operator_id=_string(value, "operator_id"),
        semantic_rule=_string(value, "semantic_rule"),
        expected_semantic_change=_string(value, "expected_semantic_change"),
        activation_case=_string(value, "activation_case"),
        equivalence_assessment=equivalence,
    )


def _string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _integer(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if type(value) is not int:
        raise ValueError(f"{key} must be an integer")
    return value


def _sha256_string(payload: dict[str, Any], key: str) -> str:
    value = _string(payload, key)
    is_lower_hex = all(character in "0123456789abcdef" for character in value)
    if len(value) != 64 or not is_lower_hex:
        raise ValueError(f"{key} must be a lowercase SHA-256 digest")
    return value
