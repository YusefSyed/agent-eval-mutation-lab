# ADR 0001: deterministic local engine with a transactional run ledger

- **Status:** accepted
- **Date:** 2026-08-28
- **Scope:** advanced engine milestone; frozen v1 remains unchanged

## Context

The original benchmark was scientifically careful but sequential and in-memory. A
credible advanced-Python extension needed to add systems depth without pretending a
13-case offline workload required a distributed platform.

## Decision

Build one bounded local pipeline:

```text
immutable RunSpec
  -> canonical TaskPlan
  -> scorer-visible whitelist projection
  -> explicit typed scorer plugin
  -> coordinator-only oracle rejoin and validation
  -> single-writer transactional SQLite ledger
  -> content-addressed immutable task records
  -> canonical ordered JSONL and static evidence report
```

The system remains a standard-library-only local library and CLI. `workers=1` is the
reference path. A bounded thread executor exists only to verify schedule-independent
semantics and isolation; workers never write SQLite and never receive oracle truth.

SQLite is derived operational state, not the scientific hash target. Canonical
identity comes from source and plugin digests, immutable task inputs, per-task result
digests, plan order, and semantic configuration.

## Accepted invariants

- Frozen v1 files and hashes remain byte-identical.
- Scorers receive a new immutable whitelist projection, never a wrapper containing
  simulator truth, expected labels, a store handle, or a full case object.
- Oracle truth is rejoined only after a score is finalized.
- A valid `unknown` result is distinct from parsing, plugin, storage, or worker
  failure.
- Task randomness is derived from task identity rather than shared consumption
  order.
- Worker count, completion order, interruption point, and warm/cold cache state do
  not change canonical results.
- Duplicate task keys with different result bytes fail loudly.
- Corrupt objects are quarantined and recomputed, never consumed silently.
- Incomplete runs are visibly marked and cannot masquerade as completed evidence.

## Rejected alternatives

- **Mandatory asyncio API:** no network fan-out or naturally asynchronous workload
  exists; async syntax would be ornamental.
- **Process pool:** the current work is extremely small, and serialization overhead
  would dominate. Only one measured backend is supported.
- **Network service or remote workers:** no multi-user or deployment requirement.
- **Generic event sourcing/CQRS:** durable immutable task commits are sufficient for
  resume; rebuilding the application from an abstract event stream is not.
- **Dynamic entry-point discovery:** there is no external plugin consumer. Explicit
  in-process registration is easier to audit.
- **Inferential statistics:** 13 hand-authored cases are not an independent sample.
- **Frontend framework:** a static dependency-free report exposes the evidence with
  less attack surface and no deployment requirement.

## Measured concurrency decision

A local Python 3.13.14 profile executed 250 repetitions of the 104-task matrix.
Sequential execution took 0.067487 seconds; a fresh four-thread executor per trial
took 0.170682 seconds, or 2.529× the sequential time. This measurement is diagnostic,
not a stable performance benchmark. It falsified a speed claim and justified keeping
parallelism as an opt-in correctness stress mode.

## Consequences

Positive:

- the project now demonstrates immutable data modeling, Protocol-based interfaces,
  canonical serialization, hashing, transactional SQLite, atomic file publication,
  idempotency, bounded concurrency, resume, cache validation, and static reporting;
- every existing v1/v2 case result remains exactly equivalent;
- a reviewer can inspect or reproduce each layer without external services.

Costs:

- more types and storage invariants must remain synchronized;
- conservative source hashing causes harmless cache misses after semantic source
  changes;
- the operational database is intentionally not byte-reproducible;
- concurrency adds correctness surface without a throughput benefit on this tiny
  corpus.

## Rollback

The legacy sequential commands remain intact. If engine equivalence fails, stop
before using its exports. If persistence fails, the canonical task plan can still run
in memory. If parallel equivalence fails, retain `workers=1`. The SQLite database and
object cache are disposable and may be rebuilt from source; frozen v1 is never
modified as part of rollback.
