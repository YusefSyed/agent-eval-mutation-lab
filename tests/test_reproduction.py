from pathlib import Path

from agent_eval_mutation_lab.reproduction import (
    CORE_ARTIFACTS,
    build_core_artifacts,
    compare_core_artifacts,
    verify_reproduction,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_clean_reproduction_matches_committed_artifacts() -> None:
    report = verify_reproduction(PROJECT_ROOT)
    assert report["verified"] is True
    assert report["baseline_lock_verified"] is True
    assert report["artifact_count"] == len(CORE_ARTIFACTS)
    assert all(item["matches"] for item in report["artifacts"])


def test_comparison_fails_closed_on_missing_or_modified_artifact(
    tmp_path: Path,
) -> None:
    expected = tmp_path / "expected"
    generated = tmp_path / "generated"
    build_core_artifacts(expected)
    build_core_artifacts(generated)

    changed = generated / CORE_ARTIFACTS[0]
    changed.write_text("not the benchmark result\n", encoding="utf-8")
    (generated / CORE_ARTIFACTS[-1]).unlink()

    checks = compare_core_artifacts(expected, generated)
    mismatches = {item.path: item for item in checks if not item.matches}
    assert set(mismatches) == {
        CORE_ARTIFACTS[0].as_posix(),
        CORE_ARTIFACTS[-1].as_posix(),
    }
    assert mismatches[CORE_ARTIFACTS[-1].as_posix()].generated_sha256 is None
