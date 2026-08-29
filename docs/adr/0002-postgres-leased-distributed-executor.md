# ADR 0002: PostgreSQL leases for distributed execution

## Status

Proposed and executable on an isolated feature branch.
No public distributed-systems claim is permitted until the crash and load
benchmarks are committed and reproduced.

## Decision

Use PostgreSQL as an optional operational coordination layer. Keep the existing
canonical task identity and content-addressed result bytes authoritative.

Workers claim one task at a time using `SELECT ... FOR UPDATE SKIP LOCKED` in a
short transaction. A claim increments an attempt counter and issues a UUID lease
token with an expiry. Computation occurs after commit and outside every database
transaction. Heartbeats extend only a live lease. Completion requires the current
worker, token, attempt number, and unexpired lease; the token fences late workers
after expiry or reassignment.

Expired work is reclaimed in canonical ordinal order. Reclaiming marks the prior
attempt expired before issuing a new token. Identical terminal recommits are
idempotent; a different digest for an already complete task fails loudly.

The base package remains dependency-free. PostgreSQL support is installed through
the `distributed` optional extra and uses a bounded connection pool with statement,
lock, and idle-transaction timeouts.

The backend lives in the separate top-level `agent_eval_distributed` package,
outside the deterministic engine's hashed package tree. Its own plan and payload
digests define distributed identity; changing it cannot silently rewrite the
identity of the 17 existing canonical local-engine artifacts.

Plan identity uses length-framed task ordinals, task keys, and payload digests.
Concurrent coordinators may register the same plan idempotently; the database
rejects a run key reused with different plan bytes or cardinality.

## Why PostgreSQL

- It provides durable transactions, row locks, constraints, and `SKIP LOCKED`
  without introducing a separate queue and state database.
- The complete task and attempt history can be inspected with ordinary SQL.
- Partial indexes cover pending and expired-lease scans without indexing terminal
  rows unnecessarily.
- The design can be exercised locally with multiple independent worker processes
  before any claim about a deployed cluster.

## Rejected alternatives

- SQLite cannot coordinate independent hosts and its single-writer behavior does
  not establish a distributed queue.
- An in-memory queue cannot survive process termination.
- Redis Streams would still require a separate authoritative terminal ledger and
  a cross-system consistency design.
- A framework-managed executor would hide the lease, fencing, and idempotency
  contracts this experiment is intended to test.

## Required evidence before promotion

1. Concurrent workers claim distinct tasks without blocking each other.
2. Killing a worker after claim causes bounded lease recovery.
3. The killed worker cannot heartbeat or commit after reassignment.
4. Every task has one canonical terminal digest despite duplicate execution
   attempts.
5. Sequential, healthy multi-worker, interrupted, and resumed runs export
   byte-identical semantic artifacts.
6. A finite load benchmark reports throughput, p50/p95 latency, lease-recovery
   time, duplicate attempts, duplicate terminal commits, queue depth, and exact
   machine/runtime configuration.

The healthy-load command writes a DSN-free JSON report and uses independent
spawned Python processes. Forced termination remains a separate acceptance test
so healthy throughput is not conflated with recovery latency.
