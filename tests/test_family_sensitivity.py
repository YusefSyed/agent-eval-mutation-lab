import json
from pathlib import Path

from agent_eval_mutation_lab.family_sensitivity import (
    render_markdown,
    run_family_sensitivity,
    write_family_reports,
)


def test_v2_directional_safety_survives_every_family_omission() -> None:
    report = run_family_sensitivity()
    for condition in report["conditions"].values():
        v2 = condition["evidence_dominance_v2_experimental"]
        assert v2["max_false_safe_count"] == 0
        assert v2["max_false_success_count"] == 0
        assert v2["max_unsupported_overclaim_count"] == 0


def test_family_report_is_deterministic(tmp_path: Path) -> None:
    first = run_family_sensitivity()
    second = run_family_sensitivity()
    assert first == second
    json_path, markdown_path = write_family_reports(first, tmp_path)
    assert json.loads(json_path.read_text(encoding="utf-8")) == first
    assert markdown_path.read_text(encoding="utf-8") == render_markdown(first)

