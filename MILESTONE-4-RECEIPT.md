# Milestone 4 receipt - guarded holdout and ownership readiness

**Date:** 2026-08-28
**Status:** verified local preparation; external evidence still missing

## Objective achieved in this milestone

Added a fail-closed validator for separately authored holdout submissions and a
project-ownership preflight that refuses to reveal or start the protected task until a
reviewed, hashed, no-AI foundation result exists.

## Holdout intake boundary

The validator checks:

- at least four cases across at least two families;
- unique case and action identities;
- valid statuses, effects, receipts, and non-executing/effect consistency;
- a named semantic relation and a 30-character distinctness rationale per case;
- label-changing, label-preserving, or evidence-withholding relation type;
- at least one relation name not used by current families/mutations; and
- self-reported independent authorship with no scorer source, prior labels, or AI use.

The result explicitly says attestation and distinctness are self-reported. No external
submission exists, no cases were imported, and no heldout claim is supported yet.

## Ownership preflight boundary

The preflight checks:

- the seven-file frozen v1 lock;
- presence of the v2 comparison artifact;
- absence of an active ownership attempt;
- a protected blank-file foundation result;
- reviewed/pass/no-AI fields;
- preserved result path existence; and
- exact SHA-256 agreement.

Current result:

```text
ready: false
baseline_lock_verified: true
ownership_task_revealed: false
blocker: reviewed foundation evidence is missing
```

Two independently created temporary output directories produced byte-identical
preflight reports and identical nonzero exit status. The exact ownership task remains
unstored and unrevealed.

## Checks and outcomes

```text
uv run pytest                    -> 38 passed
uv run ruff check .              -> all checks passed
uv run mypy                      -> no issues in 20 source files
agent-eval-verify-lock           -> 7 frozen v1 files verified
ownership preflight, two runs    -> byte-identical; exit 1 as expected
secret-pattern scan              -> no findings
```

## Evidence hashes

```text
holdout intake source   b9758e70a19687257dcaeef276d9e6f0aa8c71f44f60219d5439578dee29d973
ownership preflight     ec6eae4b16367b2479cc5cff555b67c3510897e0ae6cdd56700c606fda629b1e
holdout schema          c8d841b12d2461d19959583e54eb7b40032d8b7fe2cbcc513f9836e0dad9d3ff
review protocol         ac3c1821b83a5b721ed0042636741019148f5d13036ac99e16ea20d7e3e6e535
ownership protocol      5991c76d217b8688660626bd4f24e21ef797d90cb9b80986c28341ebd3b79510
current preflight JSON  79e4ec2fde4365359354f8050229b121fbf5c7510c2e3c4f2271d86178ca6288
```

## Remaining gates

1. The user completes and finalizes the existing protected Python foundation baseline
   with every AI surface closed.
2. The result is reviewed, passed, preserved, and recorded with its exact hash.
3. Only then may the project-specific ownership task be generated and started.
4. An external human completes the blind label review.
5. A separate author submits at least four qualifying holdout cases.
6. Disagreements are preserved and resolved through versioned evidence.
7. Publishing and resume changes occur only after these gates pass.

## Do not claim yet

- ownership-gate readiness;
- independent Python fluency;
- independently audited labels;
- a validated heldout result;
- completed empirical research; or
- a public GitHub release.

