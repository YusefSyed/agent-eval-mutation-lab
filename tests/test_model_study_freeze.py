from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_eval_mutation_lab.model_study.contracts import (
    LicenseEvidence,
    ModelIdentity,
)
from agent_eval_mutation_lab.model_study.freeze import (
    FROZEN_FILES,
    freeze_protocol,
    load_model_identity,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _models() -> tuple[ModelIdentity, ...]:
    return tuple(
        ModelIdentity(
            provider="ollama",
            tag=f"model-{index}:tag",
            blob_digest=character * 64,
            parameter_count=index,
            quantization="Q4_K_M",
            license="Apache-2.0",
            license_evidence=LicenseEvidence.LOCAL_MANIFEST,
            license_source="ollama:/api/show",
            runtime_version="0.33.1",
            template_digest=("c" if index == 1 else "d") * 64,
        )
        for index, character in ((1, "a"), (2, "b"))
    )


def test_freeze_is_byte_stable_and_separates_live_inputs_from_oracle(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    plan = freeze_protocol(
        project_root=PROJECT_ROOT,
        output_dir=first,
        models=_models(),
    )
    freeze_protocol(
        project_root=PROJECT_ROOT,
        output_dir=second,
        models=_models(),
    )
    assert plan["input_count"] == 52
    assert plan["planned_terminal_trials"] == 624
    for filename in (*FROZEN_FILES, "MANIFEST.json", "SHA256SUMS"):
        assert (first / filename).read_bytes() == (second / filename).read_bytes()

    inputs = (first / "inputs.jsonl").read_text(encoding="utf-8")
    oracle = (first / "oracle-ledger.jsonl").read_text(encoding="utf-8")
    assert len(inputs.splitlines()) == 52
    assert "expected" not in inputs
    assert "evidence_condition" not in inputs
    assert "expected" in oracle
    assert "evidence_condition" in oracle

    manifest = json.loads((first / "MANIFEST.json").read_text(encoding="utf-8"))
    assert set(manifest["files"]) == set(FROZEN_FILES)


def test_identity_loader_and_freeze_fail_closed(tmp_path: Path) -> None:
    identity_path = tmp_path / "identity.json"
    identity_path.write_text(
        json.dumps(
            {
                "provider": "ollama",
                "tag": "model:tag",
                "blob_digest": "a" * 64,
                "parameter_count": 1,
                "quantization": "Q4_K_M",
                "license": "Apache-2.0",
                "license_evidence": "local_manifest",
                "license_source": "ollama:/api/show",
                "runtime_version": "0.33.1",
                "template_digest": "b" * 64,
            }
        ),
        encoding="utf-8",
    )
    identity = load_model_identity(identity_path)
    assert identity.tag == "model:tag"
    with pytest.raises(ValueError, match="exactly two"):
        freeze_protocol(
            project_root=PROJECT_ROOT,
            output_dir=tmp_path / "invalid",
            models=(identity,),
        )
