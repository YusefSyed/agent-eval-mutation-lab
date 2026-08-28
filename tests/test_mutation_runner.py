from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from agent_eval_mutation_lab.mutation_benchmark.contracts import (
    EquivalenceAssessment,
    MutantStatus,
    MutationManifest,
    MutationSpec,
)
from agent_eval_mutation_lab.mutation_benchmark.runner import run_baseline, run_mutant

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = Path("src/agent_eval_mutation_lab/scorers_v2.py")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _manifest(spec: MutationSpec) -> MutationManifest:
    source = (PROJECT_ROOT / SOURCE_PATH).read_bytes()
    return MutationManifest(
        schema_version=1,
        source_path=SOURCE_PATH.as_posix(),
        baseline_source_sha256=_sha256(source),
        mutations=(spec,),
    )


def test_baseline_passes_through_snapshot_import_boundary() -> None:
    result = run_baseline(
        PROJECT_ROOT,
        selectors=("tests/test_scorers_v2.py",),
        timeout_seconds=20.0,
    )
    assert result.return_code == 0
    assert result.import_origin_verified is True
    assert result.failing_test_ids == ()


def test_valid_semantic_mutant_is_killed() -> None:
    spec = MutationSpec(
        mutation_id="harm-true-to-none",
        function_name="receipt_aware_v2_scorer",
        node_type="Return",
        expected_segment_sha256=(
            "37992c22232b4712e447e7067cfaa1fe3ed7c98e3080608ed81f7c2b1e62992c"
        ),
        replacement="return None",
    )
    result = run_mutant(
        PROJECT_ROOT,
        _manifest(spec),
        spec,
        selectors=("tests/test_scorers_v2.py",),
        timeout_seconds=20.0,
    )
    assert result.status is MutantStatus.KILLED
    assert result.test_run.import_origin_verified is True
    assert result.test_run.failing_test_ids


def test_development_equivalent_fixture_survives_frozen_suite() -> None:
    spec = MutationSpec(
        mutation_id="unused-helper-capability-default",
        function_name="receipt_aware_v2_scorer",
        node_type="BoolOp",
        expected_segment_sha256=(
            "be60f9c8e4696ae0a4cb89ceadad3cd08a91dfedb9c19449366c36a71be90299"
        ),
        replacement="tool_capabilities if tool_capabilities is not None else {}",
        equivalence_assessment=EquivalenceAssessment.PLAUSIBLY_EQUIVALENT,
    )
    result = run_mutant(
        PROJECT_ROOT,
        _manifest(spec),
        spec,
        selectors=("tests/test_scorers_v2.py",),
        timeout_seconds=20.0,
    )
    assert result.status is MutantStatus.PLAUSIBLY_EQUIVALENT


def test_source_hash_drift_is_invalid() -> None:
    spec = MutationSpec(
        mutation_id="drift",
        function_name="receipt_aware_v2_scorer",
        node_type="Return",
        expected_segment_sha256="0" * 64,
        replacement="return None",
    )
    manifest = MutationManifest(
        schema_version=1,
        source_path=SOURCE_PATH.as_posix(),
        baseline_source_sha256="0" * 64,
        mutations=(spec,),
    )
    result = run_mutant(
        PROJECT_ROOT,
        manifest,
        spec,
        selectors=("tests/test_scorers_v2.py",),
        timeout_seconds=20.0,
    )
    assert result.status is MutantStatus.INVALID


def test_manual_manifest_cannot_escape_project_root() -> None:
    spec = MutationSpec(
        mutation_id="escape",
        function_name="receipt_aware_v2_scorer",
        node_type="Return",
        expected_segment_sha256="0" * 64,
        replacement="return None",
    )
    manifest = replace(_manifest(spec), source_path="../outside.py")
    with pytest.raises(ValueError, match="safe repository-relative"):
        run_mutant(
            PROJECT_ROOT,
            manifest,
            spec,
            selectors=("tests/test_scorers_v2.py",),
            timeout_seconds=20.0,
        )
