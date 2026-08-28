"""Fail-closed preflight for the protected project ownership gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from agent_eval_mutation_lab.baseline_lock import verify_lock

SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ownership_preflight(
    root: Path,
    evidence_path: Path,
) -> dict[str, Any]:
    blockers: list[str] = []
    lock_path = root / "artifacts/baseline-v1/LOCK.json"
    lock_report = verify_lock(lock_path, root)
    if not lock_report["verified"]:
        blockers.append("frozen baseline-v1 lock does not verify")
    if not (root / "artifacts/v2/v1-v2-comparison.json").is_file():
        blockers.append("v2 comparison artifact is missing")
    if (root / "ownership/.ownership-gate-active").exists():
        blockers.append("an ownership-gate attempt is already active")

    evidence: dict[str, Any] = {}
    if not evidence_path.is_file():
        blockers.append("reviewed foundation evidence is missing")
    else:
        loaded = json.loads(evidence_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            blockers.append("foundation evidence must be a JSON object")
        else:
            evidence = loaded
            if evidence.get("foundation_checkpoint_passed") is not True:
                blockers.append("foundation checkpoint is not recorded as passed")
            if evidence.get("review_completed") is not True:
                blockers.append("foundation result review is not recorded as complete")
            if evidence.get("ai_assistance_used") is not False:
                blockers.append("foundation attempt must record no AI assistance")
            if evidence.get("attempt_kind") != "protected_blank_file":
                blockers.append("attempt_kind must be protected_blank_file")
            completed_at = evidence.get("completed_at")
            if not isinstance(completed_at, str) or not completed_at:
                blockers.append("completed_at is required")
            result_path_value = evidence.get("result_path")
            result_hash = evidence.get("result_sha256")
            if not isinstance(result_hash, str) or not SHA256.fullmatch(result_hash):
                blockers.append("result_sha256 must be a lowercase SHA-256 value")
            if not isinstance(result_path_value, str) or not result_path_value:
                blockers.append("result_path is required")
            else:
                result_path = Path(result_path_value)
                if not result_path.is_file():
                    blockers.append("foundation result_path does not exist")
                elif (
                    isinstance(result_hash, str)
                    and SHA256.fullmatch(result_hash)
                    and _sha256(result_path) != result_hash
                ):
                    blockers.append("foundation result hash does not match")

    return {
        "schema_version": 1,
        "ready": not blockers,
        "blockers": blockers,
        "baseline_lock_verified": lock_report["verified"],
        "foundation_evidence_path": str(evidence_path),
        "ownership_task_revealed": False,
        "rule": (
            "Do not reveal or start the ownership task while Codex or another AI "
            "surface is open."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check readiness for the protected ownership gate."
    )
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--foundation-evidence",
        type=Path,
        default=Path("ownership/FOUNDATION-EVIDENCE.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("ownership/OWNERSHIP-PREFLIGHT.json"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = ownership_preflight(args.root, args.foundation_evidence)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {args.output}")
    if not report["ready"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
