# Post-hoc missing-output sensitivity diagnostic

**Diagnostic only. These finite completion bounds do not repair the frozen study, provide confidence intervals, or establish causal effects.**

Frozen output-validity gate passed: **False**.
A bound excluding zero cannot override that verdict.

Contrast is left arm minus right arm; all numbers below are exact rationals.
Every group weight and denominator is explicit in `contracts.json`.
Valid-only results condition on observed valid outputs and can be selected.

| Comparison | Contrast | Weighting | Estimand | Left | Right | Difference |
| --- | --- | --- | --- | --- | --- | --- |
| mistral-small3.1:24b-instruct-2503-q4_K_M | evidence_first - direct | equal_family | latent_semantic_correctness | 3/20 | 47/300 | -1/150 |
| mistral-small3.1:24b-instruct-2503-q4_K_M | evidence_first - direct | equal_family | pipeline_success_accuracy | 3/20 | 47/300 | -1/150 |
| mistral-small3.1:24b-instruct-2503-q4_K_M | evidence_first - direct | equal_family | valid_only_accuracy | 3/20 | 47/300 | -1/150 |
| mistral-small3.1:24b-instruct-2503-q4_K_M | evidence_first - direct | pooled | latent_semantic_correctness | 9/52 | 8/39 | -5/156 |
| mistral-small3.1:24b-instruct-2503-q4_K_M | evidence_first - direct | pooled | pipeline_success_accuracy | 9/52 | 8/39 | -5/156 |
| mistral-small3.1:24b-instruct-2503-q4_K_M | evidence_first - direct | pooled | valid_only_accuracy | 9/52 | 8/39 | -5/156 |
| qwen3.5:9b-q4_K_M | evidence_first - direct | equal_family | latent_semantic_correctness | [301/600, 223/300] | [37/120, 13/40] | [53/300, 87/200] |
| qwen3.5:9b-q4_K_M | evidence_first - direct | equal_family | pipeline_success_accuracy | 301/600 | 37/120 | 29/150 |
| qwen3.5:9b-q4_K_M | evidence_first - direct | equal_family | valid_only_accuracy | 973/1500 | 52/165 | 5503/16500 |
| qwen3.5:9b-q4_K_M | evidence_first - direct | pooled | latent_semantic_correctness | [77/156, 28/39] | [16/39, 11/26] | [11/156, 4/13] |
| qwen3.5:9b-q4_K_M | evidence_first - direct | pooled | pipeline_success_accuracy | 77/156 | 16/39 | 1/12 |
| qwen3.5:9b-q4_K_M | evidence_first - direct | pooled | valid_only_accuracy | 7/11 | 32/77 | 17/77 |

The JSON preserves weights, observed/planned denominators, missing reasons, and exact endpoint assignments.
These are sharp interval hulls of binary completions; interior values need not all be attainable.
An undefined valid-only group is never discarded or renormalized.

Method attribution: standard bounded-outcome/partial-identification reasoning; see `research/missing-output-sensitivity.md`.
