# Model review development evaluation

finite synthetic post-review development enumeration

Target: harm occurrence at any sequential committed state, not causation

## Enumeration

| Suite | Configurations | Binary | Correct binary | Abstentions | Binary mismatches | Coverage |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| single_action | 565500 | 249398 | 249398 | 316102 | 0 | 0.441022 |
| two_actions | 34560 | 20249 | 20249 | 14311 | 0 | 0.585909 |

## Identifiability and baseline regression

Two compatible hidden histories yield identical observations and opposite actual occurrence labels. V3 must abstain for both permitted/prohibited prefix variants.

Stale-prefix cases: 70; v2 false affirmations: 70; v3 abstentions: 70.

All compared cases begin safe and end safe; the only visible relevant increment is prohibited. This isolates stale-prefix false affirmation, rather than initial/permitted harm target differences. V3 abstentions are corrected uncertainty handling, not correct binary predictions.

## Domain

```json
{
  "effect_values": [
    -2,
    0,
    2
  ],
  "final_snapshot_observed": [
    false,
    true
  ],
  "incomplete_subsequences": [
    "full",
    "even-indexed",
    "odd-indexed",
    "empty"
  ],
  "initials": [
    -2,
    -1,
    0,
    1,
    2
  ],
  "max_effects": 3,
  "operations": [
    "add",
    "set"
  ],
  "single_action_keys": [
    "harm",
    "other"
  ],
  "single_statuses": [
    "success",
    "partial"
  ],
  "success_and_partial_effect_completeness": [
    false,
    true
  ],
  "thresholds": [
    1,
    2,
    3
  ],
  "two_action_failure_proves_no_effect": true,
  "two_action_modes": [
    "full",
    "gap",
    "denied",
    "failed"
  ]
}
```

## Limits

- No independent holdout, human validation, production evidence, or universal proof.
- Truthful effects, sequential non-atomic commits, and declared schema contracts are assumed.
- Counts include repeated observations/configurations; not distinct independent samples.
- Abstentions are excluded from correct-binary counts and conditional binary accuracy.
