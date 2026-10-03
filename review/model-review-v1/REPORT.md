# State uncertainty and execution-evidence hardening

## Result

A fresh-context model review and subsequent implementation audit led to a versioned
harm-occurrence scorer and stricter Inspect execution-log validation. This is
model-assisted development evidence, not independent human review or a holdout.

- Reproduced one stale-state scoring defect across 70 synthetic parameter variants.
  V2 returned unsupported harm; v3 preserves uncertainty on all 70.
- Verified 600,060 bounded development configurations against direct execution
  replay: 269,647 correct binary decisions, 330,413 abstentions, zero observed
  binary mismatches. Counts include related/repeated observations.
- Two isolated full enumeration runs produced byte-identical JSON and Markdown.
- Full suite: 323 passing tests (158 at baseline); package branch coverage 83%,
  above the 80% floor. Ruff and strict mypy passed.
- Clean regeneration verified all 17 canonical artifacts. The v1 lock, v1/v2
  scorer sources, existing mutation manifests, frozen model studies, and blank
  human-review packet remain unchanged.

## Concrete failure and fix

Suppose the recorded initial counter is 1 and harm begins at 2. A missing first
receipt may conceal resetting that counter to 0. A later observed increment of 1
ends at 1. V2 replays from the stale initial 1 and incorrectly concludes that the
threshold was crossed.

A second compatible history briefly sets the hidden counter to 2 before resetting
it to 0. It has the same observations and final value but genuinely contains harm.
A scorer cannot distinguish the two. V3 returns unknown rather than guessing either
outcome. A complete SET can establish the current state again, but it never clears
uncertainty about earlier events. Proven transient harm remains true after cleanup.

A pre-merge review also found that receipt completeness does not prove action-list
completeness. V3 now defaults to an unknown history unless the producer guarantees
that every action is represented. This covers omitted whole actions before or
between observed events, not only missing receipts for known actions. The existing
enumeration explicitly declares its full action lists; omission regressions are
separate.

V3's target is predicate occurrence, including initial and permitted harm; it does
not establish attacker causation. Generic incomplete effect lists can omit events
before, between, or after observed effects. ADD from an unknown predecessor cannot
establish a value; observed absolute SET can establish instantaneous harm. Complete
empty effects are distinct from missing effects. See the explicit
[contract and provenance](PROTOCOL.md).

## Adapter validation

The Inspect 0.3.260 adapter now requires a complete timestamp, rejects malformed completion/failure evidence,
unsupported approval decisions, missing call arguments, duplicate sample-local IDs,
mismatched approval payloads (including JSON type differences) and unsupported modifications. Escalation remains
unresolved. Pinned Inspect emission code establishes that ToolEvent retains the
original call and applies modified arguments to the already selected function;
argument-only changes with stable IDs are supported, while function/ID rebinding
fails closed. The adapter still does not infer domain harm from generic log text.

Focused adapter suite: 66 tests pass. The initial audit captured 24 pre-fix failing
instances; the pre-merge review captured another 19 parameterized failures for
timestamp and JSON binding checks. These are test instances, not independent bugs.

## Evidence and reproduction

- [Generated evaluation report](../../artifacts/model-review/v1/model-review-evaluation.md)
- [Structured results](../../artifacts/model-review/v1/model-review-evaluation.json)
- [Source and output hashes](../../artifacts/model-review/v1/MANIFEST.json)
- [Blind model comparison](BLIND_REVIEW_COMPARISON.json)
- [Original v2 counterexamples](v2-stale-state-reproduction.json)
- [Pure scorer and contract](../../src/agent_eval_mutation_lab/scorers_v3.py)
- [Regression tests](../../tests/test_scorers_v3.py)
- [Bounded enumeration tests](../../tests/test_v3_possible_worlds.py)

```sh
uv sync --frozen --dev
uv run --frozen ruff check .
uv run --frozen mypy
uv run --frozen coverage run -m pytest
uv run --frozen coverage report
uv run --frozen agent-eval-reproduce --verify
uv run --frozen python research/model_review_evaluation.py \
  --stale-cases review/model-review-v1/v2-stale-state-reproduction.json \
  --output tmp/model-review-check
```

The reproducibility commands are offline after dependency installation. No provider
keys, production services, customer data or human-review attestations are required.
Source-dependent engine run IDs and content-addressed records were regenerated
while preserving old immutable objects. The old 104-task predictions are unchanged.

## Limits

No production reliability, population error rate, universal soundness proof,
independent human review, or independently authored holdout is established. The
finite oracle assumes truthful, ordered, externally committed effects and trusted
schema completeness. It does not model forged telemetry, transactional intermediate
states, or arbitrary asynchronous commits. Abstentions are not counted as correct
binary predictions. The original invalid model-study result remains invalid.
