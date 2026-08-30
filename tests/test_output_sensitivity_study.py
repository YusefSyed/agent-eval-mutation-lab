from __future__ import annotations

import hashlib
import json
import socket
import sqlite3
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest

from agent_eval_mutation_lab.model_study.analysis import AnalyzedTrial
from agent_eval_mutation_lab.model_study.contracts import StudyArm, TerminalStatus
from agent_eval_mutation_lab.model_study.run_plan import load_frozen_study
from agent_eval_mutation_lab.model_study.sensitivity.bounds import (
    Estimand,
    Interval,
    audit_comparison,
)
from agent_eval_mutation_lab.model_study.sensitivity.cli import main, write_diagnostic
from agent_eval_mutation_lab.model_study.sensitivity.io import read_json, read_jsonl
from agent_eval_mutation_lab.model_study.sensitivity.study import (
    join_trials,
    load_frozen_diagnostic,
    model_comparison,
    outcome_from_trial,
    verify_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "benchmarks/model-study-v1/frozen"
CANONICAL = ROOT / "artifacts/model-study/v1"


def _hash_tree():
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for root in (FROZEN, CANONICAL)
        for path in root.rglob("*")
        if path.is_file()
    }


def test_frozen_adapter_is_read_only_preserves_gate_and_known_exact_diagnostics(
    monkeypatch,
):
    before = _hash_tree()

    def forbidden(*args, **kwargs):
        raise AssertionError("diagnostic must not open SQLite or a network connection")

    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    study = load_frozen_diagnostic(ROOT)
    assert _hash_tree() == before
    assert study.provenance["planned_terminal_count"] == 624
    assert study.provenance["valid_count"] == 587
    assert study.provenance["invalid_count"] == 37
    assert study.provenance["output_validity_gate_passed"] is False
    assert study.provenance["positive_claim_gates_passed"] is False
    qwen = model_comparison(study, "qwen3.5:9b-q4_K_M", "pooled")
    assert audit_comparison(qwen, Estimand.PIPELINE).difference == Interval(
        Fraction(1, 12), Fraction(1, 12)
    )
    assert audit_comparison(qwen, Estimand.VALID_ONLY).difference == Interval(
        Fraction(17, 77), Fraction(17, 77)
    )
    assert audit_comparison(qwen, Estimand.LATENT).difference == Interval(
        Fraction(11, 156), Fraction(4, 13)
    )
    families = model_comparison(study, "qwen3.5:9b-q4_K_M", "equal_family")
    assert len(families.groups) == 5
    assert all(group.weight == Fraction(1, 5) for group in families.groups)
    assert audit_comparison(families, Estimand.LATENT).difference == Interval(
        Fraction(53, 300), Fraction(87, 200)
    )
    assert study.provenance["output_validity_gate_passed"] is False
    for model, weighting in (("absent", "pooled"), ("qwen3.5:9b-q4_K_M", "automatic")):
        with pytest.raises(ValueError):
            model_comparison(study, model, weighting)


def test_complete_semantic_unknown_is_observed_and_invalid_null_is_missing():
    complete = AnalyzedTrial(
        trial_id="test",
        input_ref="input",
        family="family",
        model="model",
        arm=StudyArm.DIRECT,
        seed=1,
        status=TerminalStatus.COMPLETE,
        prediction=None,
        expected=None,
        probability_harm=0.0,
        probability_no_harm=0.0,
        probability_unknown=1.0,
    )
    assert outcome_from_trial(complete, "family").value == 1
    assert outcome_from_trial(replace(complete, expected=True), "family").value == 0
    invalid = replace(
        complete,
        status=TerminalStatus.INVALID_RESPONSE,
        probability_harm=None,
        probability_no_harm=None,
        probability_unknown=None,
    )
    outcome = outcome_from_trial(invalid, "family")
    assert outcome.value is None
    assert outcome.missing_reason == "invalid_response"


def test_frozen_join_rejects_duplicate_incomplete_and_wrong_group_terminals():
    plan = load_frozen_study(project_root=ROOT, frozen_dir=FROZEN)
    rows = read_jsonl(CANONICAL / "trials.jsonl")
    oracle = read_jsonl(FROZEN / "oracle-ledger.jsonl")
    baseline = join_trials(plan, rows, oracle)
    assert join_trials(plan, tuple(reversed(rows)), tuple(reversed(oracle))) == baseline
    for wrong_rows, wrong_oracle in (
        (rows[:-1], oracle),
        ((*rows, rows[0]), oracle),
        (({**rows[0], "family": "wrong"}, *rows[1:]), oracle),
        (({**rows[0], "expected": 1}, *rows[1:]), oracle),
        (({**rows[0], "seed": True}, *rows[1:]), oracle),
        (({**rows[0], "trial_id": "unplanned"}, *rows[1:]), oracle),
        (rows, (*oracle, oracle[0])),
        (rows, oracle[:-1]),
    ):
        with pytest.raises(ValueError):
            join_trials(plan, wrong_rows, wrong_oracle)


def _fixture_manifest(root: Path):
    root.mkdir()
    (root / "input.json").write_text('{"x": 1}\n')
    content = (root / "input.json").read_bytes()
    manifest = {
        "schema_version": 1,
        "files": {
            "input.json": {
                "sha256": hashlib.sha256(content).hexdigest(),
                "size": len(content),
            }
        },
    }
    (root / "MANIFEST.json").write_text(json.dumps(manifest))
    _refresh_sums(root)


def _refresh_sums(root: Path):
    (root / "SHA256SUMS").write_text(
        "".join(
            f"{hashlib.sha256((root / name).read_bytes()).hexdigest()}  {name}\n"
            for name in ("input.json", "MANIFEST.json")
        )
    )


def test_checksum_and_size_manifests_must_be_complete_unique_and_consistent(tmp_path):
    root = tmp_path / "artifacts"
    _fixture_manifest(root)
    verify_manifest(root, ("input.json",))
    original = (root / "SHA256SUMS").read_text()
    for corrupted in (
        original.splitlines()[0] + "\n",
        original + original.splitlines()[0] + "\n",
        original.replace("input.json", "../escape.json"),
    ):
        (root / "SHA256SUMS").write_text(corrupted)
        with pytest.raises(ValueError):
            verify_manifest(root, ("input.json",))
    (root / "SHA256SUMS").write_text(original)
    (root / "input.json").write_text('{"x": 2}\n')
    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_manifest(root, ("input.json",))
    _refresh_sums(root)
    with pytest.raises(ValueError, match="identity"):
        verify_manifest(root, ("input.json",))


def test_reports_are_order_invariant_and_refuse_overwrite_or_canonical_output(tmp_path):
    study = load_frozen_diagnostic(ROOT)
    contract = model_comparison(study, "qwen3.5:9b-q4_K_M", "equal_family")
    reordered = replace(
        contract,
        groups=tuple(
            replace(
                g,
                left_trial_ids=tuple(reversed(g.left_trial_ids)),
                right_trial_ids=tuple(reversed(g.right_trial_ids)),
            )
            for g in reversed(contract.groups)
        ),
        outcomes=tuple(reversed(contract.outcomes)),
    )
    first, second = tmp_path / "first", tmp_path / "second"
    for output, comparison in ((first, contract), (second, reordered)):
        write_diagnostic(
            output=output,
            project_root=ROOT,
            provenance=study.provenance,
            comparisons=[("model", "equal_family", comparison)],
            estimands=tuple(reversed(tuple(Estimand))),
        )
    assert {p.name: p.read_bytes() for p in first.iterdir()} == {
        p.name: p.read_bytes() for p in second.iterdir()
    }
    report = read_json(first / "diagnostic.json")
    assert report["provenance"]["output_validity_gate_passed"] is False
    assert "False" in (first / "diagnostic.md").read_text()
    for output, root in (
        (first, ROOT),
        (tmp_path / "artifacts/model-study/v1/new", tmp_path),
    ):
        with pytest.raises(ValueError, match="new directory"):
            write_diagnostic(
                output=output,
                project_root=root,
                provenance=study.provenance,
                comparisons=[("model", "equal_family", contract)],
                estimands=(Estimand.LATENT,),
            )


def test_cli_requires_estimand_and_frozen_weighting_before_reading_or_writing(tmp_path):
    for arguments in (
        ["--frozen-study", str(ROOT), "--output", str(tmp_path / "x")],
        [
            "--frozen-study",
            str(ROOT),
            "--estimand",
            "all",
            "--output",
            str(tmp_path / "x"),
        ],
    ):
        with pytest.raises(SystemExit) as caught:
            main(arguments)
        assert caught.value.code == 2
    main(
        [
            "--frozen-study",
            str(ROOT),
            "--estimand",
            "all",
            "--weighting",
            "both",
            "--output",
            str(tmp_path / "new"),
        ]
    )
    report = read_json(tmp_path / "new/diagnostic.json")
    assert len(report["comparisons"]) == 12
    assert report["provenance"]["output_validity_gate_passed"] is False
    assert not (tmp_path / "x").exists()
    expected = ROOT / "artifacts/sensitivity/model-study-v1-posthoc"
    assert {p.name: p.read_bytes() for p in (tmp_path / "new").iterdir()} == {
        p.name: p.read_bytes() for p in expected.iterdir()
    }
    fixture = ROOT / "research/fixtures/missing-output-selection-reversal.json"
    main(
        [
            "--input",
            str(fixture),
            "--estimand",
            "all",
            "--output",
            str(tmp_path / "reversal"),
        ]
    )
    expected = ROOT / "artifacts/sensitivity/selection-reversal"
    assert {p.name: p.read_bytes() for p in (tmp_path / "reversal").iterdir()} == {
        p.name: p.read_bytes() for p in expected.iterdir()
    }
    malformed = tmp_path / "invalid.json"
    payload = read_json(fixture)
    payload["outcomes"][0]["value"] = True
    malformed.write_text(json.dumps(payload))
    with pytest.raises(SystemExit) as caught:
        main(
            [
                "--input",
                str(malformed),
                "--estimand",
                "all",
                "--output",
                str(tmp_path / "refused"),
            ]
        )
    assert caught.value.code == 2
    assert not (tmp_path / "refused").exists()
