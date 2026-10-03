# Partial-evidence scoring with actual tools

The v3 scorer now has reproducible evidence from native Inspect execution and
actual Docker/SQLite tools. Thirteen scripted cases ran twice in fresh sandboxes;
normalized observations, predictions, reports and database bytes were identical.
The downloaded CI evidence also passed the independent offline verifier locally.

[Executed source](https://github.com/YusefSyed/agent-eval-mutation-lab/tree/a5c9d67f97a10ed8104235ab46976e4252eb82bc)
and [successful CI run](https://github.com/YusefSyed/agent-eval-mutation-lab/actions/runs/37105281221).
See [provenance](PROVENANCE.json), [hash comparison](proof-comparison.json),
[raw first-run report](run-one/normalized-report.json) and
[protocol](../../../integrations/inspect_v3_bridge/PROTOCOL.md).

## What the integration establishes

The same proposed publication can fail before a commit or commit before its
response fails. Model/tool response text cannot distinguish these outcomes.
The producer records private per-invocation effects; the scorer consumes a strict
projection of those receipts and an explicit evidence-completeness contract.
Predictions are sealed before the verifier reads the independent SQLite oracle.

The existing 13 cases cover denial, approval modification, rollback,
commit-before-response failure, publish-then-revoke, retry deduplication,
conflicting request IDs and misleading tool response text. Complete evidence
supports 12 correct binary decisions; the conflicting-request case remains unknown.

Each actual execution produces five evidence views:

| View | Harm | No harm | Unknown |
| --- | ---: | ---: | ---: |
| Complete producer evidence | 5 | 7 | 1 |
| Effect records withheld | 0 | 4 | 9 |
| All receipts withheld | 0 | 0 | 13 |
| Publication actions omitted | 0 | 0 | 13 |
| Positive effects retained with other gaps | 5 | 0 | 8 |

Across 65 views per run, all 21 binary decisions agree with the DB oracle and
44 abstain. These are related views of 13 scripted executions, not 65 independent
samples. In particular, before-commit failure and committed-response failure
have byte-identical scorer inputs after publication actions are omitted, opposite
oracle outcomes, and unknown predictions. Cleanup does not erase prior harm.

## Reproduce and verify

From the repository root, verification needs Python 3.12+ and uv; it makes no
model calls and does not require Docker:

```sh
cd integrations/inspect_v3_bridge
uv sync --frozen --dev
uv run --frozen inspect-v3-verify ../../artifacts/inspect-v3-bridge/v1/run-one \
  --compare ../../artifacts/inspect-v3-bridge/v1/run-two
```

To execute fresh tools, Docker must be running:

```sh
uv run --frozen inspect-v3-bridge --output tmp/fresh-one
uv run --frozen inspect-v3-bridge --output tmp/fresh-two
uv run --frozen inspect-v3-verify tmp/fresh-one --compare tmp/fresh-two
```

CI also passed 73 bridge tests, 40 unchanged legacy tests, all 17 frozen core
artifact checks, Ruff, strict projection typing and the legacy actual-tool
baseline. The core Python 3.12, 3.13 and 3.14 jobs passed separately. Sandbox
probes confirmed nonroot execution, read-only root, no network route, no effective
capabilities, no host home/socket and no provider keys.

## Limits

This is finite scripted integration evidence using Inspect's mock model, not a
live-model evaluation, independent human review or production reliability result.
The fixed producer and host harness are trusted. Receipt writes are not atomic
with SQLite commits; missing or malformed telemetry cannot certify safety.
Hashes show internal consistency and source identity, not hardware attestation.
Native logs retain timestamps and IDs; only normalized evidence is compared
byte-for-byte. The earlier synthetic enumeration and frozen v1/v2 studies remain
separate, unchanged results.
