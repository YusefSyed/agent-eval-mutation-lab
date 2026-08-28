# Milestone 1 receipt - offline benchmark kernel

**Date:** 2026-08-28  
**Initial implementation commit:** `970e4e0`  
**Status:** verified local milestone; not pushed, published, or resume-ready

## Objective achieved in this milestone

Created a standalone Python 3.12+ project that tests whether execution-semantic
mutations expose scorer contract failures. The runtime is standard-library only,
offline, and API-key free.

## Verified implementation

- 13 synthetic cases across five scenario families.
- Seven execution-semantic mutation types.
- Separate attempt, execution, transient-harm, final-state, and unknown outcomes.
- Attempted-call, final-state-only, and receipt-aware substantive scorers.
- Always-safe, always-attack, and always-abstain sanity controls.
- Deterministic JSON and Markdown reports.
- Six-page cited research/build-decision PDF, rendered and visually inspected.

## Checks and outcomes

```text
uv run pytest       -> 8 passed
uv run ruff check . -> all checks passed
uv run mypy         -> no issues in 10 source files
two clean runs      -> byte-identical JSON and Markdown
PDF structural QA  -> 6 pages, 6 nonempty, 24 link annotations
```

Evidence hashes:

```text
results.json  b7ad1de4c15cabd64360c55e2ba451ecc813d8e3a3abe1dfac904589234ef093
results.md    a190efd319ef7bbee78596f4e804379baada352a2afe284ad2e87de4c5c1f775
PDF           f9e5eedd3665c4dcc57d2996b8e168c6ebb0133f61736f3498d3e54e9243524d
```

## Observed finite-corpus results

- Attempted-call scorer: 0.667 accuracy, 0.333 false-success rate against the
  attack-success target, and 0.000 label-changing semantic score.
- Final-state scorer: 0.917 accuracy, 0.083 false-safe rate, 0.800
  label-changing score, and 0.500 label-preserving invariance.
- Receipt-aware scorer: 0.917 accuracy, zero false-safe/false-success rates,
  1.000 label-changing score, 1.000 invariance, and 0.083 abstention.

These results describe only the released synthetic corpus. The attempted-call
result diagnoses a target-contract mismatch; it does not show that attempt
detection is intrinsically defective.

## Deferred gates

1. Freeze the initial corpus and scorers.
2. Add a held-out or separately authored mutation family.
3. Predeclare and run receipt-field ablations.
4. Add family-level leave-one-out sensitivity.
5. Obtain independent case-label review.
6. Add one thin real-log adapter if public logs expose the needed semantics.
7. Complete the protected no-AI changed-contract/debugging/explanation/reproduction
   gate before any unaided Python-fluency claim.
8. Recheck all live role postings before changing the resume.

## Do not claim yet

- independent Python fluency;
- a completed empirical research study;
- first-ever mutation testing for agent scorers;
- that Inspect, ControlArena, AgentDojo, or another framework is unsafe;
- an accepted upstream contribution; or
- a public GitHub release.

