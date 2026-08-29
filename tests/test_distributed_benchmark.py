from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from agent_eval_distributed.benchmark import (
    POSTGRES_IMAGE,
    build_load_plan,
    run_load_benchmark,
)

DSN = os.environ.get("AGENT_EVAL_TEST_POSTGRES_DSN")
pytestmark = pytest.mark.skipif(
    DSN is None, reason="PostgreSQL integration DSN not set"
)


def test_load_plan_is_canonical() -> None:
    first = build_load_plan(run_key="load", task_count=5)
    second = build_load_plan(run_key="load", task_count=5)
    assert first == second
    assert [task.ordinal for task in first.tasks] == list(range(5))
    with pytest.raises(ValueError, match="positive"):
        build_load_plan(run_key="load", task_count=0)


def test_multi_process_load_report_is_complete_and_dsn_free(
    tmp_path: Path,
) -> None:
    assert DSN is not None
    output = tmp_path / "metrics.json"
    report = run_load_benchmark(
        dsn=DSN,
        task_count=40,
        worker_count=4,
        lease_seconds=5,
        output=output,
        process_timeout_seconds=30,
        source_revision="test-revision",
    )
    assert report["task_count"] == 40
    assert report["queue_counts"] == {
        "pending": 0,
        "leased": 0,
        "complete": 40,
        "failed": 0,
    }
    assert report["database"]["attempts_total"] == 40
    assert report["database"]["attempts_complete"] == 40
    assert report["database"]["attempts_expired"] == 0
    assert report["database"]["maximum_attempts_per_task"] == 1
    assert report["duplicate_execution_attempts"] == 0
    assert report["idempotent_recommits"] == 0
    assert report["database_image"] == POSTGRES_IMAGE
    assert report["source_revision"] == "test-revision"
    assert report["throughput_tasks_per_second"] > 0
    assert report["task_latency_ms"]["p95"] >= report["task_latency_ms"]["p50"]
    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert DSN not in output.read_text(encoding="utf-8")
