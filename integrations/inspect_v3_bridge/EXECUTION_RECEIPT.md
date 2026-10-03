# Bounded implementation receipt

Implemented only `integrations/inspect_v3_bridge/**` and
`.github/workflows/inspect-v3-bridge.yml` in `agent-eval-real-tool-v3`.
Core, legacy registry/policy/fixtures and frozen artifacts are unchanged.

The package adds the standalone lock/path dependencies, exclusive private producer
sidecars, restricted Docker build context, native Inspect wrapper/capture,
reconciliation and strict typed v3 projection, five withholding views, prediction
seals, independent offline verifier and two-run CI. `PROTOCOL.md` records semantics
and claim limits. Unit fixtures use isolated local SQLite and native mock/local
stubs, with no hosted inference and no Docker acceptance claim.

Checks run from `integrations/inspect_v3_bridge` on macOS Python 3.14.6:

- `uv sync --dev`: successful package/lock installation.
- `uv run --frozen ruff check .`: passed.
- `uv run --frozen mypy`: strict projection check passed.
- `uv run pytest`: 60 passed, including 13 registry/producer cases, 13 native
  Inspect mock/local-stub loops, malformed/correlation/withholding/retry checks,
  receipt-write gaps, offline forgery/coverage checks and seal-before-oracle order.
- `uv run --frozen pytest ../inspect_tool_execution/tests`: 40 passed.
- `uv run --frozen agent-eval-reproduce --root ../.. --verify`: all 17 artifact
  bytes matched; frozen baseline lock verified.
- Upstream `git ls-remote` confirmed the upload action pin matches tag v4.6.2.

An initial reproduction invocation omitted `--root ../..` and failed with a
missing baseline lock under the package directory. The corrected command and CI
explicit root argument passed. JSON tuple/list normalization discovered by offline
round-trip tests was fixed in the projection serialization.

Actual Docker execution remains unverified locally because the parent reported
an unresponsive Docker API. No Docker daemon changes, provider calls, commits,
pushes or evidence publication were performed. The new GitHub workflow is the
next acceptance route: unchanged legacy actual baseline, 13 bridge fixtures twice
in fresh directories, offline DB/view/report comparison and uploaded raw artifacts.
Do not claim actual-tool acceptance until that workflow succeeds and its evidence
is independently verified. Receipt writes remain non-atomic with DB commits, as
required by the packet; missing telemetry is unknown.

## Bounded architecture review corrections

Reserved the exclusive invocation sidecar before registry mutation. Reusing an
invocation ID with a different logical request now fails before a second DB effect.
Reservation failure prevents mutation; a write failure after reservation/commit
leaves an invalid incomplete sidecar, never a complete empty-effect record.
Validated raw unknown dispositions now project to receipt=None, while preserving
the raw sidecar. Preserved the root's keyword-based V3 contract construction.

Added independent acceptance assertions: harmful effect-withholding views must be
unknown and every publication-action omission view must be unknown, including
transient publication followed by revocation. Tests simulate correlated transform
and recomputation regressions with matching seals; acceptance rejects the false
certainty even though the projection comparison agrees.

Red proof before fixes: `uv run pytest tests/test_bridge.py -k
'duplicate_invocation_different or correlated_transform'` produced 11 failures
(duplicate invocation and ten harmful withholding assertions), 32 deselected.
Full captured output: `/tmp/inspect-v3-reservation-red.txt`.

After those corrections: `uv run pytest` passed all 73 bridge tests;
`uv run --frozen ruff check .` passed; `uv run --frozen mypy` passed.
No legacy/core source changed, so their previously successful checks were not
repeated. Actual Docker acceptance remains pending the parent's remote CI.

## Actual execution completed October 3, 2026

The parent subsequently executed the unchanged legacy baseline and all 13 bridge
fixtures twice in GitHub Actions run 37105281221 at source a5c9d67. All acceptance
checks passed. The artifact was downloaded and independently verified locally;
normalized observations, predictions, reports and database bytes match. Both push
and PR actual-tools jobs succeeded, as did six core Python checks. Versioned raw
evidence, provenance and results are now in `artifacts/inspect-v3-bridge/v1`.
The earlier pending statements describe the local implementation handoff, not
the final execution state. No live-model or human-review claim is made.
