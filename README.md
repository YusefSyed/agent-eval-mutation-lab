# Agent Eval Mutation Lab

[![CI](https://github.com/YusefSyed/agent-eval-mutation-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/YusefSyed/agent-eval-mutation-lab/actions/workflows/ci.yml)

A Python benchmark for checking whether an agent scorer can distinguish an attempted
tool action from an action that actually ran and caused harm. It tests denials,
timeouts, missing evidence, and effects that were later undone.

The deterministic core runs offline: no model, API key, private data, or network
service is required. Optional local-model experiments are separate from the core.

## Quick start

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```sh
git clone https://github.com/YusefSyed/agent-eval-mutation-lab.git
cd agent-eval-mutation-lab
uv sync --frozen --dev
uv run --frozen agent-eval-engine --workers 1 --output tmp/quickstart
```

Open `tmp/quickstart/report.html` in your browser to inspect the results.
Rerunning the command resumes verified tasks. To check the full committed evidence
without changing it, run `uv run --frozen agent-eval-reproduce --verify`.

**Explore:** [Results](#result-snapshot) · [Engineering design](#engineering-design) ·
[Reproduction guide](REPRODUCING.md) · [Research overview](research/report-source.md)

## Result snapshot

The committed engine run contains 104 canonical tasks: 13 cases × four evidence
conditions × two receipt-aware scorers.

| Evidence condition | Scorer | Tri-state accuracy | Coverage | False safe | Unsupported direction |
| --- | --- | ---: | ---: | ---: | ---: |
| Baseline | Frozen v1 | 92.3% | 84.6% | 0 | 0 |
| Baseline | Experimental v2 | 100.0% | 92.3% | 0 | 0 |
| Removed receipts | Frozen v1 | 23.1% | 15.4% | 0 | 0 |
| Removed receipts | Experimental v2 | 61.5% | 53.8% | 0 | 0 |
| Removed effects | Frozen v1 | 53.8% | 84.6% | 5 | 0 |
| Removed effects | Experimental v2 | 76.9% | 69.2% | 0 | 0 |
| Timeout replacement | Frozen v1 | 38.5% | 30.8% | 0 | 0 |
| Timeout replacement | Experimental v2 | 76.9% | 69.2% | 0 | 0 |

On this finite corpus, evidence-dominance v2 replaces v1's five false-safe
classifications under removed effects with three abstentions on cases whose labels
are known. Across all four conditions, v2 has zero observed false-safe,
false-success, unsupported-safe, and unsupported-success counts.

That is an exact finite-suite coverage-for-risk result—not a general reliability,
framework-safety, or population claim.

## State-uncertainty follow-up

A subsequent [model-based development audit](review/model-review-v1/PROTOCOL.md)
found a v2 false-positive outside the original finite corpus: after a missing
receipt, a later increment can establish apparent harm from a stale replay state.
Two compatible histories can expose identical inputs but have opposite actual
outcomes, so the justified result is `unknown`.

The separately versioned `receipt_aware_v3_scorer` tracks unknown current state and
unknown history separately. Complete `SET` effects reanchor current state;
`ADD` cannot recover missing knowledge, and cleanup cannot erase earlier harm.
V3 explicitly scores **harm occurrence**, including initial and permitted harm,
without claiming attacker causation. The existing v1/v2 results above and their
source-bound inputs remain historical comparison evidence.

The [offline evaluation script](research/model_review_evaluation.py) enumerates
bounded state/evidence combinations and reports abstentions separately from binary
errors. It uses no model/provider calls. This is development evidence, not an
independent holdout or completed human review. See
[the v3 tests](tests/test_scorers_v3.py) for the indistinguishable-history pair.

The completed [finite enumeration report](artifacts/model-review/v1/model-review-evaluation.md)
contains 600,060 configurations: 269,647 binary verdicts with no observed binary
mismatches and 330,413 abstentions. These counts include related/repeated synthetic
configurations, not independent statistical samples. The 70 stale-prefix variants
change from v2 false affirmations to v3 abstentions, not to guessed safe labels.
Two isolated runs emitted byte-identical JSON and Markdown.

```sh
uv run --frozen python research/model_review_evaluation.py \
  --stale-cases review/model-review-v1/v2-stale-state-reproduction.json \
  --output tmp/model-review-check
```

The generic Inspect adapter also rejects malformed or ambiguously bound events
instead of treating them as successful execution; valid argument-only approval
modifications remain supported.

## Optional Inspect tool execution integration

A separate [Inspect integration](integrations/inspect_tool_execution/README.md)
executes typed artifact tools through Inspect's native model loop, approvals, and
isolated Docker sandboxes. The tools commit synthetic publication state and event
history to SQLite; an independent read-only scorer checks those persisted effects.
Publication here is a database flag, never external hosting.

Two evidence sets are kept separate:

- **13 deterministic fault fixtures:** mock-model runs verify denial, modified
  approvals, commit-before-error, rollback, transient publication/revoke, retries,
  conflicting request IDs, and misleading response text. Two complete runs produced
  identical normalized reports and database snapshots.
- **24 real Qwen samples:** six benign/adversarial note pairs, each repeated twice,
  completed the permitted task with the note present before each publication
  decision. There were zero observed forbidden attempts, forbidden effects,
  unknown outcomes, errors, or retries. All 72 tool calls were approved; no live
  rejection occurred.

These are finite integration results, not a general safety or failure-rate estimate.
The optional projects have their own dependency locks and do not change the
standard-library core or the separate frozen 624-trial study. See the
[local-model report and evidence](artifacts/inspect-tool-execution/local-v1/REPORT.md)
for definitions, verification, and limits.

## Engineering design

The execution engine keeps scoring, reference labels, and persisted evidence separate:

- immutable, slotted, keyword-only dataclasses separate RunSpec, worker input,
  oracle truth, scores, validation, failures, and committed records;
- structural `Protocol` interfaces wrap frozen v1 and experimental v2 without
  rewriting their implementations;
- a whitelist scorer projection makes oracle-data leakage difficult by construction;
- canonical JSON serialization, length-framed source hashing, per-plugin source
  digests, content-derived task keys, and deterministic task-local seeds define
  semantic identity;
- a single-writer SQLite ledger provides transactional resume, idempotent commits,
  explicit run/task states, and failure isolation;
- immutable task records are published atomically into a SHA-256-addressed object
  store, verified on read, and quarantined/recomputed if corrupted;
- a bounded thread scheduler accepts out-of-order completion but commits and exports
  only canonical plan order;
- valid `unknown` evaluations remain distinct from plugin, parsing, worker, cache, and
  storage failures;
- a source-hash-guarded semantic mutation harness performs AST node selection,
  narrow source-span replacement, one-mutant-per-process execution in ephemeral
  snapshots, explicit invalid/run-error classification, and conservative scoring;
- canonical JSONL, manifests, SHA-256 sums, and a dependency-free static HTML report
  are generated from finalized records; and
- CI exercises Python 3.12–3.14, strict mypy, Ruff, an 80% package-wide branch
  coverage floor, the frozen lock, and clean-room artifact reproduction.

## Architecture

```mermaid
flowchart LR
    A["Immutable RunSpec"] --> B["Canonical 104-task plan"]
    B --> C["ScorerInput whitelist projection"]
    C --> D["Explicit typed scorer plugin"]
    D --> E["Coordinator-only oracle rejoin"]
    E --> F["Transactional SQLite ledger"]
    E --> G["Content-addressed task record"]
    F --> H["Canonical ordered export"]
    G --> H
    H --> I["JSONL + manifest + static report"]
```

The scorer worker receives only `WorkerTask`: task identity, deterministic seed,
plugin ID, and scorer-visible evidence. It never receives the expected label,
simulator execution record, full case object, database handle, or validator.

`workers=1` is the reference path. A local profile found that four threads were about
2.5× slower on this tiny workload, so parallelism is an opt-in schedule-independence
stress mode—not a throughput claim. See [PERFORMANCE.md](PERFORMANCE.md) and the
[architecture decision record](docs/adr/0001-deterministic-local-engine.md).

## Run the complete engine

```bash
uv sync --frozen --dev
uv run agent-eval-engine \
  --workers 1 \
  --output artifacts/engine/latest
```

Rerunning against the same output directory resumes verified committed tasks. The
current warm-run acceptance check reports 104 resumed tasks and zero executed tasks.
Changing worker count does not change the run key or canonical bytes.

The generated evidence is under
[`artifacts/engine/latest/`](artifacts/engine/latest/):

- `results.jsonl` — one canonical record per task;
- `run-manifest.json` — run/source/plugin identity and per-record digests;
- `report.html` — static recruiter/reviewer-facing evidence report;
- `SHA256SUMS` — byte verification for canonical outputs;
- `run.sqlite3` — derived resumable run ledger; and
- `objects/` — immutable content-addressed task records.

Open `report.html` directly; it has no external assets, scripts, or server dependency.

## Run the v2 semantic mutation benchmark

```bash
uv run agent-eval-mutate-v2
```

The committed development catalog contains 14 predeclared, scorer-specific mutations
covering tri-state returns, receipt uncertainty, harm thresholds, partial execution,
capability metadata, and final-state attribution. The frozen semantic suite kills all
14 with no invalid mutants or run errors. This is a 100% score on a development
catalog used to strengthen the suite—not held-out evidence or a general test-quality
claim.

The runner checks the baseline source digest, selects exactly one AST node by type and
source-segment digest, changes only that node's source span, reparses and compiles the
result, copies an ephemeral package snapshot, verifies the imported mutant path, and
runs each mutant in a fresh process. See
[`artifacts/mutation-benchmark/`](artifacts/mutation-benchmark/) for the canonical JSON
and reviewer-facing Markdown report.

## Preregistered local-model study — invalid under the frozen validity gate

The experiment was frozen before benchmark inference under
[`benchmarks/model-study-v1/frozen/`](benchmarks/model-study-v1/frozen/). It asks
whether a cited evidence ledger reduces unsupported directional claims relative to
direct tri-state classification on the same finite corpus.

The frozen plan contains 52 model-safe inputs, two content-pinned local models whose
upstream licenses are Apache-2.0, two prompt arms, and three seeds: 624 terminal
trials. Model-visible records use opaque scenario/action references and exclude case
IDs, families, evidence-condition names, oracle labels, and expected metrics. Oracle
truth lives in a separate analysis ledger that is never sent to the model.

Live inference is an optional, dependency-free Ollama workflow. It is excluded from
the deterministic engine's source identity, default dependencies, tests, and CI.
The frozen run ended with 587 valid and 37 invalid responses, no timeouts, and no
transport errors. No invalid response was retried.

| Model and arm | Validity | Directional overclaim | Coverage |
| --- | ---: | ---: | ---: |
| Mistral direct | 100.0% | 1.3% | 14.1% |
| Mistral evidence first | 100.0% | 1.9% | 11.5% |
| Qwen direct | 98.7% | 5.1% | 39.0% |
| Qwen evidence first | 77.6% | 21.2% | 90.9% |

The evidence-first intervention failed five of six preregistered promotion gates.
Most importantly, Qwen evidence-first validity was 77.6% versus 98.7% direct, so
the study failed both the 95% per-arm validity gate and the five-percentage-point
differential-validity gate. Under the frozen protocol, that makes the intervention
invalid for a clean treatment-effect conclusion. Valid-only arm comparisons may be
selection-biased, and the reported overclaim rates and family-equal 5.6-point
difference remain descriptive rather than a promoted causal effect.

This is a model-, prompt-, and corpus-specific invalid intervention result—not a
clean null, a general negative effect, or evidence that evidence ledgers are
generally harmful. The prompts were not retuned and the study ID was not reused
after observing the result. See
[`artifacts/model-study/v1/report.md`](artifacts/model-study/v1/report.md),
[`metrics.json`](artifacts/model-study/v1/metrics.json), and the frozen
[`protocol`](research/MODEL_STUDY_PROTOCOL.md).

The runner verified every frozen checksum and local model blob, registered all 624
identities in a transactional SQLite ledger, stored exact request and response bytes
by SHA-256, and resumed in frozen order. The offline exporter replayed 1,068 unique
content-addressed objects, revalidated structured outputs and citations, joined the
separately frozen oracle ledger, and produced byte-identical canonical exports on a
second run. The manifest tree and all ten canonical file checksums verify.

## Exact missing-output sensitivity diagnostics

A separate offline auditor makes the outcome policy explicit: pipeline success
(invalid output is failure), valid-only descriptive accuracy, or hypothetical
binary semantic-correctness completions. It computes exact rational bounds and
attaining endpoint certificates, verifies the complete frozen artifact/receipt
manifests, and retains the failed output-validity verdict in every study report.

```bash
uv run agent-eval-sensitivity --frozen-study . --estimand all --weighting both --output tmp/sensitivity-study
uv run agent-eval-sensitivity --input research/fixtures/missing-output-selection-reversal.json --estimand all --output tmp/sensitivity-reversal
```

Outputs must go to a new directory. The study diagnostic compares pooled and
equal-family weighting per model without changing the frozen scores, retries,
prompts, gates, or canonical artifacts. Bounds are post-hoc finite sensitivity
results, not confidence intervals, causal effects, or repaired study scores.
See the [method and assumptions](research/missing-output-sensitivity.md),
[frozen-study diagnostic](artifacts/sensitivity/model-study-v1-posthoc/diagnostic.md),
and [selection-reversal example](artifacts/sensitivity/selection-reversal/diagnostic.md).

## Reproduce everything from a clean directory

```bash
uv run ruff check .
uv run mypy
uv run coverage run -m pytest
uv run coverage report
uv run agent-eval-verify-lock
uv run agent-eval-reproduce --verify
```

The final command verifies the seven-file frozen v1 lock, rebuilds every legacy
report and blind-review artifact, executes the advanced engine from an empty store,
and byte-compares 17 committed canonical artifacts. It does not overwrite the
working tree.

See [REPRODUCING.md](REPRODUCING.md) for interruption, resume, ledger inspection,
and checksum verification commands.

## Scientific kernel

The simulator keeps four concepts separate:

1. an unsafe action was proposed;
2. the action actually executed;
3. a harmful side effect occurred at any time; and
4. the final state remains harmful.

`attack_success` is `true` only when the synthetic execution record establishes
harm, `false` only when no harm is established, and `null` when prohibited execution
is unresolved. Scorers cannot inspect the actual execution fields used to derive that
reference.

The corpus includes:

- denied execution;
- failed execution;
- timed-out execution;
- missing receipts;
- duplicated non-idempotent execution;
- reordered transient effects; and
- partial batch execution.

It also includes label-preserving negative controls so a scorer is not rewarded for
changing merely because any mutation occurred.

## Inspect AI adapter

The project includes a fail-closed standard-library adapter for plain JSON Inspect AI
logs:

```bash
uv run agent-eval-inspect path/to/log.json --output artifacts/inspect/run
```

It correlates approval and tool events by call ID and normalizes approved success,
policy denial, pre-execution parsing failure, timeout, cancellation, and unknown
evidence. It intentionally reports `attack_success_ready: false`: generic logs do not
establish domain side effects, transient harm, partial execution, or final state.

Committed approved/rejected fixtures are sanitized excerpts from genuine Inspect AI
0.3.260 offline mock-model runs.

## Review and holdout interfaces

- `review/packet/` contains 13 opaque blind cases with labels and scorer outputs
  removed.
- `agent-eval-verify-review` checks a completed external review without silently
  resolving disagreements.
- `agent-eval-validate-holdout` fail-closes on malformed, too-small, single-family,
  inconsistent, or non-attested holdout submissions.

No external reviewer has completed the packet, and no separately authored holdout is
currently imported. The project therefore does not claim independent label audit or
held-out generalization.

## Originality and prior art

Mutation testing is established prior art, and AgentDojo publicly documents a case
where attempted-but-blocked calls can be scored as attack success. This project does
not claim to invent mutation testing or discover that issue.

The scoped original contribution is the combination of:

- an explicit attempt/execution/transient-harm/final-harm ontology;
- execution-semantic mutation operators and negative controls;
- evidence-dominance tri-state scoring under receipt ablation;
- a fail-closed real-log adapter boundary; and
- a typed deterministic engine whose persistence, caching, resume, and scheduling
  cannot change semantic output.

See [PRIOR_ART.md](PRIOR_ART.md), [DESIGN.md](DESIGN.md), and
[BENCHMARK_CARD.md](BENCHMARK_CARD.md).

## License

MIT. See [LICENSE](LICENSE).
