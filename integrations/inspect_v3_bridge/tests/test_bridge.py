"""Negative evidence boundaries and all 13 unchanged registry fixtures."""

import json
import shutil
from copy import deepcopy
from dataclasses import asdict

import pytest
from conftest import CASES, producer, registry
from inspect_tool_execution.effect_scorer import read_effects

from inspect_v3_bridge.projection import canonical, project, views
from inspect_v3_bridge.verify import acceptance


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_all_fixture_parity_and_views(case, execute_fixture, tmp_path):
    raw, database = execute_fixture(case)
    (tmp_path / "databases").mkdir()
    shutil.copyfile(database, tmp_path / "databases" / (case["id"] + ".sqlite3"))
    seal = {"sample_id": case["id"], "views": views(raw)}
    result = acceptance(case, raw, seal, tmp_path)
    assert result["expected_effects_match"]
    # Full typed projection has no private identity/labels/faults/database/text.
    serialized = canonical(
        {"trajectory": asdict(project(raw)[0]), "contract": asdict(project(raw)[1])}
    )
    for forbidden in (
        "expected_outcome",
        "oracle",
        "request-one",
        "invocation-",
        "sample_id",
        "before_commit",
        "after_commit",
        ".sqlite3",
    ):
        assert forbidden not in serialized
    for name, view in seal["views"].items():
        if name in {"drop_receipts", "omit_publication_action"}:
            assert view["prediction"] is None


def test_identical_counterfactual(execute_fixture):
    left = execute_fixture(next(c for c in CASES if c["id"] == "precommit-error"))
    right = execute_fixture(next(c for c in CASES if c["id"] == "committed-error"))
    assert (
        views(left[0])["omit_publication_action"]
        == views(right[0])["omit_publication_action"]
    )
    assert (
        read_effects(left[1], left[0]["sample_id"])["outcome"]
        != read_effects(right[1], right[0]["sample_id"])["outcome"]
    )


def test_text_and_expected_labels_do_not_enter_prediction(execute_fixture):
    case = deepcopy(next(c for c in CASES if c["id"] == "tampered-tool-text"))
    raw, _ = execute_fixture(case)
    original = views(raw)
    case["id"] = "changed-case"
    case["tool_response_override"] = "I published it"
    case["assistant_text"] = "different claim"
    case["expected_outcome"] = "different truth"
    changed, _ = execute_fixture(case)
    assert views(changed) == original


@pytest.mark.parametrize(
    "mutation",
    [
        "sample",
        "request",
        "invocation",
        "effects",
        "status",
        "completeness",
        "extra",
        "overlap",
        "terminal",
        "native_id",
        "approval_args",
        "wrapper_args",
    ],
)
def test_malformed_or_uncorrelated_evidence_rejected(mutation, execute_fixture):
    raw, _ = execute_fixture(next(c for c in CASES if c["id"] == "committed-error"))
    receipt = raw["receipts"]["invocation-0"]
    if mutation == "sample":
        receipt["sample_id"] = "other"
    elif mutation == "request":
        receipt["arguments"] = dict(receipt["arguments"], request_id="other")
    elif mutation == "invocation":
        receipt["invocation_id"] = "other"
    elif mutation == "effects":
        receipt["effects"][0]["value"] = True
    elif mutation == "status":
        receipt["disposition"] = "failed"
    elif mutation == "completeness":
        receipt["effects_complete"] = False
    elif mutation == "extra":
        raw["receipts"]["other"] = deepcopy(receipt)
    elif mutation == "overlap":
        raw["native"]["single_call_turns"] = False
    elif mutation == "terminal":
        raw["native"]["terminal"] = False
    elif mutation == "native_id":
        raw["native"]["events"][0]["id"] = "other"
    elif mutation == "approval_args":
        raw["approvals"][0]["proposed"] = {}
    elif mutation == "wrapper_args":
        raw["invocations"][0]["arguments"] = {}
    with pytest.raises(ValueError):
        project(raw)


def test_missing_receipt_is_unknown(execute_fixture):
    raw, _ = execute_fixture(next(c for c in CASES if c["id"] == "committed-error"))
    raw["receipts"] = {}
    assert views(raw)["complete"]["prediction"] is None


def test_conflicting_request_and_duplicate_receipts(execute_fixture):
    raw, _ = execute_fixture(next(c for c in CASES if c["id"] == "conflicting-reuse"))
    assert raw["receipts"]["invocation-1"]["disposition"] == "unknown"
    assert views(raw)["complete"]["prediction"] is None
    duplicate, _ = execute_fixture(
        next(c for c in CASES if c["id"] == "retry-after-commit")
    )
    assert duplicate["receipts"]["invocation-0"]["disposition"] == "partial"
    assert duplicate["receipts"]["invocation-1"]["effects"] == []
    duplicate["receipts"]["invocation-1"]["effects"] = duplicate["receipts"][
        "invocation-0"
    ]["effects"]
    with pytest.raises(ValueError):
        project(duplicate)


def test_receipt_reservation_failure_prevents_mutation(tmp_path):
    db = tmp_path / "registry.sqlite3"
    registry.initialize(db, "sample")
    directory = tmp_path / "not-a-directory"
    directory.write_text("blocked")
    with pytest.raises(OSError):
        producer.produce(
            db,
            directory,
            "sample",
            "invocation-0",
            "publish_artifact",
            {"artifact_id": "protected-draft", "request_id": "request-one"},
        )
    assert read_effects(db, "sample")["outcome"] == "no_forbidden_effect"


def test_exclusive_receipt_paths(tmp_path):
    db = tmp_path / "registry.sqlite3"
    registry.initialize(db, "sample")
    args = {"artifact_id": "public-report", "request_id": "request-one"}
    directory = tmp_path / "receipts"
    producer.produce(db, directory, "sample", "invocation-0", "publish_artifact", args)
    with pytest.raises(FileExistsError):
        producer.produce(
            db, directory, "sample", "invocation-0", "publish_artifact", args
        )
    assert json.loads((directory / "invocation-0.json").read_text())["effects"]


def test_missing_first_retry_receipt_retains_uncertainty(execute_fixture):
    raw, _ = execute_fixture(next(c for c in CASES if c["id"] == "retry-after-commit"))
    del raw["receipts"]["invocation-0"]
    assert views(raw)["complete"]["prediction"] is None


def test_duplicate_invocation_different_request_cannot_mutate(tmp_path):
    db = tmp_path / "registry.sqlite3"
    registry.initialize(db, "sample")
    directory = tmp_path / "receipts"
    producer.produce(
        db,
        directory,
        "sample",
        "invocation-0",
        "publish_artifact",
        {"artifact_id": "public-report", "request_id": "request-one"},
    )
    before = read_effects(db, "sample")
    with pytest.raises(FileExistsError):
        producer.produce(
            db,
            directory,
            "sample",
            "invocation-0",
            "publish_artifact",
            {"artifact_id": "protected-draft", "request_id": "request-two"},
        )
    assert read_effects(db, "sample") == before


@pytest.mark.parametrize(
    "case",
    [c for c in CASES if c["expected_outcome"] == "forbidden_effect"],
    ids=lambda c: c["id"],
)
@pytest.mark.parametrize(
    "transform", ["drop_effect_records", "omit_publication_action"]
)
def test_acceptance_rejects_correlated_transform_false_certainty(
    case, transform, execute_fixture, tmp_path, monkeypatch
):
    from inspect_v3_bridge import verify as verifier

    raw, database = execute_fixture(case)
    (tmp_path / "databases").mkdir()
    shutil.copyfile(database, tmp_path / "databases" / (case["id"] + ".sqlite3"))
    tampered_views = views(raw)
    tampered_views[transform]["prediction"] = False
    # Simulate a transform/scorer regression shared by report and recomputation.
    # Independent semantic acceptance must reject even when those agree.
    monkeypatch.setattr(verifier, "views", lambda observed: deepcopy(tampered_views))
    sealed = {"sample_id": case["id"], "views": deepcopy(tampered_views)}
    with pytest.raises(ValueError, match="withheld .* produced unwarranted certainty"):
        verifier.acceptance(case, raw, sealed, tmp_path)


def test_receipt_write_failure_after_reservation_remains_invalid(tmp_path, monkeypatch):
    from pathlib import Path

    db = tmp_path / "registry.sqlite3"
    registry.initialize(db, "sample")
    directory = tmp_path / "receipts"
    open_file = Path.open

    class FailedWrite:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def write(self, value):
            raise OSError("injected telemetry write failure")

    def reserve_then_fail(path, mode="r", *args, **kwargs):
        stream = open_file(path, mode, *args, **kwargs)
        return FailedWrite(stream) if mode == "x" else stream

    monkeypatch.setattr(Path, "open", reserve_then_fail)
    with pytest.raises(OSError, match="injected telemetry write failure"):
        producer.produce(
            db,
            directory,
            "sample",
            "invocation-0",
            "publish_artifact",
            {"artifact_id": "protected-draft", "request_id": "request-one"},
        )
    assert read_effects(db, "sample")["outcome"] == "forbidden_effect"
    with pytest.raises(json.JSONDecodeError):
        json.loads((directory / "invocation-0.json").read_text())


def test_generic_unknown_projects_missing_receipt(execute_fixture):
    raw, _ = execute_fixture(next(c for c in CASES if c["id"] == "conflicting-reuse"))
    assert raw["receipts"]["invocation-1"]["disposition"] == "unknown"
    assert project(raw)[0].actions[1].receipt is None
