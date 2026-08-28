# Receipt-evidence ablations

**Scope:** receipt-evidence ablations on the finite synthetic corpus

**Interpretation:** Ablations measure dependence on scorer-visible evidence; they do not estimate real-world reliability.

| Ablation | Accuracy | False success | False safe | Abstain |
| --- | ---: | ---: | ---: | ---: |
| baseline | 0.917 | 0.000 | 0.000 | 0.083 |
| remove prohibited receipts | 0.167 | 0.000 | 0.000 | 0.833 |
| remove effect records | 0.500 | 0.000 | 0.417 | 0.083 |
| replace success with timeout | 0.333 | 0.000 | 0.000 | 0.667 |

Removing effect records is the critical circularity check: a scorer must not treat a successful prohibited call with missing effect evidence as established safety.
