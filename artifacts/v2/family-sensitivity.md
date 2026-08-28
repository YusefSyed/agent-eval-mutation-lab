# Leave-one-scenario-family-out sensitivity

**Interpretation:** Exact leave-one-family-out sensitivity on the finite corpus; not a population uncertainty interval.

| Condition | Scorer | Accuracy range | Coverage range | Max false safe | Max false success | Max unknown overclaim |
| --- | --- | --- | --- | ---: | ---: | ---: |
| baseline | receipt_aware_v1_frozen | 0.909-1.000 | 0.818-1.000 | 0 | 0 | 0 |
| baseline | evidence_dominance_v2_experimental | 1.000-1.000 | 0.909-1.000 | 0 | 0 | 0 |
| remove prohibited receipts | receipt_aware_v1_frozen | 0.091-0.273 | 0.000-0.250 | 0 | 0 | 0 |
| remove prohibited receipts | evidence_dominance_v2_experimental | 0.545-0.636 | 0.455-0.625 | 0 | 0 | 0 |
| remove effect records | receipt_aware_v1_frozen | 0.455-0.636 | 0.818-1.000 | 5 | 0 | 0 |
| remove effect records | evidence_dominance_v2_experimental | 0.625-0.818 | 0.625-0.727 | 0 | 0 | 0 |
| replace success with timeout | receipt_aware_v1_frozen | 0.250-0.455 | 0.182-0.364 | 0 | 0 | 0 |
| replace success with timeout | evidence_dominance_v2_experimental | 0.625-0.818 | 0.625-0.727 | 0 | 0 | 0 |

Ranges show dependence on the included scenario families. They do not justify confidence intervals or broad generalization.
