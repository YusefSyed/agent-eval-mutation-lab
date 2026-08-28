"""Clean-room regeneration and byte-level verification of core artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agent_eval_mutation_lab.baseline_lock import verify_lock
from agent_eval_mutation_lab.benchmark import run_benchmark as run_finite_benchmark
from agent_eval_mutation_lab.engine.artifacts import ContentAddressedStore
from agent_eval_mutation_lab.engine.equivalence import (
    assert_legacy_v2_equivalence,
)
from agent_eval_mutation_lab.engine.export import write_run_artifacts
from agent_eval_mutation_lab.engine.planner import (
    build_default_run_spec,
    plan_run,
)
from agent_eval_mutation_lab.engine.plugins import default_scorer_plugins
from agent_eval_mutation_lab.engine.runtime import run_resumable
from agent_eval_mutation_lab.engine.store import SqliteRunStore
from agent_eval_mutation_lab.family_sensitivity import (
    run_family_sensitivity,
    write_family_reports,
)
from agent_eval_mutation_lab.mutation_benchmark.benchmark import (
    run_benchmark as run_mutation_benchmark,
)
from agent_eval_mutation_lab.mutation_benchmark.benchmark import (
    write_reports as write_mutation_reports,
)
from agent_eval_mutation_lab.mutation_benchmark.catalog import load_manifest
from agent_eval_mutation_lab.receipt_ablations import (
    run_receipt_ablations,
    write_ablation_reports,
)
from agent_eval_mutation_lab.report import write_reports as write_finite_reports
from agent_eval_mutation_lab.review_packet import write_review_packet
from agent_eval_mutation_lab.v2_evaluation import (
    run_v2_comparison,
    write_v2_reports,
)

CORE_ARTIFACTS = (
    Path("artifacts/latest/results.json"),
    Path("artifacts/latest/results.md"),
    Path("artifacts/ablations/receipt-ablations.json"),
    Path("artifacts/ablations/receipt-ablations.md"),
    Path("artifacts/v2/v1-v2-comparison.json"),
    Path("artifacts/v2/v1-v2-comparison.md"),
    Path("artifacts/v2/family-sensitivity.json"),
    Path("artifacts/v2/family-sensitivity.md"),
    Path("artifacts/mutation-benchmark/semantic-mutations.json"),
    Path("artifacts/mutation-benchmark/semantic-mutations.md"),
    Path("review/packet/blind-cases.json"),
    Path("review/packet/review-form.json"),
    Path("review/packet/MANIFEST.json"),
    Path("artifacts/engine/latest/results.jsonl"),
    Path("artifacts/engine/latest/run-manifest.json"),
    Path("artifacts/engine/latest/report.html"),
    Path("artifacts/engine/latest/SHA256SUMS"),
)


@dataclass(frozen=True, slots=True)
class ArtifactCheck:
    """One expected/generated artifact comparison."""

    path: str
    expected_sha256: str | None
    generated_sha256: str | None
    matches: bool


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_core_artifacts(
    output_root: Path, *, project_root: Path | None = None
) -> tuple[Path, ...]:
    """Regenerate every deterministic core artifact below ``output_root``."""

    source_root = (
        Path(__file__).resolve().parents[2]
        if project_root is None
        else project_root.resolve()
    )
    write_finite_reports(
        run_finite_benchmark(), output_root / "artifacts/latest"
    )
    write_ablation_reports(
        run_receipt_ablations(), output_root / "artifacts/ablations"
    )
    write_v2_reports(run_v2_comparison(), output_root / "artifacts/v2")
    write_family_reports(run_family_sensitivity(), output_root / "artifacts/v2")
    mutation_manifest = load_manifest(
        source_root / "benchmarks/mutations-v2-development.json"
    )
    write_mutation_reports(
        run_mutation_benchmark(source_root, mutation_manifest),
        output_root / "artifacts/mutation-benchmark",
    )
    write_review_packet(output_root / "review/packet")
    engine_output = output_root / "artifacts/engine/latest"
    plugins = default_scorer_plugins()
    plan = plan_run(build_default_run_spec(source_root), plugins=plugins)
    summary = run_resumable(
        plan,
        store=SqliteRunStore(engine_output / "run.sqlite3"),
        artifacts=ContentAddressedStore(engine_output / "objects"),
        plugins=plugins,
    )
    assert_legacy_v2_equivalence(summary.records, run_v2_comparison())
    write_run_artifacts(plan, summary, engine_output, plugins=plugins)
    return tuple(output_root / relative for relative in CORE_ARTIFACTS)


def compare_core_artifacts(
    expected_root: Path, generated_root: Path
) -> tuple[ArtifactCheck, ...]:
    """Compare committed and cleanly regenerated artifacts by SHA-256."""

    checks = []
    for relative in CORE_ARTIFACTS:
        expected = _sha256(expected_root / relative)
        generated = _sha256(generated_root / relative)
        checks.append(
            ArtifactCheck(
                path=relative.as_posix(),
                expected_sha256=expected,
                generated_sha256=generated,
                matches=expected is not None and expected == generated,
            )
        )
    return tuple(checks)


def verify_reproduction(project_root: Path) -> dict[str, Any]:
    """Regenerate in an empty directory and verify all committed evidence."""

    project_root = project_root.resolve()
    lock = verify_lock(
        project_root / "artifacts/baseline-v1/LOCK.json", project_root
    )
    with tempfile.TemporaryDirectory(prefix="agent-eval-reproduce-") as raw_dir:
        generated_root = Path(raw_dir)
        build_core_artifacts(generated_root, project_root=project_root)
        checks = compare_core_artifacts(project_root, generated_root)

    verified = bool(lock["verified"]) and all(check.matches for check in checks)
    return {
        "schema_version": 1,
        "verified": verified,
        "baseline_lock_verified": bool(lock["verified"]),
        "artifact_count": len(checks),
        "artifacts": [asdict(check) for check in checks],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Regenerate deterministic benchmark evidence in a clean directory "
            "and verify it byte-for-byte."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Repository root containing committed artifacts.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Explicit verification mode (also the default behavior).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Regenerate artifacts below this directory instead of verifying.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.output is not None:
        paths = build_core_artifacts(args.output)
        print(json.dumps([str(path) for path in paths], indent=2))
        return

    report = verify_reproduction(args.root)
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["verified"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
