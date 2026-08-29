from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from agent_eval_distributed.contracts import (
    DistributedPlan,
    DistributedTask,
    RunCounts,
    TaskLease,
)


def _task(ordinal: int) -> DistributedTask:
    return DistributedTask.from_payload(
        task_key=f"task-{ordinal}", ordinal=ordinal, payload=f"{ordinal}".encode()
    )


def test_plan_requires_canonical_unique_tasks() -> None:
    plan = DistributedPlan.from_tasks(run_key="run", tasks=(_task(0), _task(1)))
    assert [task.ordinal for task in plan.tasks] == [0, 1]

    with pytest.raises(ValueError, match="contiguous"):
        DistributedPlan.from_tasks(run_key="run", tasks=(_task(1),))
    with pytest.raises(ValueError, match="unique"):
        DistributedPlan.from_tasks(
            run_key="run",
            tasks=(_task(0), replace(_task(1), task_key="task-0")),
        )
    with pytest.raises(ValueError, match="does not match"):
        replace(plan, plan_digest="0" * 64)


def test_task_and_lease_reject_payload_digest_drift() -> None:
    task = _task(0)
    with pytest.raises(ValueError, match="does not match"):
        replace(task, payload=b"changed")

    lease = TaskLease(
        run_key="run",
        task_key=task.task_key,
        ordinal=task.ordinal,
        payload=task.payload,
        payload_digest=task.payload_digest,
        worker_id="worker-1",
        token=uuid4(),
        attempt_no=1,
        expires_at=datetime.now(UTC),
    )
    with pytest.raises(ValueError, match="does not match"):
        replace(lease, payload=b"changed")
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(lease, expires_at=datetime.now())


def test_run_counts_derive_terminal_and_total() -> None:
    counts = RunCounts(pending=3, leased=2, complete=4, failed=1)
    assert counts.terminal == 5
    assert counts.total == 10
