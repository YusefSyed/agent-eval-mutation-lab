# Milestone 5 receipt — advanced deterministic Python engine

**Date:** 2026-08-28  
**Status:** verified local engineering milestone; not yet pushed or publicly released

## Objective achieved

Extended the finite benchmark into a typed, deterministic, resumable local evaluation
engine that demonstrates advanced Python systems and reliability mechanics without
changing frozen v1 evidence or inflating the empirical claim.

## Architecture evidence

- 104 canonical tasks: 13 cases × four evidence conditions × two scorers.
- Immutable slotted data contracts separate RunSpec, worker input, oracle truth,
  score, validation, failure, artifact, and execution summary.
- Explicit `Protocol` scorer plugins wrap frozen v1 and experimental v2.
- WorkerTask contains no expected label, simulator truth, case object, validator, or
  database handle.
- SHA-256 source/plugin/task/result identity with deterministic task-local seeds.
- Single-writer transactional SQLite ledger with idempotent commits and explicit
  complete/interrupted/incomplete states.
- Atomic content-addressed task objects, digest verification, corruption quarantine,
  and deterministic recomputation.
- Bounded thread scheduler buffers out-of-order completion and commits canonical plan
  order; `workers=1` remains the reference path.
- Canonical JSONL, semantic run manifest, SHA-256 sums, and dependency-free static
  HTML evidence report.

## Canonical run

```text
status                  complete
expected tasks          104
completed tasks         104
failed tasks            0
run key                 e85542f262b8446188c6463526c7aa4c191b62bb694f08a63b746adedb8e239b
semantic run digest     ea10f4fe5e9603379ae7e7ca568cadb89e1d6d01b278fd30265077f70fbd9de9
canonical results hash  2f3788d689cf1796c442c5193a67e03e63279c3c525ac184ca8fc3d64a8951cd
source-tree digest      aef85436c57b377e544da43aefbd2d2b03654c117005319856c2d662007e4483
```

Export hashes:

```text
run-manifest.json  7eb46ffa5fa2683868867ed9b05c45be3f73e5c035a85cd9c6c52f90f4f24c15
report.html         2a62b933f11390104705bed9a1db53452c344c1168c2992f2a3277fd969eea70
run.sqlite3         e0c9cfdfe573e45c956b24921978b47ca4bce64f2eb0ae9d7440c870fb98d318
SHA256SUMS          095d25208f57ec21c6c508239a29003239a594280324245e5153dea7e22bbe44
```

## Verification

```text
Ruff                               all checks passed
strict mypy                        no issues in 35 source files
pytest                             54 passed
package-only branch coverage       81% (configured floor: 80%)
engine-core branch coverage        90% excluding CLI wrapper
frozen v1 lock                     7/7 files verified
clean-room reproduction            15/15 canonical artifacts matched
warm four-worker rerun             104 resumed; 0 executed; bytes unchanged
SHA256SUMS                          manifest, report, and results all OK
SQLite integrity                   ok; 104 complete tasks; 104 artifacts
package build                      0.2.0 wheel and source distribution succeeded
secret/absolute-path scan          no findings
static report desktop QA           visually inspected; no defect found
static report 390px mobile QA       no overflow; labeled result cards
browser console/external assets    no warnings/errors; zero external assets
```

The package contains 35 Python source files, including 14 engine modules, and 18 test
files. Current source totals 4,844 lines; line count is descriptive, not a quality
claim.

## Architecture decision

The adopted design is a bounded hybrid centered on typed deterministic
planning, a transactional local run ledger, content-addressed evidence, one measured
parallel backend, and static reporting. Mandatory asyncio, a network service, generic
event sourcing, dynamic plugin discovery, premature inferential statistics, and a
frontend app were rejected as unjustified complexity.

## Performance truth

A local 250-trial profile of the 104-task matrix found a fresh four-thread executor
2.529× slower than sequential execution. The project publishes this negative result.
Parallelism is therefore a schedule-independence and isolation test, not a speed
claim.

## Current claim boundary

This is now a strong verified engineering artifact suitable for
truthful portfolio and résumé description. It remains a finite synthetic benchmark,
not a production safety system, statistically validated general result, independent
label audit, accepted upstream contribution, or proof of unaided Python fluency.

Independent blind review and separately authored holdout evidence remain external
credibility upgrades rather than reasons to hide the completed engineering work.
