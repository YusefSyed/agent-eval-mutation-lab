import hashlib
import json
from pathlib import Path

from agent_eval_mutation_lab.ownership_readiness import ownership_preflight


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_missing_foundation_evidence_keeps_gate_blocked(tmp_path: Path) -> None:
    report = ownership_preflight(_repo_root(), tmp_path / "missing.json")
    assert report["ready"] is False
    assert report["ownership_task_revealed"] is False
    assert "reviewed foundation evidence is missing" in report["blockers"]


def test_valid_preserved_foundation_result_can_clear_preflight(tmp_path: Path) -> None:
    result = tmp_path / "foundation-result.json"
    result.write_text('{"status":"passed"}\n', encoding="utf-8")
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "attempt_kind": "protected_blank_file",
                "foundation_checkpoint_passed": True,
                "review_completed": True,
                "ai_assistance_used": False,
                "completed_at": "2026-09-01T12:00:00Z",
                "result_path": str(result),
                "result_sha256": hashlib.sha256(result.read_bytes()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    report = ownership_preflight(_repo_root(), evidence)
    assert report["ready"] is True
    assert report["blockers"] == []
    assert report["ownership_task_revealed"] is False


def test_tampered_foundation_result_fails_preflight(tmp_path: Path) -> None:
    result = tmp_path / "foundation-result.json"
    result.write_text("original", encoding="utf-8")
    original_hash = hashlib.sha256(result.read_bytes()).hexdigest()
    result.write_text("tampered", encoding="utf-8")
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "attempt_kind": "protected_blank_file",
                "foundation_checkpoint_passed": True,
                "review_completed": True,
                "ai_assistance_used": False,
                "completed_at": "2026-09-01T12:00:00Z",
                "result_path": str(result),
                "result_sha256": original_hash,
            }
        ),
        encoding="utf-8",
    )
    report = ownership_preflight(_repo_root(), evidence)
    assert report["ready"] is False
    assert "foundation result hash does not match" in report["blockers"]

