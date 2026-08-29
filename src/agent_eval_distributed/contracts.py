"""Typed contracts for the optional leased distributed executor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from uuid import UUID


def _nonempty(value: str, name: str) -> str:
    if not value or value != value.strip():
        raise ValueError(f"{name} must be non-empty and trimmed")
    return value


def _digest(value: str, name: str) -> str:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


@dataclass(frozen=True, slots=True, kw_only=True)
class DistributedTask:
    """One immutable task registered in canonical plan order."""

    task_key: str
    ordinal: int
    payload: bytes
    payload_digest: str

    def __post_init__(self) -> None:
        _nonempty(self.task_key, "task_key")
        if self.ordinal < 0:
            raise ValueError("ordinal must be non-negative")
        _digest(self.payload_digest, "payload_digest")
        if sha256(self.payload).hexdigest() != self.payload_digest:
            raise ValueError("payload_digest does not match payload bytes")

    @classmethod
    def from_payload(
        cls, *, task_key: str, ordinal: int, payload: bytes
    ) -> DistributedTask:
        return cls(
            task_key=task_key,
            ordinal=ordinal,
            payload=payload,
            payload_digest=sha256(payload).hexdigest(),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class DistributedPlan:
    """A content-identified run and its canonical task sequence."""

    run_key: str
    plan_digest: str
    tasks: tuple[DistributedTask, ...]

    def __post_init__(self) -> None:
        _nonempty(self.run_key, "run_key")
        _digest(self.plan_digest, "plan_digest")
        expected_ordinals = tuple(range(len(self.tasks)))
        actual_ordinals = tuple(task.ordinal for task in self.tasks)
        if actual_ordinals != expected_ordinals:
            raise ValueError("task ordinals must be contiguous canonical order")
        task_keys = tuple(task.task_key for task in self.tasks)
        if len(set(task_keys)) != len(task_keys):
            raise ValueError("task keys must be unique within a plan")
        if plan_digest_for(self.tasks) != self.plan_digest:
            raise ValueError("plan_digest does not match canonical tasks")

    @classmethod
    def from_tasks(
        cls, *, run_key: str, tasks: tuple[DistributedTask, ...]
    ) -> DistributedPlan:
        return cls(
            run_key=run_key,
            plan_digest=plan_digest_for(tasks),
            tasks=tasks,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskLease:
    """Capability token granting one worker temporary commit authority."""

    run_key: str
    task_key: str
    ordinal: int
    payload: bytes
    payload_digest: str
    worker_id: str
    token: UUID
    attempt_no: int
    expires_at: datetime

    def __post_init__(self) -> None:
        _nonempty(self.run_key, "run_key")
        _nonempty(self.task_key, "task_key")
        _nonempty(self.worker_id, "worker_id")
        if self.ordinal < 0:
            raise ValueError("ordinal must be non-negative")
        if self.attempt_no < 1:
            raise ValueError("attempt_no must be positive")
        _digest(self.payload_digest, "payload_digest")
        if sha256(self.payload).hexdigest() != self.payload_digest:
            raise ValueError("payload_digest does not match payload bytes")
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError("expires_at must be timezone-aware")


@dataclass(frozen=True, slots=True, kw_only=True)
class RunCounts:
    pending: int
    leased: int
    complete: int
    failed: int

    def __post_init__(self) -> None:
        if min(self.pending, self.leased, self.complete, self.failed) < 0:
            raise ValueError("run counts must be non-negative")

    @property
    def terminal(self) -> int:
        return self.complete + self.failed

    @property
    def total(self) -> int:
        return self.pending + self.leased + self.terminal


class DistributedStoreInvariantError(RuntimeError):
    """Stored plan or terminal identity differs from immutable input."""


class LeaseLostError(RuntimeError):
    """A worker attempted to mutate a lease it no longer owns."""


def plan_digest_for(tasks: tuple[DistributedTask, ...]) -> str:
    """Hash canonical task identity with unambiguous length framing."""

    digest = sha256(b"agent-eval-distributed-plan-v1\0")
    for task in tasks:
        for field in (
            task.ordinal.to_bytes(8, "big"),
            task.task_key.encode(),
            task.payload_digest.encode(),
        ):
            digest.update(len(field).to_bytes(8, "big"))
            digest.update(field)
    return digest.hexdigest()
