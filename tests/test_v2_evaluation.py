import json
from pathlib import Path

from agent_eval_mutation_lab.v2_evaluation import (
    render_markdown,
    run_v2_comparison,
    write_v2_reports,
)


def test_v2_eliminates_observed_false_safe_without_automatic_guilt() -> None:
    report = run_v2_comparison()
    baseline = report["conditions"]["baseline"]
    removed_effects = report["conditions"]["remove_effect_records"]
    v2_baseline = baseline["evidence_dominance_v2_experimental"]["metrics"]
    v1_removed = removed_effects["receipt_aware_v1_frozen"]["metrics"]
    v2_removed = removed_effects["evidence_dominance_v2_experimental"][
        "metrics"
    ]

    assert v2_baseline["tri_state_accuracy"] == 1.0
    assert v2_removed["false_safe_count"] == 0
    assert v2_removed["false_success_count"] == 0
    assert v2_removed["unsupported_safe_count"] == 0
    assert v2_removed["unsupported_success_count"] == 0
    assert v1_removed["false_safe_count"] > v2_removed["false_safe_count"]
    assert v2_removed["unnecessary_abstention_count"] > 0


def test_v2_report_round_trip_is_deterministic(tmp_path: Path) -> None:
    first = run_v2_comparison()
    second = run_v2_comparison()
    assert first == second
    json_path, markdown_path = write_v2_reports(first, tmp_path)
    assert json.loads(json_path.read_text(encoding="utf-8")) == first
    assert markdown_path.read_text(encoding="utf-8") == render_markdown(first)

