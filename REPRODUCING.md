# Reproducing the evidence

Agent Eval Mutation Lab is designed to reproduce from a clean checkout without a
model, API key, network call at runtime, private dataset, or manually prepared state.
The development environment uses `uv`; the installed package uses only Python's
standard library at runtime.

## Full verification

```bash
uv sync --frozen --dev
uv run --frozen ruff check .
uv run --frozen mypy
uv run --frozen coverage run -m pytest
uv run --frozen coverage report
uv run --frozen agent-eval-verify-lock
uv run --frozen agent-eval-reproduce --verify
```

The final command starts from an empty temporary directory, verifies the seven-file
frozen v1 lock, rebuilds the legacy reports and blind-review packet, executes the
104-task typed engine and 14-mutant development benchmark, and byte-compares 17
committed canonical artifacts. It does
not overwrite the working tree.

## Run the semantic mutation benchmark

```bash
uv run --frozen agent-eval-mutate-v2
```

The command refuses source-hash drift, first verifies the unmodified scorer through
the same snapshot boundary, and then runs one predeclared semantic mutant per child
process. Its stable JSON and Markdown outputs are written to
`artifacts/mutation-benchmark/`. Runtime durations are intentionally excluded from
the canonical evidence.

## Run or resume the advanced engine

```bash
uv run agent-eval-engine \
  --workers 1 \
  --output artifacts/engine/latest
```

That directory contains:

- `run.sqlite3`: a derived operational ledger for transactional resume;
- `objects/`: immutable task records addressed by their exact SHA-256 digest;
- `results.jsonl`: 104 canonical task records in plan order;
- `run-manifest.json`: semantic identity, source and plugin digests, task counts,
  and per-record digests;
- `report.html`: a static dependency-free evidence report; and
- `SHA256SUMS`: digests for the canonical export, manifest, and report.

Run the same command again with a different worker count:

```bash
uv run agent-eval-engine \
  --workers 4 \
  --output artifacts/engine/latest
```

The ledger should report 104 resumed tasks and zero executed tasks. Worker count,
completion order, cache timing, timestamps, absolute paths, and SQLite page layout
are deliberately excluded from semantic identity.

## Inspect the run ledger

```bash
sqlite3 artifacts/engine/latest/run.sqlite3 'PRAGMA integrity_check;'
sqlite3 artifacts/engine/latest/run.sqlite3 \
  'SELECT state, COUNT(*) FROM tasks GROUP BY state;'
sqlite3 artifacts/engine/latest/run.sqlite3 \
  'SELECT COUNT(*) FROM artifacts;'
```

A completed current snapshot returns `ok`, `complete|104`, and `104`. The database
is disposable and may differ at the byte level across equivalent runs; canonical
JSONL and manifest hashes are the scientific evidence.

## Verify exported bytes

```bash
cd artifacts/engine/latest
shasum -a 256 -c SHA256SUMS
```

All three entries should report `OK`. Current exact identities live in
`run-manifest.json`; documentation intentionally does not duplicate hashes that
change whenever semantic source code changes.

## Interruption test

The bounded flag below commits a partial run and exits nonzero by design:

```bash
uv run agent-eval-engine \
  --max-new-tasks 17 \
  --output /tmp/agent-eval-interrupted
```

Rerun the command without `--max-new-tasks`. The ledger reuses 17 digest-verified
records and executes the remaining 87. Tests also cover worker-count changes during
resume, out-of-order completion, corrupt-object quarantine, plugin exceptions, and
idempotent duplicate commits.
