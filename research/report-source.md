# Python flagship project research report

**Audience:** early-career software, AI-product, evaluation, and research-engineering
candidate  
**Date:** 2026-08-28  
**Decision:** build a narrow original offline Python scorer-mutation benchmark;
retain a conventional PyTorch replication as the fallback if originality or validity
gates fail.

## Executive answer

The current résumé demonstrates shipped product engineering and evaluation judgment,
but its named projects are TypeScript/JavaScript/Deno while Python appears only in the
skills list. Current official role evidence makes that gap consequential:

- Anthropic's Fellows description asks for strong Python skills, empirical research,
  open-source or impactful projects, and independent execution.
- Scale's AI Builder internship asks for production-quality Python and/or JavaScript,
  real LLM tools, agentic frameworks, measurement, and an active portfolio.
- Quadrillion's internship asks for significant engineering ability in Python or
  React while building an agentic computational-research platform.
- Current Netic and similar agent-platform roles add Python async/FastAPI and agent
  orchestration to the same pattern.

Sources:
[Anthropic Fellows](https://red.anthropic.com/2024/anthropic-fellows-program/),
[Scale AI Builder Intern](https://scale.com/careers/4703343005),
[Quadrillion Software Engineering Intern](https://jobs.ashbyhq.com/quadrillion-labs/601e105d-2f0f-4482-9bae-3a825a1b97fd),
[Netic Agent Platform Intern](https://jobs.ashbyhq.com/netic/b0ea7aab-8eea-4d31-96f9-278364180ae7/).

The strongest project direction is not a copied portfolio clone or another consumer
app. It is a public Python evaluation artifact with an offline core, a predeclared
question, coherent baselines, controlled mutations, deterministic evidence, explicit
limitations, and a path to external framework interoperability.

## Candidate frameworks and reuse decision

Inspect AI, ControlArena, and AgentDojo are active MIT-licensed Python projects.
They supply credible task/scorer/log, AI-control, and prompt-injection benchmark
ecosystems. They should be used later as dependencies or adapter targets. Forking a
large repository would make most of the visible architecture upstream-owned and risk
producing a narrow patch without a coherent empirical artifact.

Sources:
[Inspect tasks](https://inspect.aisi.org.uk/tasks.html),
[Inspect logs](https://inspect.aisi.org.uk/eval-logs.html),
[ControlArena](https://github.com/UKGovernmentBEIS/control-arena),
[AgentDojo](https://github.com/ethz-spylab/agentdojo).

## Prior-art correction

An initial proposal to compare tool-name allowlisting with argument-aware authorization
was rejected after finding Agent Security Gate, which already implements a broader
Python policy gate and related benchmarks. AgentDojo issue #168 then supplied a
different, evidence-backed problem: security scoring can confuse attempted-but-blocked
calls with successful execution. A separate reproduction means simply restaging that
bug would also be too weak.

The selected question generalizes beyond one bug: can execution-semantic mutations
test whether trajectory scorers preserve distinctions among proposals, execution,
transient effects, final state, and missing evidence?

## Gap matrix

| Claim | Evidence | Confidence | Remaining gap |
| --- | --- | --- | --- |
| Python is asserted but not demonstrated by a named flagship | Current résumé source and shared feedback | High | Public Python project plus separate independent gate |
| Target roles value Python plus eval/agent/research engineering | Official role pages | High for cited roles | Role availability can change; recheck before applying |
| Established frameworks are reusable and permissively licensed | Official docs and GitHub licenses | High | Choose adapter only after core report works |
| Argument-aware authorization is already substantially covered | Agent Security Gate public repository | High | Do not duplicate |
| Attempt/execution scoring confusion is real | AgentDojo issue #168 and reproduction | High for that task | Broader prevalence is unknown |
| Scorer mutation benchmark is sufficiently distinct to prototype | Targeted repository/paper search plus two Pro reviews | Moderate | Holdout, independent review, and wider prior-art search |
| Current project proves independent Python fluency | Contradicted by learning-gate state and assistance record | High | Protected ownership gate remains unpassed |

## Recommendation and limits

Implement the offline kernel, but limit the claim to exact synthetic results. The
full flagship still needs a frozen corpus, hidden or independently authored mutation
family, receipt ablations, family-level sensitivity analysis, representative failure
analysis, and one real-log adapter. The repository must remain labelled Codex-assisted
until the separate no-AI ownership gate passes.

## Claim-to-source ledger

| Claim | Source | Publisher | Access note |
| --- | --- | --- | --- |
| Fellows values Python, empirical research, open source, and independent execution | Introducing the Anthropic Fellows Program | Anthropic | Official public page; historical cohort details may differ from current listing |
| Scale AI Builder values Python/JS, agentic workflows, evals, measurement, and portfolio evidence | AI Builder Intern | Scale AI | Official posting was searchable; direct page later redirected to careers index |
| Quadrillion asks for Python or React and builds an agentic research platform | Software Engineering Intern | Quadrillion / Ashby | Official ATS page |
| Inspect task = dataset + solver + scorer; logs preserve results and samples | Tasks and Log Files | UK AI Security Institute | Official documentation |
| ControlArena provides settings, protocols, monitors, scorers, and safety/usefulness analysis | ControlArena README | UK AI Security Institute and Redwood Research | Official GitHub repository, MIT license |
| AgentDojo is an MIT prompt-injection benchmark with programmatic utility/security scoring | AgentDojo README and paper | ETH Zurich SPY Lab and collaborators | Official GitHub/OpenReview sources |
| AgentDojo issue documents attempted-but-blocked calls scored as success | Issue #168 | AgentDojo public tracker | Open issue plus independent reproduction comment |
| Mutation testing is established prior art | SWE-Mutation, LLMorpheus, Breaking Models to Test the Judge | Research authors | Primary papers; exact tool-agent-scorer combination not established |

## Continuation update - real-log evidence and ablations

Targeted follow-up research selected Inspect AI 0.3.260 as the first adapter target.
Its official `ToolEvent` schema records call ID, function, arguments, result, structured
error, completion timestamp, and hard-failure state. Its separate `ApprovalEvent` records
the correlated call and approval decision. A genuine offline run using Inspect's
`mockllm/model` confirmed that approval and tool events correlate on the call ID; policy
rejection produces `decision="reject"` plus `error.type="approval"`, while approved
execution produces a result and completion timestamp.

This evidence supports coarse execution normalization only. Generic Inspect logs do not
establish domain side effects, transient harm, partial execution, or final environment
state. The implemented adapter therefore returns `attack_success_ready: false` and maps
timeouts, cancellations, contradictions, and generic hard failures to unknown rather
than safe.

AgentDojo's public run JSON records model proposals, tool messages, aggregate utility,
and security results but does not bind those proposals to a generic execution receipt.
Its open issue #168 is direct evidence of the resulting ambiguity. AgentDojo is therefore
a later attributed regression target, not the first adapter.

Receipt ablations against the frozen v1 scorer produced the following exact finite-corpus
results:

| Evidence condition | Accuracy | False-safe | Abstention |
| --- | ---: | ---: | ---: |
| Baseline | 0.917 | 0.000 | 0.083 |
| Remove prohibited receipts | 0.167 | 0.000 | 0.833 |
| Remove effect records | 0.500 | 0.417 | 0.083 |
| Replace success with timeout | 0.333 | 0.000 | 0.667 |

The effect-record ablation exposes a concrete weakness: the v1 receipt-aware scorer can
interpret a successful prohibited call with missing effect details as established
no-harm. That result is now frozen evidence for a future v2 scorer; v1 must not be
silently rewritten.

Additional primary sources:

- [Inspect AI ToolEvent source](https://github.com/UKGovernmentBEIS/inspect_ai/blob/main/src/inspect_ai/event/_tool.py)
- [Inspect AI ApprovalEvent source](https://github.com/UKGovernmentBEIS/inspect_ai/blob/main/src/inspect_ai/event/_approval.py)
- [Inspect AI log documentation](https://inspect.aisi.org.uk/eval-logs.html)
- [AgentDojo public run format](https://github.com/ethz-spylab/agentdojo/tree/main/runs)
- [AgentDojo issue #168](https://github.com/ethz-spylab/agentdojo/issues/168)
