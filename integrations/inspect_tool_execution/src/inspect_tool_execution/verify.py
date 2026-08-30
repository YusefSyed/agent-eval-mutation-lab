"""Re-score exported databases and compare deterministic evidence without Docker."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .effect_scorer import read_effects
from .policy import ID
from .provenance import PROJECT, source_hashes


def verify(directory: Path) -> dict[str, str]:
    report_file = directory / "normalized-report.json"
    report = json.loads(report_file.read_text())
    if report["source_sha256"] != source_hashes():
        raise ValueError("recorded source identity differs from current source")
    cases = {
        case["id"]: case for case in json.loads((PROJECT / "cases.json").read_text())
    }
    result_ids = [result["case_id"] for result in report["results"]]
    if (
        len(result_ids) != len(cases)
        or set(result_ids) != set(cases)
        or report.get("full_suite") is not True
    ):
        raise ValueError("full-suite verification requires the exact fixture case IDs")
    hashes = {
        "normalized-report.json": hashlib.sha256(report_file.read_bytes()).hexdigest()
    }
    seen = set()
    for result in report["results"]:
        sample_id = result["case_id"]
        if not ID.fullmatch(sample_id) or sample_id in seen:
            raise ValueError("invalid or duplicate sample identity")
        seen.add(sample_id)
        case = cases[sample_id]
        path = directory / "databases" / f"{sample_id}.sqlite3"
        observed = read_effects(path, sample_id)
        if observed["outcome"] == "unknown" or observed != result["effects"]:
            raise ValueError(f"effect re-score mismatch: {sample_id}")
        # Saved expected_* flags are diagnostics, not acceptance evidence.
        effects_match = (
            observed["outcome"] == case["expected_outcome"]
            and len(observed["events"]) == case["expected_events"]
            and observed["final_published"] == case["expected_final"]
        )
        expected_dispatch = [
            {"function": call["function"], "error_type": error}
            for call, error in zip(
                case["calls"], case["expected_tool_errors"], strict=True
            )
        ]
        dispatch_match = (
            result["tool_execution"] == expected_dispatch
            and result["approvals"] == case["expected_approval_records"]
        )
        if not effects_match or not dispatch_match:
            raise ValueError(f"independent fixture acceptance failed: {sample_id}")
        if (
            result["expected_effects_match"] is not True
            or result["expected_dispatch_match"] is not True
        ):
            raise ValueError(f"recorded acceptance flags disagree: {sample_id}")
        hashes[str(path.relative_to(directory))] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    actual = {p.stem for p in (directory / "databases").glob("*.sqlite3")}
    if actual != seen:
        raise ValueError("database/report sample sets differ")
    for key in (
        "all_expected_effects_match",
        "all_expected_dispatch_match",
        "all_acceptance_checks_pass",
    ):
        if report[key] is not True:
            raise ValueError(
                "recorded suite flags disagree with independent acceptance"
            )
    return hashes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    hashes = verify(args.directory)
    if args.compare and hashes != verify(args.compare):
        raise ValueError("normalized reports or raw database bytes differ")
    print(
        json.dumps(
            {
                "verified_files": len(hashes),
                "comparison_identical": bool(args.compare),
                "sha256": hashes,
            },
            sort_keys=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
