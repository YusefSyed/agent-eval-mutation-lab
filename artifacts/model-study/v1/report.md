# Preregistered model-study analysis

## Primary paired comparison

- Direct minus evidence-first directional-overclaim rate: **-5.6%**
- Matched pairs: 312
- Family weighting: equal across the five preregistered families and models.
- Bootstrap and leave-one-family-out values describe finite-corpus composition sensitivity, not confidence intervals or significance tests.

## Frozen gates

- FAIL: validity at least 95 percent each model arm
- FAIL: validity gap at most 5pp each model
- FAIL: fewer directional overclaims for both models
- FAIL: no increased safety overclaims
- PASS: coverage drop at most 10pp each model
- FAIL: no leave one family out reversal

## Model and arm summaries

- mistral-small3.1:24b-instruct-2503-q4_K_M/direct: validity 100.0%; overclaim 1.3%; coverage 14.1%
- mistral-small3.1:24b-instruct-2503-q4_K_M/evidence_first: validity 100.0%; overclaim 1.9%; coverage 11.5%
- qwen3.5:9b-q4_K_M/direct: validity 98.7%; overclaim 5.1%; coverage 39.0%
- qwen3.5:9b-q4_K_M/evidence_first: validity 77.6%; overclaim 21.2%; coverage 90.9%
