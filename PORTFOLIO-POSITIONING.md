# Portfolio and résumé positioning

## Thirty-second project description

Agent Eval Mutation Lab is a Codex-assisted Python 3.12+ evaluation system that
tests whether tool-agent scorers confuse proposed actions, actual execution,
realized harm, and unresolved evidence. Its advanced engine turns 13 synthetic cases
into 104 content-addressed evaluation tasks with typed information-flow boundaries,
transactional resume, corruption-safe caching, schedule-independent execution, and
byte-reproducible evidence exports.

## Role-signal map

| Target role family | Verified project signal | Evidence to open first |
| --- | --- | --- |
| AI evaluation / reliability | Tri-state contracts, mutation operators, receipt ablations, false-safe analysis | `BENCHMARK_CARD.md`, `artifacts/v2/`, static report |
| ML infrastructure / eval platform | Typed task planning, explicit plugins, canonical manifests, deterministic seeds | `engine/contracts.py`, `engine/planner.py`, manifest |
| Backend / platform engineering | Transactional SQLite, idempotent commits, resume, atomic content-addressed objects | `engine/store.py`, `engine/artifacts.py`, persistence tests |
| Reliability / quality engineering | Fail-closed errors, corruption quarantine, schedule equivalence, clean-room reproduction | scheduler/persistence tests, `REPRODUCING.md` |
| Python software engineering | Strict mypy, Protocols, immutable dataclasses, packaging, CLI, CI across 3.12–3.14 | `pyproject.toml`, CI workflow, wheel/sdist receipt |
| Empirical AI / research engineering | Predeclared ontology, exact metrics, ablations, family sensitivity, claim limitations | `DESIGN.md`, `PRIOR_ART.md`, research PDF |

## Current defensible résumé bullets

These bullets describe the verified engineering artifact. The repository's public
assistance disclosure must remain available; do not describe the work as unaided.

- Built a typed offline Python evaluation engine that expands 13 execution-semantic
  agent cases into 104 deterministic scorer tasks across four evidence conditions,
  with strict separation between scorer-visible inputs and oracle-only truth.
- Implemented transactional SQLite resume, idempotent commits, atomic SHA-256 object
  storage, corrupt-cache quarantine, and bounded schedule-independent execution;
  sequential and four-worker runs produce byte-identical canonical exports.
- Designed and tested evidence-dominance tri-state scoring that recorded zero
  false-safe, false-success, or unsupported directional overclaims across four
  finite-corpus conditions, replacing five v1 false-safe classifications with
  abstentions under missing effect evidence.
- Shipped Python 3.12–3.14 CI with strict mypy, Ruff, 54 tests, an 80% package branch
  coverage floor, frozen-artifact verification, clean-room regeneration of 15
  canonical artifacts, and reproducible wheel/source builds.

## Compact one-line project entry

**Agent Eval Mutation Lab** — Python, SQLite, typed protocols, concurrency, mutation
testing, reproducible evaluation. Offline 104-task engine with transactional resume,
content-addressed evidence, schedule-independent execution, and fail-closed
tri-state scorer analysis.

## Technical interview narrative

1. **Problem:** Attempt traces are not proof of execution or harm; final state can
   also hide transient harm.
2. **Decision:** Make the outcome ontology explicit and keep scorer-visible evidence
   structurally separate from simulator truth.
3. **Architecture:** Canonical planning creates immutable task identities; workers
   score only whitelist projections; one coordinator validates, persists, and exports
   in plan order.
4. **Reliability mechanics:** SQLite resume is transactional, cached bytes are
   content-addressed and revalidated, duplicate divergent commits fail, and corrupt
   objects are quarantined and recomputed.
5. **Concurrency tradeoff:** Threads were measured slower on the tiny workload, so
   they remain an opt-in correctness stress mode rather than a performance claim.
6. **Empirical result:** v2 exchanges coverage for lower directional risk under
   missing evidence on this finite corpus; no generalization claim is made.
7. **Limitation:** External blind review and separately authored holdout cases are
   still pending, and the repository is Codex-assisted.

## Claims to avoid

- “Independently coded” or “proof of Python fluency.”
- “Production-grade distributed evaluation platform.”
- “Statistically validated” or “generalizes to real agents.”
- “Made Inspect/AgentDojo safe” or “found a new framework vulnerability.”
- “100% accurate” without the finite-corpus and coverage qualifiers.
- “Parallel speedup”; the measured local result was a slowdown.

## Highest-value next external evidence

The project no longer needs generic feature breadth. The remaining value comes from
validators outside the implementation loop:

1. one external human completes the blind label packet;
2. a separate author supplies at least four qualifying holdout cases;
3. disagreements remain visible and versioned; and
4. a reviewer or maintainer inspects the public repository or accepts a bounded
   upstream contribution.

Those steps would strengthen empirical credibility. They are not prerequisites for
describing the verified engineering system accurately today.
