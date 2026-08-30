# Post-hoc missing-output sensitivity diagnostic

**Diagnostic only. These finite completion bounds do not repair the frozen study, provide confidence intervals, or establish causal effects.**

Frozen output-validity gate passed: **not applicable**.
A bound excluding zero cannot override that verdict.

Contrast is left arm minus right arm; all numbers below are exact rationals.
Every group weight and denominator is explicit in `contracts.json`.
Valid-only results condition on observed valid outputs and can be selected.

| Comparison | Contrast | Weighting | Estimand | Left | Right | Difference |
| --- | --- | --- | --- | --- | --- | --- |
| declared_comparison | left - right | declared_group_weights | latent_semantic_correctness | [1/5, 1] | 4/5 | [-3/5, 1/5] |
| declared_comparison | left - right | declared_group_weights | pipeline_success_accuracy | 1/5 | 4/5 | -3/5 |
| declared_comparison | left - right | declared_group_weights | valid_only_accuracy | 1 | 4/5 | 1/5 |

The JSON preserves weights, observed/planned denominators, missing reasons, and exact endpoint assignments.
These are sharp interval hulls of binary completions; interior values need not all be attainable.
An undefined valid-only group is never discarded or renormalized.

Method attribution: standard bounded-outcome/partial-identification reasoning; see `research/missing-output-sensitivity.md`.
