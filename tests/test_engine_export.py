import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

from agent_eval_mutation_lab.engine.aggregation import aggregate_records
from agent_eval_mutation_lab.engine.artifacts import ContentAddressedStore
from agent_eval_mutation_lab.engine.contracts import ExecutionSummary, RunPlan
from agent_eval_mutation_lab.engine.export import write_run_artifacts
from agent_eval_mutation_lab.engine.planner import (
    build_default_run_spec,
    plan_run,
)
from agent_eval_mutation_lab.engine.plugins import (
    ScorerPlugin,
    default_scorer_plugins,
)
from agent_eval_mutation_lab.engine.runtime import run_resumable
from agent_eval_mutation_lab.engine.store import SqliteRunStore
from agent_eval_mutation_lab.v2_evaluation import run_v2_comparison

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _complete_run(
    root: Path, *, workers: int
) -> tuple[RunPlan, ExecutionSummary, Mapping[str, ScorerPlugin]]:
    plugins = default_scorer_plugins()
    plan = plan_run(build_default_run_spec(PROJECT_ROOT), plugins=plugins)
    summary = run_resumable(
        plan,
        store=SqliteRunStore(root / "run.sqlite3"),
        artifacts=ContentAddressedStore(root / "objects"),
        plugins=plugins,
        workers=workers,
    )
    return plan, summary, plugins


def test_engine_aggregates_match_legacy_metrics(tmp_path: Path) -> None:
    _, summary, _ = _complete_run(tmp_path, workers=1)
    actual = aggregate_records(summary.records)
    legacy = run_v2_comparison()
    expected = {
        condition: {
            scorer_id: scorer["metrics"]
            for scorer_id, scorer in scorers.items()
        }
        for condition, scorers in legacy["conditions"].items()
    }
    assert actual == expected


def test_exports_are_worker_independent_and_self_verifying(
    tmp_path: Path,
) -> None:
    plan_one, summary_one, plugins_one = _complete_run(
        tmp_path / "one", workers=1
    )
    plan_four, summary_four, plugins_four = _complete_run(
        tmp_path / "four", workers=4
    )
    paths_one = write_run_artifacts(
        plan_one,
        summary_one,
        tmp_path / "one/export",
        plugins=plugins_one,
    )
    paths_four = write_run_artifacts(
        plan_four,
        summary_four,
        tmp_path / "four/export",
        plugins=plugins_four,
    )

    assert [path.name for path in paths_one] == [path.name for path in paths_four]
    assert [path.read_bytes() for path in paths_one] == [
        path.read_bytes() for path in paths_four
    ]

    results_path, manifest_path, report_path, sums_path = paths_one
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "complete"
    assert manifest["canonical_record_count"] == 104
    assert manifest["results_sha256"] == hashlib.sha256(
        results_path.read_bytes()
    ).hexdigest()
    assert len(results_path.read_text(encoding="utf-8").splitlines()) == 104
    html = report_path.read_text(encoding="utf-8")
    assert "Did the attack execute" in html
    assert "https://" not in html
    assert "http://" not in html

    for line in sums_path.read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", maxsplit=1)
        assert digest == hashlib.sha256(
            (sums_path.parent / name).read_bytes()
        ).hexdigest()


def test_incomplete_export_suppresses_qualified_evidence(tmp_path: Path) -> None:
    plugins = default_scorer_plugins()
    plan = plan_run(build_default_run_spec(PROJECT_ROOT), plugins=plugins)
    summary = run_resumable(
        plan,
        store=SqliteRunStore(tmp_path / "run.sqlite3"),
        artifacts=ContentAddressedStore(tmp_path / "objects"),
        plugins=plugins,
        max_new_tasks=5,
    )
    _, manifest_path, report_path, _ = write_run_artifacts(
        plan, summary, tmp_path / "export", plugins=plugins
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "interrupted"
    assert manifest["warning"].startswith("INCOMPLETE RUN")
    assert "INCOMPLETE" in report_path.read_text(encoding="utf-8")
