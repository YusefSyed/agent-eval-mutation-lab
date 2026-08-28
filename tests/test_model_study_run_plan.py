from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from agent_eval_mutation_lab.model_study.contracts import StudyArm
from agent_eval_mutation_lab.model_study.run_plan import load_frozen_study

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FROZEN = PROJECT_ROOT / "benchmarks/model-study-v1/frozen"


def test_frozen_plan_expands_to_paired_deterministic_624_trials() -> None:
    first = load_frozen_study(project_root=PROJECT_ROOT, frozen_dir=FROZEN)
    second = load_frozen_study(project_root=PROJECT_ROOT, frozen_dir=FROZEN)
    assert first == second
    assert len(first.trials) == 624
    assert len(first.models) == 2
    assert len({trial.identity.trial_id for trial in first.trials}) == 624
    assert [trial.identity.arm for trial in first.trials[:2]] == [
        StudyArm.DIRECT,
        StudyArm.EVIDENCE_FIRST,
    ]
    assert first.trials[0].input_ref == first.trials[1].input_ref
    assert first.trials[0].payload == first.trials[1].payload
    assert (
        first.trials[0].identity.prompt_digest
        != first.trials[1].identity.prompt_digest
    )
    serialized = str(first.trials[0].payload)
    assert "expected" not in serialized
    assert "evidence_condition" not in serialized


def test_frozen_plan_rejects_tampered_protocol_bytes(tmp_path: Path) -> None:
    copied = tmp_path / "frozen"
    shutil.copytree(FROZEN, copied)
    inputs = copied / "inputs.jsonl"
    inputs.write_bytes(inputs.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_frozen_study(project_root=PROJECT_ROOT, frozen_dir=copied)
