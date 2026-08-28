import hashlib
import json
from pathlib import Path

from agent_eval_mutation_lab.baseline_lock import verify_lock


def test_committed_baseline_lock_matches() -> None:
    root = Path(__file__).resolve().parents[1]
    report = verify_lock(root / "artifacts/baseline-v1/LOCK.json", root)
    assert report["verified"] is True
    assert all(item["matches"] for item in report["files"])


def test_changed_file_fails_lock(tmp_path: Path) -> None:
    sample = tmp_path / "sample.txt"
    sample.write_text("changed", encoding="utf-8")
    expected = hashlib.sha256(b"original").hexdigest()
    lock = tmp_path / "LOCK.json"
    lock.write_text(
        json.dumps({"files": {"sample.txt": expected}}),
        encoding="utf-8",
    )
    report = verify_lock(lock, tmp_path)
    assert report["verified"] is False

