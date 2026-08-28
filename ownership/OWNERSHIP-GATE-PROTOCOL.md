# Protected project-ownership gate

## Purpose

Measure whether the project owner can independently implement, debug, explain, and
reproduce the benchmark after Codex-assisted construction.

This gate is separate from project correctness. Passing tests on Codex-authored code
does not pass the ownership gate.

## Current prerequisite

The existing protected Python foundation baseline in `python-learning` is staged but
not started. The project-specific ownership task must remain unrevealed until that
foundation attempt has been completed, reviewed, and recorded as passed.

Run the fail-closed preflight:

```text
uv run agent-eval-ownership-preflight
```

The expected current result is `ready: false` with a missing-foundation-evidence
blocker. Do not bypass it by editing the generated preflight result.

## Foundation evidence contract

After the foundation baseline is genuinely completed and reviewed, create
`ownership/FOUNDATION-EVIDENCE.json` from the example. It must point to the preserved
result artifact and include its exact SHA-256 hash. The preflight validates the file
and hash; the pass/review fields remain human-recorded evidence rather than something
this repository can independently prove.

## Ownership gate phases

The exact task content is intentionally not stored or revealed yet.

When readiness is true, a future start command should create a fresh attempt directory
and reveal one task at a time:

1. changed-contract implementation in a protected blank file;
2. diagnosis and repair of an unfamiliar seeded defect;
3. clean reproduction of benchmark evidence; and
4. oral explanation of the outcome ontology, v1/v2 tradeoff, metrics, limitations,
   and one rejected alternative.

## Integrity rules

- Do not start from this Codex task.
- Close Codex, ChatGPT, Copilot, Claude, Gemini, AI search, and every other AI surface.
- Do not inspect a future hidden task or evaluator before the timer starts.
- Work only in the generated attempt directory.
- Preserve incomplete work and errors; do not rehearse or silently replace them.
- Reopen Codex only after the attempt is finalized and hashed.

## Evidence required before a fluency claim

- preserved timed attempt files and timestamps;
- exact start/final hashes;
- tests and failure output;
- changed-contract implementation evidence;
- seeded-defect diagnosis and repair evidence;
- clean reproduction output; and
- recorded oral defense reviewed by a human.

No single phase, self-attestation, or passing repository test is sufficient on its own.

