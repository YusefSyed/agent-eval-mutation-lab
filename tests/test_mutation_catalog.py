from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from agent_eval_mutation_lab.mutation_benchmark.catalog import load_manifest
from agent_eval_mutation_lab.mutation_benchmark.contracts import MutationPartition


def _payload() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source_path": "src/pkg/scorer.py",
        "baseline_source_sha256": "a" * 64,
        "mutations": [
            {
                "mutation_id": "return-true-to-none",
                "partition": "development",
                "function_name": "score",
                "node_type": "Return",
                "expected_segment_sha256": "b" * 64,
                "replacement": "return None",
                "operator_id": "tri_state_return_replacement",
                "semantic_rule": "affirmative harm returns true",
                "expected_semantic_change": "harm is downgraded to unknown",
                "activation_case": "harmful receipt",
                "equivalence_assessment": "none",
            }
        ],
    }


def _write(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_loads_strict_manifest(tmp_path: Path) -> None:
    manifest = load_manifest(_write(tmp_path, _payload()))
    assert manifest.schema_version == 1
    assert manifest.mutations[0].partition is MutationPartition.DEVELOPMENT
    assert manifest.mutations[0].operator_id == "tri_state_return_replacement"


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value.update(schema_version=2),
        lambda value: value.update(source_path="../escape.py"),
        lambda value: value.update(baseline_source_sha256="bad"),
        lambda value: value.update(mutations=[]),
        lambda value: value["mutations"][0].update(partition="unknown"),
        lambda value: value["mutations"][0].update(equivalence_assessment="unknown"),
        lambda value: value["mutations"][0].update(replacement=""),
    ],
)
def test_rejects_invalid_manifest(
    tmp_path: Path,
    change: Callable[[dict[str, Any]], None],
) -> None:
    payload = _payload()
    change(payload)
    with pytest.raises(ValueError):
        load_manifest(_write(tmp_path, payload))
