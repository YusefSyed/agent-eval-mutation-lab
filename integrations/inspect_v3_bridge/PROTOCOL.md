# Inspect v3 bridge protocol

This additive package uses the legacy 13 fixtures and exact argument approval
policy with native Inspect `mockllm/model` output and isolated actual Docker tools.
It makes no hosted model calls. A successful acceptance run is finite scripted
integration evidence, not live model behavior or production validation.

The producer imports the unchanged legacy registry. Host-assigned invocation IDs
are distinct from logical request IDs. Each private sidecar is exclusively reserved before any SQL mutation and binds sample,
invocation, effective function and effective arguments. A normal committed mutation
has one ordered SET effect; an idempotent retry has a complete empty effect list.
Only the exact injected before-commit rollback certifies FAILED/no effect. The
controlled after-commit path commits through `fault=none`, writes PARTIAL evidence,
and then loses the response. Generic exceptions certify no completeness and project to a missing receipt. A receipt
write failure after commit leaves an invalid incomplete sidecar and remains a telemetry gap; writes are not transactionally
atomic with SQLite.

The model can supply only exposed tool arguments. It cannot choose receipt paths,
invocation IDs, faults, completeness or snapshot commands. Sandbox configuration
matches the legacy fixed image digest, nonroot user, no network/capabilities/host
mounts, read-only root and bounded tmpfs/CPU/memory/processes. Dockerfile-specific
context rules allow only the registry, snapshot helper and producer/build files.

Native assistant call IDs and native tool event IDs/arguments/errors reconcile with
approvals, wrapper entries and sidecars. Inspect records proposed event arguments
on approval modification; wrapper entries record the actual effective arguments.
Only successful termination, one call per turn, completed nonoverlapping events
and exact reconciliation establish complete action records. Fixture expected calls
are used afterward for acceptance, not to establish observation completeness.

The strict typed scorer sees neutral IDs, an initial protected publication flag of
zero, threshold one, receipts and a completeness contract. It receives no final
snapshot, fixture labels, faults, logical request IDs, SQLite history, DB paths,
model text or tool response text. Its prediction is exclusively created on disk
before the independent read-only SQLite oracle opens the transported DB snapshot.

Each of the 13 executions generates five views: complete, no receipts, publication
actions omitted, effect records omitted, and positive evidence with other gaps.
Removing entire actions disables action completeness; removing effects disables
success and partial effect completeness. Precommit and committed-error publication
omission views have identical full scorer inputs and unknown predictions despite
opposite oracle outcomes. Views are not additional executions or model samples.

Offline verification reads native logs, raw capture and exclusive seals, recomputes
projection/views/predictions, validates exact case coverage and source hashes, and
independently checks SQLite plus expected legacy dispatch/approval behavior. Saved
report flags or normalized oracle effects never stand in for raw evidence. Two-run
comparison includes observation, contract, prediction, report and DB snapshot bytes;
native timestamps/log UUIDs are retained but excluded from deterministic comparison.
These hashes verify consistency and source identity, not hardware attestation or
protection against an adversary rewriting an entire evidence bundle and its sources.

From this directory:

```text
uv sync --frozen --dev
uv run --frozen ruff check .
uv run --frozen mypy
uv run --frozen pytest
uv run --frozen inspect-v3-bridge --output tmp/run-one
uv run --frozen inspect-v3-bridge --output tmp/run-two
uv run --frozen inspect-v3-verify tmp/run-one --compare tmp/run-two
uv run --frozen agent-eval-reproduce --root ../.. --verify
uv run --frozen pytest ../inspect_tool_execution/tests
```

Unit tests exercise the actual registry and producer locally and native Inspect
mock loops with local stubs; temporary offline-verifier fixtures explicitly use
those stubs. They are not Docker isolation acceptance. The CI workflow runs the
unchanged legacy Docker baseline and then all 13 bridge cases twice in fresh
output directories. It uploads raw native logs/captures, seals, reports, snapshots
and proof comparison, including partial output on failure. Only successful remote
execution and offline verification authorize publishing versioned evidence under
`artifacts/inspect-v3-bridge/v1`.
