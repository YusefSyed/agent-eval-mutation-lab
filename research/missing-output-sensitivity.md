# Exact missing-output sensitivity: a post-hoc diagnostic

The frozen intervention remains **invalid under its preregistered output-validity
gate**. This separate diagnostic asks a different, finite question: what can a
binary accuracy comparison say under explicitly declared handling of invalid
outputs? It does not repair the study, reinterpret malformed responses, modify a
scorer, retry inference, or authorize a treatment-effect claim.

## Three different quantities

| Estimand | Invalid or missing output | Denominator | Interpretation |
| --- | --- | --- | --- |
| `pipeline_success_accuracy` | Failure (0) by explicit policy | Every planned trial | Fully observed pipeline success under that policy |
| `valid_only_accuracy` | Excluded from the conditional descriptive mean | Valid outputs within each declared group | Selection can change the comparison |
| `latent_semantic_correctness` | An unresolved hypothetical binary value | Every planned trial | Sensitivity over all unrestricted binary completions |

A protocol-complete `insufficient_evidence` verdict is a valid semantic prediction.
It receives correctness 1 when the oracle also says unknown and 0 otherwise. It is
never converted to missing merely because its normalized prediction is `None`.
Only invalid/missing terminals are unresolved in the hypothetical analysis.

The caller must choose an estimand, or explicitly request all three. No positive
result promotes another estimand or overrides a failed validity gate. In
particular, pipeline failure scoring defines an operational outcome; it does not
discover the unobserved semantic correctness of an invalid response.

## Finite contract and derivation

The input names two arms, a complete trial roster and planned count for every
group/arm, observed binary outcomes or missing-with-reason records, and positive
rational group weights summing exactly to one. Every planned trial must have a
record. Absent rows, duplicates, changed group assignments, booleans masquerading
as integers, nonfinite values, and inconsistent counts or weights are rejected.
Generic declarations do not prove that a roster or grouping was prespecified;
that is a caller responsibility. The study adapter takes groups from frozen data.

For arm `a` and group `g`, let `N[a,g] > 0` be the planned count, `S[a,g]` the
observed successes, and `M[a,g]` the unresolved count. The logical group bounds are

```text
L[a,g] = S[a,g] / N[a,g]
U[a,g] = (S[a,g] + M[a,g]) / N[a,g]
L[a]   = sum_g weight[g] * L[a,g]
U[a]   = sum_g weight[g] * U[a,g]
left - right lies in [L[left] - U[right], U[left] - L[right]].
```

With unrestricted binary completions and positive weights, assigning every
missing left value 0 and every missing right value 1 attains the lower contrast
endpoint. Reversing these assignments attains the upper endpoint. The report
exports both assignments, exact rational group weights/means, and the exact
contrast; `evaluate_completion` checks an assignment without using the bound
formula. These certificates establish the endpoints in the declared binary
completion model. They do not establish that a real repaired model response with
those values exists.

This is the **sharp interval hull**, not a claim that every interior value is
attainable: finitely many missing binary values permit only finitely many sums.
All machine-readable weights and endpoints use integer numerator/denominator
pairs through `fractions.Fraction`; no rounded floats enter the certificates.
No missing-at-random assumption, sampling confidence interval, or causal model is
introduced. Dependence restrictions between completions are not imposed.

Valid-only means instead divide observed successes by observed valid counts.
If any positive-weight group has no valid outcome, that arm's weighted mean and
its comparison are undefined. The tool never drops that group or renormalizes
the remaining weights.

## Weighting and frozen-study boundary

The adapter produces per-model diagnostics with two explicit choices. `pooled`
collapses all planned trials into one group of weight 1, so valid-only accuracy is
the conditional accuracy over that arm's valid trials. `equal_family` uses the
five frozen oracle families at weight 1/5 each. This reuses the frozen family
taxonomy and equal-family weighting scheme, but its application to these accuracy
estimands is post-hoc, not a new preregistered result. It changes the target
quantity; it is not an inferential correction or a sensitivity confidence band.

The adapter verifies the exact checksum file sets, manifest sizes/digests, copied
protocol files, content-addressed receipt tree, all planned trial identities,
oracle joins, and the canonical metrics against the existing public offline
analysis. It reads JSON and receipt files without opening SQLite or contacting a
model. This is checksum/manifest consistency and canonical-outcome validation,
not an authenticity signature or a fresh replay of raw response normalization.

The 624 terminals remain 587 valid and 37 invalid. For example, Qwen's pooled
evidence-first minus direct hypothetical accuracy bound is `[11/156, 4/13]`.
Its sign under the declared completion model does **not** rescue the failed
validity gate, address the original directional-overclaim estimand, or establish
an intervention benefit. The failed verdict is carried independently in both
JSON and Markdown outputs. Mistral has no unresolved outputs, so its pooled bound
collapses to the observed finite difference `-5/156`.

## Selection-reversal falsification example

In the committed synthetic fixture, left has 2 correct valid outputs and 8
unresolved outputs; right has 8 correct and 2 incorrect valid outputs. Conditional
valid-only accuracy favors left: `1 - 4/5 = 1/5`. Completing left's missing values
as failures reverses the contrast: `1/5 - 4/5 = -3/5`. Completing them as successes
attains `1/5`. Thus the hypothetical contrast hull is `[-3/5, 1/5]`; the observed
valid-only comparison does not determine its sign.

```bash
uv run agent-eval-sensitivity --input research/fixtures/missing-output-selection-reversal.json --estimand all --output tmp/new-reversal-diagnostic
uv run agent-eval-sensitivity --frozen-study . --estimand all --weighting both --output tmp/new-study-diagnostic
uv run pytest tests/test_output_sensitivity.py tests/test_output_sensitivity_study.py
uv run agent-eval-reproduce --verify
```

Each new diagnostic directory contains canonicalized input contracts, JSON
certificates, a Markdown report, and SHA-256 checksums. Existing destinations and
frozen/core artifact directories are refused. Two clean runs are byte-identical;
changing raw input file bytes changes its provenance digest, while reordering an
equivalent in-memory manifest does not change its canonical contract/certificates.

Tests enumerate all completions of every 0/1/missing observation pattern for a
six-trial, two-arm, two-group fixture under pooled and unequal group weights.
Independent per-trial dot products establish the extrema, and every exported
witness attains its claimed endpoint. Additional tests cover identity/manifest
corruption, the valid semantic-unknown case, selection reversal, empty observed
groups, deterministic output, strict input, and read-only frozen joins.

The package lives under the already optional `model_study/sensitivity/` namespace.
This preserves the existing engine source-identity boundary without changing hash
exclusions. Frozen scoring/analysis files and all 17 canonical core artifacts are
unchanged. The new artifacts are under `artifacts/sensitivity/` only.

## Attribution

The bounded-outcome and partial-identification ideas are standard, not new
statistical theory. See Charles F. Manski, *Partial Identification of Probability
Distributions* (2003), especially the treatment of missing outcomes and means:
[publisher record](https://link.springer.com/book/10.1007/b97478) and
[author's contents and introduction](https://www.cemmap.ac.uk/wp-content/legacy/forms/manskipaper.pdf).
The contribution here is an executable finite contract, exact arithmetic and
witness certificates, independent falsification tests, and an integrity-checked
adapter that keeps a failed model-study gate separate from post-hoc diagnostics.
