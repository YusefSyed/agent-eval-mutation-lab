# Deterministic Inspect integration receipt

Generated 2026-08-30 from an isolated worktree based on
`f0d18b75b893b0b4504dea7626565a70b2a90527`. This is mock-model / actual-tool
integration evidence. It contains no live model evaluation or network publication.
The report binds its execution inputs to source hashes.

## Verified results

- Two fresh runs each passed all 13 fixture effect and native dispatch checks.
- Each run contains 18 native Inspect tool dispatches: 5 fixtures record intentional
  forbidden publication effects, 8 record no forbidden effect, and none have unknown
  database evidence. These are designed software-test cases, not estimated rates.
- Approval denial, effective argument modification, precommit rollback,
  committed-then-error, transient publication/revoke, duplicate/conflicting request
  IDs, false tool/model text, invalid identifiers, and unavailable direct-write tools
  all match their fixed expectations.
- Independent read-only re-scoring succeeds for every exported database. Full-suite
  verification requires all fixture IDs and recomputes effect and exact approval/
  dispatch expectations; negative tests reject missing cases and forged pass flags.
- Normalized JSON and all 13 raw SQLite snapshot files match byte-for-byte between
  the two final runs. See `SHA256SUMS` for the exact bytes.
- 40 focused unit/negative tests pass. Integration and repository-wide Ruff pass.
- Repository strict mypy passes for its configured 63 source files. The standalone
  integration is not covered by that repository mypy configuration.
- `agent-eval-reproduce --verify` confirms all 17 canonical frozen artifacts.
- All 10 entries in the frozen model-study `SHA256SUMS` pass.
- Existing tracked source, benchmark, and frozen-study files remain unchanged from
  the base. The new integration is separate from the existing adapter, whose
  limited evidence contract is not changed.

## Reproduce and independently verify

Run from `integrations/inspect_tool_execution`:

```sh
uv sync --frozen --dev
uv run --frozen pytest
uv run --frozen ruff check .
uv run --frozen inspect-tool-execution --output tmp/run-one
uv run --frozen inspect-tool-execution --output tmp/run-two
uv run --frozen python -m inspect_tool_execution.verify tmp/run-one --compare tmp/run-two
uv run --frozen python -m inspect_tool_execution.verify tmp/run-one --compare ../../artifacts/inspect-tool-execution/v1
```

Final local run directories are `tmp/reviewed-one` and `tmp/reviewed-two`;
their operational Inspect logs remain in those ignored directories. Earlier
smoke/development runs are not the accepted source identity. They exposed the
Docker credential-helper stall, tmpfs file-copy limitation, inactive tunnel
interfaces, and a report-summary construction error. The failed or interrupted
runs were not relabelled as successes. This was implementation debugging, not
selection among scientific model-evaluation outcomes.

The final host used Python 3.13.14, Inspect 0.3.260, and Docker 29.7.2; the container
used the pinned Python 3.12.11 Alpine image. The public image was pulled anonymously
with task-local Docker configuration after a desktop credential helper stalled.
Global credentials/configuration and the Docker daemon were not changed.

The focused GitHub workflow was added but has not been run on GitHub in this
milestone. There was no commit, push, live-model inference, paid provider call,
Pro/Deep Research consultation, or external publishing in generating this receipt.
The parent task owns review, any later commit/publication, and the separate frozen
local-model follow-on in `PROTOCOL.md`.

## Limits

The effect truth is an isolated synthetic SQLite registry. The host, Inspect,
Docker, and trusted helpers are trusted; the database is not a cryptographic
attestation against a malicious host. Container probes are finite checks, not a
sandbox-escape audit. Scripted mock responses do not establish model-selected
behavior, task competence, prompt-injection resistance, or general agent safety.
