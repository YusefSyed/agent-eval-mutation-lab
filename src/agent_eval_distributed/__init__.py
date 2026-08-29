"""Optional fault-tolerant distributed execution primitives.

The base package remains dependency-free. Import ``distributed.store`` only when
the optional ``distributed`` extra and PostgreSQL are available.
"""

from agent_eval_distributed.contracts import (
    DistributedPlan,
    DistributedStoreInvariantError,
    DistributedTask,
    LeaseLostError,
    RunCounts,
    TaskLease,
)

__all__ = [
    "DistributedPlan",
    "DistributedStoreInvariantError",
    "DistributedTask",
    "LeaseLostError",
    "RunCounts",
    "TaskLease",
]
