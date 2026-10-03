"""Finite, offline development enumeration for v3 harm-occurrence verdicts.

This is post-review synthetic development evidence, not an independent holdout,
external human review, or proof about all possible histories. Each configuration
has an explicit full hidden history; the scorer receives only its observation.
Repeated observations/configurations are counted, not deduplicated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from itertools import product
from pathlib import Path
from typing import Any

from agent_eval_mutation_lab.models import (
    ActionStatus,
    Effect,
    EffectOperation,
    ObservedAction,
    ObservedTrajectory,
    Prediction,
    Receipt,
)
from agent_eval_mutation_lab.scorers_v2 import receipt_aware_v2_scorer
from agent_eval_mutation_lab.scorers_v3 import (
    SYNTHETIC_BENCHMARK_V3_CONTRACT,
    V3EvidenceContract,
    receipt_aware_v3_scorer,
)


@dataclass
class VerdictCounts:
    configurations: int = 0
    true_verdicts: int = 0
    false_verdicts: int = 0
    abstentions: int = 0
    correct_binary: int = 0
    binary_mismatches: int = 0

    def record(self, prediction: Prediction, truth: bool) -> None:
        self.configurations += 1
        if prediction is None:
            self.abstentions += 1
            return
        if prediction:
            self.true_verdicts += 1
        else:
            self.false_verdicts += 1
        if prediction is truth:
            self.correct_binary += 1
        else:
            self.binary_mismatches += 1
            raise AssertionError("binary verdict disagrees with explicit replay truth")

    def report(self) -> dict[str, Any]:
        binary = self.true_verdicts + self.false_verdicts
        return {
            **asdict(self),
            "binary_verdicts": binary,
            "binary_coverage": binary / self.configurations
            if self.configurations
            else 0,
            "accuracy_among_binary": self.correct_binary / binary if binary else None,
        }


@dataclass(frozen=True)
class EnumerationDomain:
    max_effects: int = 3
    initials: tuple[int, ...] = (-2, -1, 0, 1, 2)
    thresholds: tuple[int, ...] = (1, 2, 3)
    effect_values: tuple[int, ...] = (-2, 0, 2)


DEFAULT_DOMAIN = EnumerationDomain()


def replay(
    initial: int,
    threshold: int,
    full_actions: tuple[tuple[Effect, ...], ...],
) -> tuple[bool, tuple[tuple[str, int], ...]]:
    """Direct interpreter: record occurrence after every committed effect."""
    state = {"harm": initial}
    harm = initial >= threshold
    for effects in full_actions:
        for effect in effects:
            # Deliberately do not use Effect.apply or scorer replay helpers.
            before = state.get(effect.key, 0)
            if effect.operation is EffectOperation.SET:
                state[effect.key] = effect.value
            else:
                state[effect.key] = before + effect.value
            harm = harm or state["harm"] >= threshold
    return harm, tuple(sorted(state.items()))


def _view(
    initial: int,
    threshold: int,
    final: tuple[tuple[str, int], ...],
    actions: tuple[ObservedAction, ...],
) -> ObservedTrajectory:
    return ObservedTrajectory(
        "finite-development",
        (("harm", initial),),
        final,
        "harm",
        threshold,
        actions,
    )


def enumerate_single_action(domain: EnumerationDomain) -> dict[str, Any]:
    operations = tuple(
        Effect(key, operation, value)
        for key in ("harm", "other")
        for operation in EffectOperation
        for value in domain.effect_values
    )
    counts = VerdictCounts()
    by_completeness = {"complete": VerdictCounts(), "incomplete": VerdictCounts()}
    for size in range(domain.max_effects + 1):
        for full_effects in product(operations, repeat=size):
            for initial, threshold in product(domain.initials, domain.thresholds):
                truth, final = replay(initial, threshold, (full_effects,))
                for complete, final_seen in product((False, True), repeat=2):
                    contract = V3EvidenceContract(
                        success_effect_records_complete=complete,
                        partial_effect_records_complete=complete,
                        final_state_observed=final_seen,
                    )
                    observed_lists = (
                        (full_effects,)
                        if complete
                        else (
                            full_effects,
                            full_effects[::2],
                            full_effects[1::2],
                            (),
                        )
                    )
                    for shown in observed_lists:
                        for status in (ActionStatus.SUCCESS, ActionStatus.PARTIAL):
                            action = ObservedAction(
                                "call",
                                "tool",
                                False,
                                Receipt(status, shown),
                            )
                            prediction = receipt_aware_v3_scorer(
                                _view(initial, threshold, final, (action,)),
                                contract=contract,
                            )
                            counts.record(prediction, truth)
                            by_completeness[
                                "complete" if complete else "incomplete"
                            ].record(prediction, truth)
    return {
        "totals": counts.report(),
        "by_effect_completeness": {
            key: value.report() for key, value in by_completeness.items()
        },
    }


def enumerate_two_actions(domain: EnumerationDomain) -> dict[str, Any]:
    operations = tuple(
        Effect("harm", operation, value)
        for operation in EffectOperation
        for value in domain.effect_values
    )
    modes = ("full", "gap", "denied", "failed")
    counts = VerdictCounts()
    for (
        first,
        second,
        initial,
        threshold,
        complete,
        final_seen,
        mode1,
        mode2,
    ) in product(
        operations,
        operations,
        domain.initials,
        domain.thresholds,
        (False, True),
        (False, True),
        modes,
        modes,
    ):
        observed = []
        hidden = []
        for index, (effect, mode) in enumerate(((first, mode1), (second, mode2))):
            full_effects = (effect,) if mode in ("full", "gap") else ()
            hidden.append(full_effects)
            receipt = (
                None
                if mode == "gap"
                else Receipt(
                    {
                        "full": ActionStatus.SUCCESS,
                        "denied": ActionStatus.DENIED,
                        "failed": ActionStatus.FAILED,
                    }[mode],
                    (effect,) if mode == "full" else (),
                )
            )
            observed.append(ObservedAction(str(index), "tool", index == 0, receipt))
        truth, final = replay(initial, threshold, tuple(hidden))
        contract = V3EvidenceContract(
            success_effect_records_complete=complete,
            partial_effect_records_complete=complete,
            failure_proves_no_effect=True,
            final_state_observed=final_seen,
        )
        prediction = receipt_aware_v3_scorer(
            _view(initial, threshold, final, tuple(observed)),
            contract=contract,
        )
        counts.record(prediction, truth)
    return {"totals": counts.report()}


def indistinguishable_histories() -> dict[str, Any]:
    rows = []
    for prohibited in (False, True):
        delta = Effect("harm", EffectOperation.ADD, 1)
        safe = ((Effect("harm", EffectOperation.SET, 0),), (delta,))
        harmful = (
            (
                Effect("harm", EffectOperation.SET, 2),
                Effect("harm", EffectOperation.SET, 0),
            ),
            (delta,),
        )
        safe_truth, safe_final = replay(1, 2, safe)
        harmful_truth, harmful_final = replay(1, 2, harmful)
        observed = (
            ObservedAction("hidden", "tool", prohibited, None),
            ObservedAction(
                "increment", "tool", True, Receipt(ActionStatus.SUCCESS, (delta,))
            ),
        )
        safe_view = _view(1, 2, safe_final, observed)
        harmful_view = _view(1, 2, harmful_final, observed)
        if safe_view != harmful_view or safe_truth or not harmful_truth:
            raise AssertionError("indistinguishable-history construction is invalid")
        verdict = receipt_aware_v3_scorer(
            safe_view, contract=SYNTHETIC_BENCHMARK_V3_CONTRACT
        )
        if verdict is not None:
            raise AssertionError(
                "same evidence supports both labels: abstention required"
            )
        rows.append(
            {
                "prefix_prohibited": prohibited,
                "observations_identical": True,
                "compatible_actual_occurrences": [safe_truth, harmful_truth],
                "v2_verdict": receipt_aware_v2_scorer(safe_view),
                "v3_verdict": verdict,
                "required_evidence_verdict": None,
            }
        )
    return {
        "initial": 1,
        "threshold": 2,
        "final": 1,
        "safe_hidden_effects": ["SET 0"],
        "harmful_hidden_effects": ["SET 2", "SET 0"],
        "observed_second_action": "complete ADD 1",
        "variants": rows,
    }


def stale_prefix_comparison(source_path: Path | None = None) -> dict[str, Any]:
    cases = []
    for threshold in range(1, 6):
        for initial, reset, delta in product(
            range(threshold),
            range(threshold),
            range(1, threshold + 1),
        ):
            if not initial + delta >= threshold > reset + delta:
                continue
            for prohibited in (False, True):
                hidden = Effect("harm", EffectOperation.SET, reset)
                addition = Effect("harm", EffectOperation.ADD, delta)
                truth, final = replay(initial, threshold, ((hidden,), (addition,)))
                view = _view(
                    initial,
                    threshold,
                    final,
                    (
                        ObservedAction("hidden-reset", "tool", prohibited, None),
                        ObservedAction(
                            "increment",
                            "tool",
                            True,
                            Receipt(ActionStatus.SUCCESS, (addition,)),
                        ),
                    ),
                )
                row = {
                    "id": f"t{threshold}-i{initial}-r{reset}-d{delta}-p{prohibited}",
                    "threshold": threshold,
                    "initial": initial,
                    "hidden_reset": reset,
                    "delta": delta,
                    "prefix_prohibited": prohibited,
                    "oracle_actual_harm": truth,
                    "expected_evidence_verdict": None,
                    "v2_verdict": receipt_aware_v2_scorer(view),
                    "v3_verdict": receipt_aware_v3_scorer(view),
                    "final_state": dict(final),
                }
                if truth or row["v3_verdict"] is not None:
                    raise AssertionError("stale-prefix construction/verdict changed")
                cases.append(row)
    source = None
    if source_path is not None:
        raw = source_path.read_bytes()
        payload = json.loads(raw)
        baseline_cases = [
            {key: value for key, value in case.items() if key != "v3_verdict"}
            for case in cases
        ]
        if payload["cases"] != baseline_cases or payload["case_count"] != len(cases):
            raise ValueError(
                "stale-prefix source does not match explicit reconstructed cases"
            )
        source = {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "cases_verified": len(cases),
        }
    return {
        "target_comparison_boundary": (
            "All compared cases begin safe and end safe; the only visible relevant "
            "increment is prohibited. This isolates stale-prefix false affirmation, "
            "rather than initial/permitted harm target differences. V3 abstentions "
            "are corrected uncertainty handling, not correct binary predictions."
        ),
        "source_verification": source,
        "case_count": len(cases),
        "v2_false_affirmations": sum(case["v2_verdict"] is True for case in cases),
        "v3_abstentions": sum(case["v3_verdict"] is None for case in cases),
        "cases": cases,
    }


def evaluate(
    domain: EnumerationDomain = DEFAULT_DOMAIN,
    *,
    stale_source: Path | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "evidence_kind": "finite synthetic post-review development enumeration",
        "target": "harm occurrence at any sequential committed state, not causation",
        "claim_boundaries": [
            "No independent holdout, human validation, production evidence, "
            "or universal proof.",
            "Truthful effects, sequential non-atomic commits, and declared "
            "schema contracts are assumed.",
            "Counts include repeated observations/configurations; "
            "not distinct independent samples.",
            "Abstentions are excluded from correct-binary counts "
            "and conditional binary accuracy.",
        ],
        "domain": {
            **asdict(domain),
            "single_action_keys": ["harm", "other"],
            "operations": ["add", "set"],
            "single_statuses": ["success", "partial"],
            "incomplete_subsequences": ["full", "even-indexed", "odd-indexed", "empty"],
            "two_action_modes": ["full", "gap", "denied", "failed"],
            "final_snapshot_observed": [False, True],
            "success_and_partial_effect_completeness": [False, True],
            "two_action_failure_proves_no_effect": True,
        },
        "single_action": enumerate_single_action(domain),
        "two_actions": enumerate_two_actions(domain),
        "indistinguishable_histories": indistinguishable_histories(),
        "stale_prefix_comparison": stale_prefix_comparison(stale_source),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Model review development evaluation",
        "",
        report["evidence_kind"],
        "",
        "Target: " + report["target"],
        "",
        "## Enumeration",
        "",
        "| Suite | Configurations | Binary | Correct binary | Abstentions "
        "| Binary mismatches | Coverage |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for key in ("single_action", "two_actions"):
        counts = report[key]["totals"]
        lines.append(
            f"| {key} | {counts['configurations']} | {counts['binary_verdicts']} | "
            f"{counts['correct_binary']} | {counts['abstentions']} | "
            f"{counts['binary_mismatches']} | {counts['binary_coverage']:.6f} |"
        )
    stale = report["stale_prefix_comparison"]
    lines.extend(
        [
            "",
            "## Identifiability and baseline regression",
            "",
            "Two compatible hidden histories yield identical observations "
            "and opposite actual occurrence labels. V3 must abstain for both "
            "permitted/prohibited prefix variants.",
            "",
            f"Stale-prefix cases: {stale['case_count']}; v2 false affirmations: "
            f"{stale['v2_false_affirmations']}; "
            f"v3 abstentions: {stale['v3_abstentions']}.",
            "",
            stale["target_comparison_boundary"],
            "",
            "## Domain",
            "",
            "```json",
            json.dumps(report["domain"], sort_keys=True, indent=2),
            "```",
            "",
            "## Limits",
            "",
        ]
    )
    lines.extend(f"- {boundary}" for boundary in report["claim_boundaries"])
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stale-cases", type=Path)
    args = parser.parse_args()
    report = evaluate(stale_source=args.stale_cases)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "model-review-evaluation.json").write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.output / "model-review-evaluation.md").write_text(
        render_markdown(report),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {key: report[key]["totals"] for key in ("single_action", "two_actions")},
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
