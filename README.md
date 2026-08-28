# Agent Eval Mutation Lab

Agent Eval Mutation Lab is an offline Python benchmark for one narrow question:

> Can execution-semantic mutation testing expose tool-agent scorers that confuse
> proposed actions, actual execution, and realized harm?

The benchmark currently contains 13 hand-authored synthetic cases across five
scenario families, including seven execution-semantic mutation types. It compares
an attempted-call scorer, a final-state-only scorer, and a receipt-aware scorer,
plus three trivial sanity controls. The run writes deterministic JSON and Markdown
artifacts and requires no model, API key, private data, or network access.

This is an initial benchmark kernel, not a finished research result and not a claim
that any production agent or evaluation framework is safe or unsafe.

## Run

```bash
uv sync --dev
uv run pytest
uv run ruff check .
uv run mypy
uv run agent-eval-mutation --output artifacts/latest
```

The last command creates:

- `artifacts/latest/results.json`
- `artifacts/latest/results.md`

## Outcome contract

The simulator keeps four concepts separate:

1. an unsafe action was proposed;
2. the action actually executed;
3. a harmful side effect occurred at any time; and
4. the final state remains harmful.

`attack_success` is `true` only when the synthetic execution record establishes a
harmful side effect. It is `null` when a prohibited timed-out action leaves execution
unknown. A scorer sees only proposed calls, visible receipts, and the final state; it
cannot read actual execution fields or expected labels.

## Mutation families

- denied execution
- failed execution
- timed-out execution
- missing receipt
- duplicated execution
- reordered execution
- partial execution

The corpus includes both label-changing mutations and label-preserving negative
controls. A scorer should change its result only when the relevant outcome changes.

## What is original and what is not

Mutation testing is established prior art. AgentDojo's public issue tracker also
documents a concrete case where attempted-but-blocked calls can be scored as attack
success. This project does not claim to invent mutation testing or discover that bug.

The scoped contribution under development is the combination of an explicit
attempt/execution/harm ontology, execution-semantic mutation operators, scorer-
contract comparisons, and a framework-independent finite benchmark. See
[PRIOR_ART.md](PRIOR_ART.md) and [DESIGN.md](DESIGN.md).

## Evidence boundary

- Current results apply only to this synthetic finite corpus.
- A later release needs a held-out mutation family or independently authored cases,
  receipt-field ablations, leave-one-family-out sensitivity analysis, and one real
  trajectory-log adapter.
- No résumé result should be claimed until those gates and one-command reproduction
  are complete.
- The repository is Codex-assisted. It is not evidence of unaided Python fluency.
  See [ASSISTANCE.md](ASSISTANCE.md) for the separate ownership gate.

## License

MIT. See [LICENSE](LICENSE).

