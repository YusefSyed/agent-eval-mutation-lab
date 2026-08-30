"""Adversarial report edits must not upgrade failures or subsets to acceptance."""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from inspect_tool_execution.effect_scorer import read_effects
from inspect_tool_execution.provenance import source_hashes
from inspect_tool_execution.verify import verify


@pytest.fixture
def evidence(tmp_path):
    source = Path(__file__).parents[3] / "artifacts" / "inspect-tool-execution" / "v1"
    directory = tmp_path / "evidence"
    shutil.copytree(source, directory)
    report_file = directory / "normalized-report.json"
    report = json.loads(report_file.read_text())
    # Use captured real-tool evidence as a test fixture for the current verifier.
    # This rebinds only the temporary test copy, not committed evidence provenance.
    report["source_sha256"] = source_hashes()
    report["full_suite"] = True
    report_file.write_text(json.dumps(report))
    assert len(verify(directory)) == 14
    return directory, report_file, report


def test_missing_case_cannot_pass_full_suite_with_true_flags(evidence):
    directory, report_file, report = evidence
    removed = report["results"].pop()
    (directory / "databases" / f"{removed['case_id']}.sqlite3").unlink()
    report_file.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="exact fixture case IDs"):
        verify(directory)


def test_forged_effect_pass_flags_cannot_override_actual_expectation(evidence):
    directory, report_file, report = evidence
    result = next(r for r in report["results"] if r["case_id"] == "denied-absent")
    path = directory / "databases" / "denied-absent.sqlite3"
    # A fully consistent forbidden event, with the edited report acknowledging
    # those actual effects but falsely retaining its acceptance=True flags.
    with sqlite3.connect(path) as db:
        db.execute(
            "UPDATE artifacts SET published=1 WHERE artifact_id='protected-draft'"
        )
        db.execute(
            "INSERT INTO events VALUES (1,'forged','publish_artifact',"
            "'protected-draft',0,1)"
        )
        db.execute(
            "INSERT INTO requests VALUES ('forged','publish_artifact',"
            "'protected-draft',1)"
        )
    result["effects"] = read_effects(path, "denied-absent")
    report_file.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="independent fixture acceptance failed"):
        verify(directory)


@pytest.mark.parametrize("part", ["tool_execution", "approvals"])
def test_forged_dispatch_pass_flags_cannot_override_native_expectation(evidence, part):
    directory, report_file, report = evidence
    result = report["results"][0]
    if part == "tool_execution":
        result[part][0]["error_type"] = "parsing"
    else:
        result[part][0]["decision"] = "reject"
    report_file.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="independent fixture acceptance failed"):
        verify(directory)


def test_source_change_and_database_tamper_are_rejected(evidence):
    directory, report_file, report = evidence
    path = directory / "databases" / "approved-persisted.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("UPDATE artifacts SET published=0 WHERE artifact_id='public-report'")
    with pytest.raises(ValueError, match="effect re-score mismatch"):
        verify(directory)
    report["source_sha256"] = {}
    report_file.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="source identity"):
        verify(directory)
