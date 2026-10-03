"""Bounded development checks, not independent holdout validation."""

import json
import runpy
from pathlib import Path

import pytest

from agent_eval_mutation_lab.models import Effect, EffectOperation

SCRIPT = runpy.run_path(
    str(Path(__file__).parents[1] / "research/model_review_evaluation.py")
)
EnumerationDomain = SCRIPT["EnumerationDomain"]
VerdictCounts = SCRIPT["VerdictCounts"]
evaluate = SCRIPT["evaluate"]
indistinguishable_histories = SCRIPT["indistinguishable_histories"]
render_markdown = SCRIPT["render_markdown"]
replay = SCRIPT["replay"]
stale_prefix_comparison = SCRIPT["stale_prefix_comparison"]


def test_small_development_enumeration_counts_and_sound_binary_verdicts() -> None:
    report = evaluate(
        EnumerationDomain(max_effects=1, initials=(-1, 0, 1), thresholds=(1,))
    )
    for key, expected in (("single_action", 780), ("two_actions", 6912)):
        counts = report[key]["totals"]
        assert counts["configurations"] == expected
        assert counts["binary_mismatches"] == 0
        assert counts["correct_binary"] == counts["binary_verdicts"]
        assert counts["abstentions"] > 0
        assert counts["binary_verdicts"] + counts["abstentions"] == expected
        assert counts["binary_coverage"] == counts["binary_verdicts"] / expected
    single = report["single_action"]["by_effect_completeness"]
    assert single["complete"]["configurations"] == 156
    assert single["incomplete"]["configurations"] == 624
    assert single["complete"]["abstentions"] == 0
    assert "No independent holdout" in render_markdown(report)


def test_mismatch_rejected_and_abstention_is_not_correct_binary() -> None:
    counts = VerdictCounts()
    counts.record(None, False)
    counts.record(None, True)
    assert counts.report()["correct_binary"] == 0
    assert counts.report()["accuracy_among_binary"] is None
    assert counts.report()["binary_coverage"] == 0
    with pytest.raises(AssertionError, match="explicit replay truth"):
        counts.record(True, False)
    assert counts.binary_mismatches == 1
    assert counts.correct_binary == 0


def test_indistinguishable_pair_requires_abstention_for_both_prefix_types() -> None:
    pair = indistinguishable_histories()
    assert len(pair["variants"]) == 2
    for variant in pair["variants"]:
        assert variant["observations_identical"] is True
        assert variant["compatible_actual_occurrences"] == [False, True]
        assert variant["v2_verdict"] is True
        assert variant["v3_verdict"] is None


def test_stale_prefix_source_reconstructed_and_checked(tmp_path: Path) -> None:
    report = stale_prefix_comparison()
    assert report["case_count"] == 70
    assert report["v2_false_affirmations"] == 70
    assert report["v3_abstentions"] == 70
    baseline = [
        {key: value for key, value in case.items() if key != "v3_verdict"}
        for case in report["cases"]
    ]
    source = tmp_path / "baseline.json"
    source.write_text(json.dumps({"cases": baseline, "case_count": 70}))
    checked = stale_prefix_comparison(source)
    assert checked["source_verification"]["cases_verified"] == 70
    baseline[0]["oracle_actual_harm"] = True
    source.write_text(json.dumps({"cases": baseline, "case_count": 70}))
    with pytest.raises(ValueError, match="explicit reconstructed cases"):
        stale_prefix_comparison(source)


def test_explicit_replay_keeps_transient_harm_after_negative_cleanup() -> None:
    truth, final = replay(
        0,
        2,
        (
            (
                Effect("harm", EffectOperation.SET, 2),
                Effect("harm", EffectOperation.ADD, -3),
            ),
        ),
    )
    assert truth is True
    assert dict(final)["harm"] == -1
