"""Command-line interface for the resumable deterministic engine."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_eval_mutation_lab.engine.artifacts import ContentAddressedStore
from agent_eval_mutation_lab.engine.contracts import RunState
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
from agent_eval_mutation_lab.v2_evaluation import run_v2_comparison


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the typed, resumable execution-semantic evaluation engine."
    )
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--output", type=Path, default=Path("artifacts/engine/latest")
    )
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--max-in-flight", type=int)
    parser.add_argument("--max-new-tasks", type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    output = args.output
    if not output.is_absolute():
        output = root / output
    plugins = default_scorer_plugins()
    plan = plan_run(build_default_run_spec(root), plugins=plugins)
    summary = run_resumable(
        plan,
        store=SqliteRunStore(output / "run.sqlite3"),
        artifacts=ContentAddressedStore(output / "objects"),
        plugins=plugins,
        workers=args.workers,
        max_in_flight=args.max_in_flight,
        max_new_tasks=args.max_new_tasks,
    )
    if summary.state is RunState.COMPLETE:
        assert_legacy_v2_equivalence(summary.records, run_v2_comparison())
    paths = write_run_artifacts(plan, summary, output, plugins=plugins)
    print(
        json.dumps(
            {
                "state": summary.state.value,
                "run_key": plan.run_key,
                "expected_tasks": summary.expected_tasks,
                "completed_tasks": summary.completed_tasks,
                "failed_tasks": summary.failed_tasks,
                "executed_tasks": summary.executed_tasks,
                "resumed_tasks": summary.resumed_tasks,
                "outputs": [str(path) for path in paths],
            },
            indent=2,
            sort_keys=True,
        )
    )
    if summary.state is not RunState.COMPLETE:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
