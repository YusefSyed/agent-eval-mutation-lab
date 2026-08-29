"""Finite multi-process load benchmark for the PostgreSQL lease store."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from dataclasses import asdict, dataclass
from hashlib import sha256
from multiprocessing import get_context
from pathlib import Path
from queue import Empty
from typing import Any
from uuid import uuid4

import psycopg

from agent_eval_distributed.contracts import DistributedPlan, DistributedTask
from agent_eval_distributed.store import PostgresLeaseStore

POSTGRES_IMAGE = (
    "postgres@sha256:18cfe3ef5e6815560c98237d6216d1e5119702fb0f3894c8785dd58b8bbe5d73"
)


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkerReport:
    worker_id: str
    completed: int
    idempotent_recommits: int
    task_latencies_ns: tuple[int, ...]


def _task_payload(ordinal: int) -> bytes:
    return json.dumps(
        {"ordinal": ordinal, "schema": "distributed-load-task-v1"},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def build_load_plan(*, run_key: str, task_count: int) -> DistributedPlan:
    if task_count < 1:
        raise ValueError("task_count must be positive")
    tasks = tuple(
        DistributedTask.from_payload(
            task_key=f"load-task-{ordinal:08d}",
            ordinal=ordinal,
            payload=_task_payload(ordinal),
        )
        for ordinal in range(task_count)
    )
    return DistributedPlan.from_tasks(run_key=run_key, tasks=tasks)


def _worker_loop(
    *,
    dsn: str,
    run_key: str,
    worker_id: str,
    lease_seconds: float,
    reports: Any,
) -> None:
    store = PostgresLeaseStore(dsn, min_pool_size=1, max_pool_size=2)
    store.wait()
    latencies: list[int] = []
    completed = 0
    recommits = 0
    try:
        while True:
            started_ns = time.perf_counter_ns()
            lease = store.claim_next(
                run_key=run_key,
                worker_id=worker_id,
                lease_seconds=lease_seconds,
            )
            if lease is None:
                break
            result_digest = sha256(
                b"distributed-load-result-v1\0" + lease.payload
            ).hexdigest()
            newly_committed = store.complete(
                lease=lease,
                result_digest=result_digest,
            )
            latencies.append(time.perf_counter_ns() - started_ns)
            if newly_committed:
                completed += 1
            else:
                recommits += 1
        reports.put(
            WorkerReport(
                worker_id=worker_id,
                completed=completed,
                idempotent_recommits=recommits,
                task_latencies_ns=tuple(latencies),
            )
        )
    finally:
        store.close()


def _nearest_rank(values: tuple[int, ...], percentile: float) -> int:
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(percentile * len(ordered) + 0.999999) - 1))
    return ordered[index]


def _database_metrics(dsn: str, run_key: str) -> dict[str, Any]:
    with psycopg.connect(dsn) as connection:
        version = connection.execute("SHOW server_version").fetchone()
        attempts = connection.execute(
            "SELECT count(*), count(*) FILTER (WHERE outcome = 'complete'), "
            "count(*) FILTER (WHERE outcome = 'expired') "
            "FROM agent_eval.attempts WHERE run_key = %s",
            (run_key,),
        ).fetchone()
        maximum = connection.execute(
            "SELECT COALESCE(max(attempt_count), 0) FROM agent_eval.tasks "
            "WHERE run_key = %s",
            (run_key,),
        ).fetchone()
    if version is None or attempts is None or maximum is None:
        raise RuntimeError("PostgreSQL benchmark metrics were unavailable")
    return {
        "postgres_version": version[0],
        "attempts_total": attempts[0],
        "attempts_complete": attempts[1],
        "attempts_expired": attempts[2],
        "maximum_attempts_per_task": maximum[0],
    }


def run_load_benchmark(
    *,
    dsn: str,
    task_count: int,
    worker_count: int,
    lease_seconds: float,
    output: Path,
    process_timeout_seconds: float = 120.0,
    source_revision: str | None = None,
) -> dict[str, Any]:
    if not dsn or dsn != dsn.strip():
        raise ValueError("dsn must be non-empty and trimmed")
    if worker_count < 1:
        raise ValueError("worker_count must be positive")
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    if process_timeout_seconds <= 0:
        raise ValueError("process_timeout_seconds must be positive")
    if source_revision is not None and (
        not source_revision or source_revision != source_revision.strip()
    ):
        raise ValueError("source_revision must be non-empty and trimmed")

    run_key = f"distributed-load-{uuid4().hex}"
    plan = build_load_plan(run_key=run_key, task_count=task_count)
    coordinator = PostgresLeaseStore(dsn, min_pool_size=1, max_pool_size=4)
    coordinator.wait()
    coordinator.migrate()
    coordinator.register_plan(plan)

    context = get_context("spawn")
    reports = context.Queue()
    processes = [
        context.Process(
            target=_worker_loop,
            kwargs={
                "dsn": dsn,
                "run_key": run_key,
                "worker_id": f"worker-{index:02d}",
                "lease_seconds": lease_seconds,
                "reports": reports,
            },
            name=f"distributed-load-worker-{index:02d}",
        )
        for index in range(worker_count)
    ]

    started_ns = time.perf_counter_ns()
    try:
        for process in processes:
            process.start()
        deadline = time.monotonic() + process_timeout_seconds
        for process in processes:
            remaining = max(0.0, deadline - time.monotonic())
            process.join(timeout=remaining)
        unfinished = [process.name for process in processes if process.is_alive()]
        if unfinished:
            raise TimeoutError(f"workers exceeded timeout: {unfinished}")
        failed = {
            process.name: process.exitcode
            for process in processes
            if process.exitcode != 0
        }
        if failed:
            raise RuntimeError(f"workers failed: {failed}")
        worker_reports: list[WorkerReport] = []
        for _ in processes:
            try:
                worker_reports.append(reports.get(timeout=5))
            except Empty as error:
                raise RuntimeError("worker exited without a report") from error
    finally:
        for process in processes:
            if process.is_alive():
                process.kill()
                process.join(timeout=5)
        reports.close()

    elapsed_ns = time.perf_counter_ns() - started_ns
    counts = coordinator.counts(run_key=run_key)
    coordinator.close()
    latencies = tuple(
        latency for worker in worker_reports for latency in worker.task_latencies_ns
    )
    database = _database_metrics(dsn, run_key)
    completed = sum(worker.completed for worker in worker_reports)
    recommits = sum(worker.idempotent_recommits for worker in worker_reports)
    if counts.complete != task_count or counts.total != task_count:
        raise RuntimeError("benchmark did not produce one terminal task per plan item")
    if completed != task_count or len(latencies) != task_count:
        raise RuntimeError("worker reports do not match terminal task count")

    report: dict[str, Any] = {
        "schema": "distributed-load-benchmark-v1",
        "run_key": run_key,
        "plan_digest": plan.plan_digest,
        "task_count": task_count,
        "worker_count": worker_count,
        "lease_seconds": lease_seconds,
        "elapsed_seconds": elapsed_ns / 1_000_000_000,
        "throughput_tasks_per_second": task_count * 1_000_000_000 / elapsed_ns,
        "task_latency_ms": {
            "p50": _nearest_rank(latencies, 0.50) / 1_000_000,
            "p95": _nearest_rank(latencies, 0.95) / 1_000_000,
            "maximum": max(latencies) / 1_000_000,
        },
        "queue_counts": asdict(counts),
        "idempotent_recommits": recommits,
        "duplicate_execution_attempts": database["attempts_total"] - task_count,
        "database": database,
        "database_image": POSTGRES_IMAGE,
        "runtime": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "machine": platform.machine(),
            "platform": platform.platform(),
            "process_start_method": "spawn",
        },
        "worker_completed_counts": {
            worker.worker_id: worker.completed for worker in worker_reports
        },
    }
    if source_revision is not None:
        report["source_revision"] = source_revision
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(output)
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a finite multi-process PostgreSQL lease benchmark."
    )
    parser.add_argument(
        "--dsn",
        default=os.environ.get("AGENT_EVAL_POSTGRES_DSN"),
        help="PostgreSQL DSN; defaults to AGENT_EVAL_POSTGRES_DSN.",
    )
    parser.add_argument("--tasks", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--lease-seconds", type=float, default=5.0)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument(
        "--source-revision",
        default=os.environ.get("AGENT_EVAL_SOURCE_REVISION"),
        help="Optional immutable source revision recorded in the report.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/distributed-benchmark/latest/metrics.json"),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if not args.dsn:
        raise SystemExit("--dsn or AGENT_EVAL_POSTGRES_DSN is required")
    report = run_load_benchmark(
        dsn=args.dsn,
        task_count=args.tasks,
        worker_count=args.workers,
        lease_seconds=args.lease_seconds,
        output=args.output,
        process_timeout_seconds=args.timeout_seconds,
        source_revision=args.source_revision,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv[1:])
