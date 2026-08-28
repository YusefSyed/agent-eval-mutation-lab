# Agent Eval Mutation Lab project map

## Purpose and scope

- This repository ships a framework-independent Python benchmark for testing the
  execution-semantic robustness of tool-agent trajectory scorers.
- Supported runtime is Python 3.12+ through `uv`; the current offline kernel uses
  only the standard library at runtime.
- Non-goals: no live agent or model calls, no API keys, no private/customer data,
  no production-safety claims, no general-purpose eval framework, and no unaided
  Python-fluency claim before the separate ownership gate in `ASSISTANCE.md`.

## Authority order

When sources disagree, use this order:

1. Current implementation plus reproducible tests and generated result hashes.
2. `DESIGN.md` outcome ontology and falsification gates.
3. `README.md` run and public claim boundaries.
4. `PRIOR_ART.md` and `research/report-source.md` research context.

The PDF is a dated reporting artifact. Regenerate it after metrics or claim
boundaries change; do not treat its embedded counts as authority over current code.

## Repository map

| Area | First files or symbols | Boundary or invariant |
| --- | --- | --- |
| Ground truth | `models.py`, `simulator.execute` | Actual execution fields never enter scorer views |
| Synthetic corpus | `cases.benchmark_cases` | Every mutant names a base and expectation class |
| Mutations | `mutations.py` | Effects must be coherent for the selected scenario |
| Scorers | `scorers.py` | Each scorer has an explicit target contract |
| Metrics | `metrics.py` | Evidence-withholding cases are not invariance pairs |
| Reports | `benchmark.py`, `report.py` | Same inputs must emit byte-identical JSON/Markdown |
| Research | `DESIGN.md`, `PRIOR_ART.md`, `ASSISTANCE.md` | No first-ever, framework-safety, or unaided-fluency claim |

Trace a concrete `case_id` from `cases.py` through `simulator.execute`, the
scorer-safe observation, each scorer, and the generated case result.

## Symptom to evidence map

| Symptom | Open in this order | Focused check |
| --- | --- | --- |
| Wrong attack-success label | `simulator.py`, source case, `DESIGN.md` | `tests/test_simulator.py` |
| Mutation score seems unfair | case expectation, `metrics.py` | `tests/test_mutations.py` |
| Receipt scorer appears oracle-like | `ObservedTrajectory`, `receipt_aware_scorer` | scorer-view negative test |
| Results changed unexpectedly | `cases.py`, scorers, metrics | two clean runs plus `cmp` |
| PDF disagrees with results | `artifacts/latest/results.json`, report builder | regenerate, render all pages |

## Working safely

- Inspect `git status --short` and planned diffs first.
- Preserve unrelated changes and generated evidence; never reset or clean broadly.
- Add a regression for contract or mutation failures before changing behavior.
- Keep outcome ontology, mutation expectation, scorer contract, metrics, and docs in
  sync.
- Do not add real framework data until its license and contamination rules are
  checked and the adapter can remain outside the core.

## Commands

```text
uv sync --dev
uv run pytest
uv run ruff check .
uv run mypy
uv run agent-eval-mutation --output artifacts/latest
```

## Definition of done

- Targeted and negative contract tests pass.
- Ruff and strict mypy pass.
- Two clean runs produce byte-identical JSON and Markdown.
- Public claims remain bounded to current finite evidence.
- Dated PDF and generated artifacts agree with the current result hash.
- Unrelated career-workspace state is untouched.

