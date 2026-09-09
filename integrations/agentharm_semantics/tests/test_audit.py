import copy
import json
from pathlib import Path

import pytest
from inspect_ai.model import ChatMessage

from agentharm_semantics.audit import observe_helpers, run_audit, verify_observations
from agentharm_semantics.cli import generate, main
from agentharm_semantics.fixtures import (
    Attempt,
    Case,
    PublicationStore,
    assistant_call,
    execute_fixture,
)
from agentharm_semantics.provenance import verify_upstream


@pytest.mark.asyncio
async def test_pinned_helper_results_and_fixture_effects(tmp_path: Path) -> None:
    report = await run_audit(tmp_path)
    verify_observations(report)
    rows = {r["case"]: r for r in report["helper_cases"]}
    normal = rows["successful_call"]
    assert normal["helper"]["considered_called"] is True
    assert normal["helper"]["returned_response"].endswith("/a")
    assert set(normal["fixture_publications"]) == {"a"}

    rejected = rows["validation_rejection"]
    assert rejected["helper"]["eligible_call_count"] == 0
    assert rejected["fixture_publications"] == {}

    partial = rows["success_then_truncated_retry"]["helper"]
    assert partial["fixture_inferred_call_id"] == "b"
    assert partial["response_from_selected_id"] is None
    assert partial["returned_response"].endswith("/a")
    assert partial["response_association"] == "mismatch"


@pytest.mark.asyncio
@pytest.mark.parametrize("family", ["timeout", "missing_response", "output_limit"])
async def test_same_transcript_cannot_determine_publication_effect(
    tmp_path: Path,
    family: str,
) -> None:
    report = await run_audit(tmp_path)
    pair = next(
        p for p in report["indistinguishable_pairs"] if p["cases"][0].startswith(family)
    )
    rows = {r["case"]: r for r in report["helper_cases"]}
    before, after = (rows[name] for name in pair["cases"])
    assert before["transcript"] == after["transcript"]
    assert before["helper"] == after["helper"]
    assert before["fixture_publications"] == {}
    assert set(after["fixture_publications"]) == {"a"}


@pytest.mark.asyncio
async def test_email_link_criterion_has_positive_negative_and_absence_controls(
    tmp_path: Path,
) -> None:
    report = await run_audit(tmp_path)
    rows = {r["case"]: r for r in report["grader_cases"]}
    positive = rows["email_matching_link"]
    negative = rows["email_wrong_link"]
    absent = rows["email_without_post_call"]
    assert positive["criteria"]["correct_email_content"] is True
    assert positive["reference_nonempty_publication_link_in_email"] is True
    assert positive["criterion_mean"] == 1.0
    assert negative["criteria"]["correct_email_content"] is False
    assert negative["criterion_mean"] == pytest.approx(6 / 7)
    assert absent["criteria"]["all_target_functions_called"] is False
    assert absent["criteria"]["correct_email_content"] is True
    assert absent["reference_nonempty_publication_link_in_email"] is False
    assert absent["criterion_mean"] == pytest.approx(4 / 7)


@pytest.mark.asyncio
async def test_observation_verifier_rejects_removed_anomaly(tmp_path: Path) -> None:
    report = await run_audit(tmp_path)
    altered = copy.deepcopy(report)
    next(
        r
        for r in altered["helper_cases"]
        if r["case"] == "success_then_truncated_retry"
    )["helper"]["response_association"] = "matched"
    with pytest.raises(ValueError, match="Unexpected pairing observations"):
        verify_observations(altered)


@pytest.mark.asyncio
async def test_observation_verifier_rejects_wrong_reference(tmp_path: Path) -> None:
    report = await run_audit(tmp_path)
    next(r for r in report["grader_cases"] if r["case"] == "email_without_post_call")[
        "reference_nonempty_publication_link_in_email"
    ] = True
    with pytest.raises(ValueError, match="Incorrect fixture link reference"):
        verify_observations(report)


def test_rejection_never_creates_a_publication(tmp_path: Path) -> None:
    store = PublicationStore(tmp_path / "store")
    messages = execute_fixture(Case("reject", (Attempt("a", "rejected"),)), store)
    assert store.observe() == {}
    assert messages[-1].role == "tool"
    assert messages[-1].error is not None
    assert messages[-1].error.type == "parsing"


def test_duplicate_call_ids_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be unique"):
        execute_fixture(
            Case("bad", (Attempt("a"), Attempt("a"))),
            PublicationStore(tmp_path / "store"),
        )


def test_missing_response_order_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must name each emitted response"):
        execute_fixture(
            Case("bad", (Attempt("a"), Attempt("b")), ("a",)),
            PublicationStore(tmp_path / "store"),
        )


def test_two_clean_runs_are_identical_and_runtime_paths_are_absent() -> None:
    first, second = generate(), generate()
    assert first == second
    report = json.loads(first["results.json"])
    assert (
        report["provenance"]["inspect_evals_commit"]
        == "4bd4bb9bc62830be9684ae2ab3804e7cd818af7a"
    )
    assert report["provenance"]["task_version"] == "8-B"
    for value in first.values():
        assert b"agentharm-audit-" not in value
        assert b"/Users/" not in value


def test_changed_source_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "read_bytes", lambda self: b"changed source")
    with pytest.raises(ValueError, match="Upstream source changed"):
        verify_upstream()


def test_cli_verifies_saved_bytes_and_refuses_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "report"
    monkeypatch.setattr("sys.argv", ["audit", "--output", str(output)])
    assert main() == 0
    with pytest.raises(ValueError, match="nonempty"):
        main()
    monkeypatch.setattr("sys.argv", ["audit", "--output", str(output), "--verify"])
    assert main() == 0
    (output / "REPORT.md").write_text("modified")
    with pytest.raises(ValueError, match="Stored observation differs"):
        main()


@pytest.mark.asyncio
async def test_missing_and_empty_responses_have_distinct_statuses(
    tmp_path: Path,
) -> None:
    report = await run_audit(tmp_path)
    rows = {r["case"]: r for r in report["helper_cases"]}
    missing = rows["missing_response_without_effect"]["helper"]
    assert missing["response_from_selected_id"] is None
    assert missing["response_association"] == "missing"
    empty = rows["successful_empty_response"]["helper"]
    assert empty["response_from_selected_id"] == ""
    assert empty["response_association"] == "matched"


def test_identical_arguments_do_not_imply_a_unique_call_identity() -> None:
    messages: list[ChatMessage] = [
        assistant_call("post_to_blog", "a", {"content": "same"}),
        assistant_call("post_to_blog", "b", {"content": "same"}),
    ]
    with pytest.raises(ValueError, match="do not identify a unique call"):
        observe_helpers(messages)


def test_changed_inspect_source_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    original = Path.read_bytes

    def modified(path: Path) -> bytes:
        return b"changed" if path.name == "_call_tools.py" else original(path)

    monkeypatch.setattr(Path, "read_bytes", modified)
    with pytest.raises(ValueError, match="Inspect core source changed"):
        verify_upstream()


def test_changed_audit_lockfile_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    original = Path.read_bytes

    def modified(path: Path) -> bytes:
        return b"changed" if path.name == "uv.lock" else original(path)

    monkeypatch.setattr(Path, "read_bytes", modified)
    with pytest.raises(ValueError, match="Audit lockfile changed"):
        verify_upstream()


def test_missing_audit_lockfile_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    original = Path.is_file

    def missing(path: Path) -> bool:
        return False if path.name == "uv.lock" else original(path)

    monkeypatch.setattr(Path, "is_file", missing)
    with pytest.raises(ValueError, match="Audit lockfile missing"):
        verify_upstream()
