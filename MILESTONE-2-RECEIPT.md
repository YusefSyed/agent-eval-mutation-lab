# Milestone 2 receipt - Inspect adapter and evidence ablations

**Date:** 2026-08-28
**Status:** verified local milestone; not pushed, published, or resume-ready

## Objective achieved in this milestone

Frozen the initial benchmark evidence, tested the v1 receipt-aware scorer under
predeclared evidence ablations, and added a fail-closed adapter for plain JSON Inspect
AI logs without adding Inspect as a runtime dependency.

## Verified adapter evidence

- Official Inspect `ToolEvent` and `ApprovalEvent` source were reviewed.
- Genuine Inspect AI 0.3.260 JSON logs were generated locally with `mockllm/model`.
- Approved calls normalized to `succeeded` with a result.
- Policy-rejected calls normalized to `denied` with `error.type="approval"`.
- Timeouts, cancellations, contradictions, and generic failures normalize to unknown.
- The adapter reports `attack_success_ready: false` because generic logs do not
  establish domain side effects, transient harm, partial execution, or final state.

## Receipt-ablation result

| Evidence condition | Accuracy | False-safe | Abstention |
| --- | ---: | ---: | ---: |
| Baseline | 0.917 | 0.000 | 0.083 |
| Remove prohibited receipts | 0.167 | 0.000 | 0.833 |
| Remove effect records | 0.500 | 0.417 | 0.083 |
| Replace success with timeout | 0.333 | 0.000 | 0.667 |

The effect-record ablation is the material negative result: v1 can interpret a
successful prohibited call with missing effect details as no harm. Baseline v1 is now
locked and must not be rewritten; a future v2 scorer should abstain on that evidence.

## Checks and outcomes

```text
uv run pytest                 -> 16 passed
uv run ruff check .           -> all checks passed
uv run mypy                   -> no issues in 13 source files
agent-eval-verify-lock        -> 7 frozen files verified
base reports, two clean runs  -> byte-identical
ablation reports, two runs    -> byte-identical
adapter reports, two runs     -> byte-identical
fresh Inspect full-log run    -> approved succeeded; rejected denied
PDF structural QA             -> 7 pages, 7 nonempty, 26 link annotations
PDF visual QA                 -> every page inspected; no defects found
```

## Evidence hashes

```text
receipt-ablations.json  95d3ea1c6798d87b46a60a13e22670c37c7396a47fbe5ee758a12d4228099911
receipt-ablations.md    302d0f95dfda67bd93188f10350ae9c6546d5b65c3dbf77fbc05af1eb9774206
inspect approved JSON   62cdf18b015468ad0e864c118a4edb6ff7b4e143596b1b7728f49a41366d8bb6
inspect rejected JSON   c8e1c158e817133f38e44058a1b843f1955a3841abe37a18989eaf01b30ea1d1
Inspect adapter source  368963d5296ca2c0d3327549c46be75d02fa68341e758532b65010a68eda458c
ablation source         b00bbb6509804fbc8465d26806d9f64c04cc5e09aad2b211af2d5a2c0a949ee5
expanded PDF            d1378546d0523d5d212ad58febdf33d1e4d030525fcb805396e3684c2e2be768
                        historical milestone-2 render; recoverable from commit fe522bd
```

The stable PDF path was later updated for milestone 3. The hash above remains the
milestone-2 evidence hash and is not expected to match the current report.

## Remaining gates

1. Add a held-out or separately authored mutation family without changing v1.
2. Run leave-one-family-out sensitivity at the scenario-family level.
3. Obtain independent case-label and outcome-ontology review.
4. Design v2 to abstain on successful prohibited calls with missing effect evidence.
5. Complete the protected no-AI changed-contract, debugging, explanation, and clean
   reproduction gate.
6. Publish only after the ownership and review gates pass.

## Do not claim yet

- independent Python fluency;
- generic Inspect attack-success scoring;
- real-world model or framework safety results;
- completed empirical research;
- an accepted upstream contribution; or
- a public GitHub release.
