from pathlib import Path

from agent_eval_mutation_lab.review_packet import (
    build_blind_review_packet,
    write_review_packet,
)
from agent_eval_mutation_lab.review_verifier import (
    expected_review_labels,
    verify_review_submission,
)


def test_blind_packet_contains_no_expected_labels_or_scorer_outputs() -> None:
    packet, form = build_blind_review_packet()

    def keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {
                nested_key
                for nested_value in value.values()
                for nested_key in keys(nested_value)
            }
        if isinstance(value, list):
            return {
                nested_key for item in value for nested_key in keys(item)
            }
        return set()

    packet_keys = keys(packet)
    assert "expected" not in packet_keys
    assert "prediction" not in packet_keys
    assert "scorer" not in packet_keys
    assert len(packet["cases"]) == 13
    assert all(case["review_id"].startswith("R") for case in packet["cases"])
    assert all(label["attack_success"] == "" for label in form["labels"])


def test_review_packet_writes_deterministically(tmp_path: Path) -> None:
    first_paths = write_review_packet(tmp_path / "first")
    second_paths = write_review_packet(tmp_path / "second")
    for first, second in zip(first_paths, second_paths, strict=True):
        assert first.read_bytes() == second.read_bytes()


def _completed_submission() -> dict:
    _, form = build_blind_review_packet()
    expected = expected_review_labels()
    form["attestation"] = {
        "reviewer_pseudonym": "independent-reviewer",
        "independent_review_completed": True,
        "scorer_outputs_seen": False,
        "ground_truth_labels_seen": False,
        "ai_assistance_used": False,
        "review_notes": "test fixture only",
    }
    for label in form["labels"]:
        label.update(expected[label["review_id"]])
    return form


def test_review_verifier_accepts_exact_completed_submission() -> None:
    report = verify_review_submission(_completed_submission())
    assert report["complete"] is True
    assert report["attestation_passed"] is True
    assert report["review_passed"] is True
    assert report["case_agreement_rate"] == 1.0


def test_review_verifier_rejects_disagreement_and_blank_attestation() -> None:
    submission = _completed_submission()
    submission["labels"][0]["attack_success"] = "unknown"
    submission["attestation"]["independent_review_completed"] = False
    report = verify_review_submission(submission)
    assert report["review_passed"] is False
    assert report["attestation_passed"] is False
    assert report["matching_case_count"] < report["case_count"]
