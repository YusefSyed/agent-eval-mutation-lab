# Benchmark card

## Summary

Agent Eval Mutation Lab is a finite synthetic benchmark, local evaluation engine,
and preregistered local-model study for a narrow measurement problem: whether
tool-agent scorers distinguish unsafe proposals from actual execution, realized
harm, and justified uncertainty.

It is not a production safety certification or population study. The model study is
specific to two pinned local model builds, two frozen prompts, and this corpus.

## Tasks and labels

- 13 hand-authored cases across five scenario families.
- Seven execution-semantic mutations plus clean and negative-control cases.
- Four scorer-visible evidence conditions: baseline, removed prohibited receipts,
  removed effect records, and success-to-timeout replacement.
- Two substantive receipt-aware scorers in the engine matrix: frozen v1 and
  experimental evidence-dominance v2.
- 104 canonical engine tasks: 13 cases × four conditions × two scorers.
- Tri-state target: `true`, `false`, or `unknown` attack success.
- 624 model-study trials: 52 opaque inputs × two pinned models × two prompt arms ×
  three seeds.

Oracle outcomes are produced by a simulator from actual execution fields that never
enter the scorer projection. The scorer receives only initial/final visible state,
the harm predicate, proposed calls, and available receipts.

## Intended uses

- Regression-test scorer contracts under denied, failed, timed-out, missing,
  duplicated, reordered, and partial execution evidence.
- Demonstrate fail-closed handling of incomplete tool evidence.
- Test whether orchestration, persistence, cache state, or worker scheduling changes
  canonical semantic results.
- Serve as a small, inspectable substrate for independent review and separately
  authored holdout cases.
- Test a preregistered prompting intervention with explicit validity, risk,
  coverage, and composition-sensitivity gates.

## Out-of-scope uses

- Estimating real-world attack rates or general model behavior.
- Comparing production agent frameworks.
- Certifying a scorer, agent, or application as safe.
- Treating repeated synthetic tasks as independent statistical samples.
- Inferring generalization from the current zero observed v2 overclaim counts.

## Metrics

The engine reports exact finite-corpus metrics:

- tri-state accuracy and coverage;
- selective risk among non-abstaining predictions;
- false-safe and false-success counts;
- unsupported directional claims when the reference is unknown;
- unknown recall; and
- unnecessary abstention on known cases.

The model-study analysis additionally reports protocol validity, multiclass Brier
score, seed disagreement, paired directional-overclaim differences, and finite
family-composition sensitivity.

No confidence interval, p-value, or population estimate is reported because the
current cases are hand-authored and not an independent sample.

## Current observed result

Across baseline and three evidence ablations, experimental v2 produced zero observed
false-safe, false-success, unsupported-safe, and unsupported-success counts. Under
removed effect records, it replaced frozen v1's five false-safe classifications with
three known-case abstentions. This is an exact coverage-for-risk result on this
corpus only.

The preregistered model study is invalid under its output-validity gates. Mistral
was 100% valid in both arms. Qwen direct was 98.7% valid, while Qwen evidence-first
was 77.6% valid; this failed both the per-arm and differential-validity gates. Five
of six promotion gates failed. The reported 5.1% direct and 21.2% evidence-first
overclaim rates are descriptive, not a clean treatment-effect estimate, because
differential invalidity can bias arm comparisons. The intervention is not promoted,
and the prompts were not retuned under the same study ID.

## Reproducibility and engineering controls

- Immutable typed RunSpec, TaskSpec, scorer projection, result, and validation
  contracts.
- Content-derived task keys and deterministic per-task seeds.
- Explicit in-process plugin registry; no dynamic or remote code loading.
- Transactional single-writer SQLite ledger with idempotent commits.
- Content-addressed immutable task records with digest verification and corruption
  quarantine.
- Bounded schedule-independent thread execution; sequential execution is the
  reference path.
- Canonical ordered JSONL, semantic run manifest, and SHA-256 sums.
- Clean-room regeneration and byte comparison in CI on Python 3.12–3.14.
- A transactional 624-trial study ledger, 1,068 unique content-addressed
  request/response objects, offline oracle rejoin, deterministic re-export, and ten
  verified canonical study checksums.
- Package-wide branch coverage is enforced at 80%; the current measured package
  result is 81%, and the engine core measures 90% when CLI wrappers are excluded.

## Review and holdout status

A deterministic blind label-review packet and fail-closed holdout intake validator
exist. No external reviewer has completed the packet, and no separately authored
holdout submission has been imported. Disagreements must be preserved rather than
edited away.

## Provenance and ownership

The corpus is synthetic and contains no private or customer data. The repository
demonstrates a verified engineering artifact; it does not by itself prove unaided
Python fluency. See `OWNERSHIP.md`.

## License

Code and committed synthetic artifacts are released under the repository's MIT
license. Inspect fixtures are sanitized excerpts generated from an offline mock-model
run; their provenance is recorded next to the fixtures.
