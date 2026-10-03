"""Offline verifier tests use native mock/local-stub evidence, never Docker."""

import json
import shutil
from copy import deepcopy

import pytest
from conftest import CASES
from test_native import run_native_fixture

from inspect_v3_bridge import runner
from inspect_v3_bridge.projection import canonical, views
from inspect_v3_bridge.verify import acceptance, verify


@pytest.fixture(scope="module")
def unit_evidence(tmp_path_factory):
    output = tmp_path_factory.mktemp("unit-evidence")
    for subdir in ("raw", "sealed", "databases", "inspect-logs"):
        (output / subdir).mkdir()
    results = []
    for case in CASES:
        raw, database, log_path = run_native_fixture(case, output / case["id"])
        shutil.copyfile(database, output / "databases" / (case["id"] + ".sqlite3"))
        shutil.copyfile(log_path, output / "inspect-logs" / log_path.name)
        sealed = {"sample_id": case["id"], "views": views(raw)}
        (output / "raw" / (case["id"] + ".json")).write_text(canonical(raw))
        (output / "sealed" / (case["id"] + ".json")).write_text(canonical(sealed))
        results.append(acceptance(case, raw, sealed, output))
    report = {
        "schema_version": 1,
        "execution": "mock_model_actual_docker_tools",
        "live_model_evidence": False,
        "source_sha256": runner.source_hashes(),
        "results": results,
        "all_acceptance_checks_pass": True,
    }
    (output / "normalized-report.json").write_text(canonical(report))
    # Local-stub test artifacts are temporary, not public actual-tool evidence.
    return output


def test_offline_recomputation_and_comparison(unit_evidence, tmp_path):
    hashes = verify(unit_evidence)
    shutil.copytree(unit_evidence, tmp_path / "copy")
    assert verify(tmp_path / "copy") == hashes
    assert len(hashes) == 40


@pytest.mark.parametrize(
    "mutation",
    [
        "raw_complete",
        "seal_prediction",
        "seal_contract",
        "seal_bool_type",
        "report_passed",
        "source",
        "missing",
        "extra",
        "database",
        "native_flag",
        "probe_schema",
        "report_effects",
    ],
)
def test_offline_verifier_rejects_forgery(mutation, unit_evidence, tmp_path):
    output = tmp_path / "tampered"
    shutil.copytree(unit_evidence, output)
    name = "committed-error.json"
    path = output / "normalized-report.json"
    if mutation == "raw_complete":
        path = output / "raw" / name
        doc = json.loads(path.read_text())
        doc["native"]["single_call_turns"] = False
    elif mutation == "seal_prediction":
        path = output / "sealed" / name
        doc = json.loads(path.read_text())
        doc["views"]["complete"]["prediction"] = False
    elif mutation == "seal_contract":
        path = output / "sealed" / name
        doc = json.loads(path.read_text())
        doc["views"]["complete"]["scorer_input"]["contract"][
            "action_records_complete"
        ] = False
    elif mutation == "seal_bool_type":
        path = output / "sealed" / name
        doc = json.loads(path.read_text())
        doc["views"]["complete"]["prediction"] = 1
    elif mutation == "report_passed":
        doc = json.loads(path.read_text())
        doc["all_acceptance_checks_pass"] = False
    elif mutation == "source":
        doc = json.loads(path.read_text())
        doc["source_sha256"] = {}
    elif mutation == "missing":
        (output / "raw" / name).unlink()
        doc = json.loads(path.read_text())
    elif mutation == "extra":
        shutil.copyfile(output / "raw" / name, output / "raw/extra.json")
        doc = json.loads(path.read_text())
    elif mutation == "database":
        (output / "databases/committed-error.sqlite3").write_bytes(b"not SQLite")
        doc = json.loads(path.read_text())
    elif mutation == "native_flag":
        path = next((output / "inspect-logs").glob("*.json"))
        doc = json.loads(path.read_text())
        doc["status"] = "error"
    elif mutation == "probe_schema":
        path = output / "raw" / name
        doc = json.loads(path.read_text())
        doc["sandbox_probes"] = {"forged": True}
    else:
        doc = json.loads(path.read_text())
        doc["results"][0]["oracle"]["events"] = []
    path.write_text(canonical(doc))
    with pytest.raises((ValueError, KeyError)):
        verify(output)


def test_runner_seals_prediction_before_oracle(unit_evidence, tmp_path, monkeypatch):
    case = deepcopy(next(c for c in CASES if c["id"] == "committed-error"))
    raw = json.loads((unit_evidence / "raw/committed-error.json").read_text())
    # Reuse a native local-stub sample without running tools or Docker again.
    from inspect_ai.log import read_eval_log

    logs = [
        read_eval_log(str(p)) for p in (unit_evidence / "inspect-logs").glob("*.json")
    ]
    log = next(log for log in logs if log.samples[0].id == case["id"])
    real_capture = runner.Capture

    def prepared_capture(sample, gate, faults, override):
        gate.approvals = deepcopy(raw["approvals"])
        capture = real_capture(sample, gate, faults, override)
        capture.entries = deepcopy(raw["invocations"])
        return capture

    monkeypatch.setattr(runner, "Capture", prepared_capture)
    monkeypatch.setattr(runner, "eval", lambda *a, **kw: [log])
    (tmp_path / "databases").mkdir()
    shutil.copyfile(
        unit_evidence / "databases/committed-error.sqlite3",
        tmp_path / "databases/committed-error.sqlite3",
    )
    from inspect_v3_bridge import verify as verifier

    read = verifier.read_effects

    def read_after_seal(path, sample):
        sealed = json.loads((tmp_path / "sealed/committed-error.json").read_text())
        assert sealed["views"]["complete"]["prediction"] is True
        assert views(raw) == sealed["views"]
        return read(path, sample)

    monkeypatch.setattr(verifier, "read_effects", read_after_seal)
    assert runner.run_case(case, tmp_path)["views"]["complete"]["prediction"] is True
    case["expected_outcome"] = "no_forbidden_effect"
    # Oracle/fixture changes invalidate acceptance, never rewrite the sealed score.
    with pytest.raises(ValueError):
        acceptance(
            case,
            raw,
            json.loads((tmp_path / "sealed/committed-error.json").read_text()),
            tmp_path,
        )
    assert (
        json.loads((tmp_path / "sealed/committed-error.json").read_text())["views"][
            "complete"
        ]["prediction"]
        is True
    )
