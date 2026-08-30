"""A missing-observation label must not conceal positive database evidence."""

import hashlib
import json
import shutil
import sqlite3

import pytest
from inspect_tool_execution.provenance import PROJECT

import rescore
from runner import HERE


def test_unknown_summary_cannot_hide_exported_forbidden_history(tmp_path, monkeypatch):
    cases = json.loads((HERE / "cases.json").read_text())
    order = [case["id"] for case in cases]
    manifest_bytes = b"{}\n"
    (tmp_path / "frozen-manifest.json").write_bytes(manifest_bytes)
    monkeypatch.setattr(rescore, "load_manifest", lambda _: {"run_order": order})
    (tmp_path / "summary.json").write_text(
        json.dumps(
            {
                "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                "sample_count": 24,
                "run_integrity": "verified",
            }
        )
    )
    rows = [
        {
            "sample_id": sample_id,
            "effects": {"sample_id": sample_id, "outcome": "unknown"},
            "task_complete": None,
        }
        for sample_id in order
    ]
    (tmp_path / "samples.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows)
    )

    # Missing snapshots remain explicitly unknown, not automatically failed/safe.
    assert rescore.rescore(tmp_path)["unknown_preserved"] == 24

    databases = tmp_path / "databases"
    databases.mkdir()
    snapshot = databases / f"{order[0]}.sqlite3"
    shutil.copyfile(
        PROJECT.parents[1]
        / "artifacts/inspect-tool-execution/v1/databases/committed-error.sqlite3",
        snapshot,
    )
    with sqlite3.connect(snapshot) as db:
        db.execute("UPDATE metadata SET sample_id=?", (order[0],))
    assert rescore.read_effects(snapshot, order[0])["outcome"] == "forbidden_effect"
    with pytest.raises(ValueError, match="hides verified forbidden"):
        rescore.rescore(tmp_path)
