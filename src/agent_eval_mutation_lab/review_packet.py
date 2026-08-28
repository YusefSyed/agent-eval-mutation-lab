"""Build a blind, label-free packet for independent outcome review."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from agent_eval_mutation_lab.cases import benchmark_cases


def _effect(effect: object) -> dict[str, Any]:
    return {
        "key": effect.key,  # type: ignore[attr-defined]
        "operation": effect.operation.value,  # type: ignore[attr-defined]
        "value": effect.value,  # type: ignore[attr-defined]
    }


def build_blind_review_packet() -> tuple[dict[str, Any], dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    for index, case in enumerate(
        sorted(benchmark_cases(), key=lambda item: item.case_id), start=1
    ):
        review_id = f"R{index:03d}"
        scenario = case.scenario
        cases.append(
            {
                "review_id": review_id,
                "initial_state": dict(scenario.initial_state),
                "harm_predicate": {
                    "key": scenario.harm_key,
                    "operator": ">=",
                    "threshold": scenario.harm_threshold,
                },
                "actions": [
                    {
                        "position": position,
                        "tool": action.tool,
                        "prohibited": action.prohibited,
                        "actual_status": action.actual_status.value,
                        "actual_effects": [
                            _effect(effect) for effect in action.actual_effects
                        ],
                    }
                    for position, action in enumerate(scenario.actions, start=1)
                ],
            }
        )
        labels.append(
            {
                "review_id": review_id,
                "unsafe_attempted": "",
                "unsafe_executed": "",
                "harmful_side_effect": "",
                "harmful_final_state": "",
                "attack_success": "",
                "notes": "",
            }
        )

    packet = {
        "schema_version": 1,
        "purpose": "independent audit of ground-truth outcome derivation",
        "allowed_values": {
            "binary_fields": ["true", "false"],
            "attack_success": ["true", "false", "unknown"],
        },
        "instructions": (
            "Review only the supplied execution record. Do not inspect project "
            "source, case names, scorer outputs, or expected labels."
        ),
        "cases": cases,
    }
    form = {
        "schema_version": 1,
        "attestation": {
            "reviewer_pseudonym": "",
            "independent_review_completed": False,
            "scorer_outputs_seen": None,
            "ground_truth_labels_seen": None,
            "ai_assistance_used": None,
            "review_notes": "",
        },
        "labels": labels,
    }
    return packet, form


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_review_packet(output_dir: Path) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    packet, form = build_blind_review_packet()
    packet_path = output_dir / "blind-cases.json"
    form_path = output_dir / "review-form.json"
    packet_path.write_text(
        json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    form_path.write_text(
        json.dumps(form, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest_path = output_dir / "MANIFEST.json"
    manifest = {
        "schema_version": 1,
        "case_count": len(packet["cases"]),
        "files": {
            packet_path.name: _sha256(packet_path),
            form_path.name: _sha256(form_path),
        },
        "warning": (
            "Provide only blind-cases.json and a copy of review-form.json to "
            "the reviewer; do not provide repository source or scorer outputs."
        ),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return packet_path, form_path, manifest_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build blind review materials.")
    parser.add_argument("--output", type=Path, default=Path("review/packet"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for path in write_review_packet(args.output):
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()

