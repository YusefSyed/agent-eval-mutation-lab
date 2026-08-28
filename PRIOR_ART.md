# Prior art and attribution boundary

This repository was designed after a scoped search of current target-role demands,
agent-evaluation frameworks, public issue trackers, and mutation-testing research.
It contains no copied source code from the projects below.

## Directly motivating evidence

- [AgentDojo](https://github.com/ethz-spylab/agentdojo) is an MIT-licensed Python
  environment for prompt-injection attacks and defenses. Its public
  [issue #168](https://github.com/ethz-spylab/agentdojo/issues/168) documents a
  scorer that can treat attempted-but-blocked calls as successful execution. A
  separate reproduction is linked in that issue. This project does not claim to
  discover that bug.
- [Inspect AI evaluation best practices](https://github.com/UKGovernmentBEIS/inspect_evals/blob/main/BEST_PRACTICES.md)
  say scoring should align with the actual outcome. Inspect's task, scorer, and log
  APIs are a potential later adapter target, not code copied into this kernel.
- [ControlArena](https://github.com/UKGovernmentBEIS/control-arena) is an
  MIT-licensed Python framework for AI-control policies, monitors, settings, and
  safety/usefulness analysis. This project does not replace those abstractions.

## Mutation-testing lineage

- [SWE-Mutation](https://arxiv.org/abs/2605.22175) applies mutation testing to
  evaluate generated software test suites.
- [LLMorpheus](https://arxiv.org/abs/2404.09952) studies LLM-generated program
  mutants for software mutation testing.
- [Breaking Models to Test the Judge](https://arxiv.org/abs/2608.14315) applies
  mutation testing to semantic evaluators in the domain of class diagrams.

These works mean the honest claim is adaptation, not invention: this project adapts
established mutation-testing principles to execution-semantic tool-agent scorers.

## Rejected overlap

[Agent Security Gate](https://github.com/giselleevita/agent-security-gate) is an
Apache-2.0 Python project with policy enforcement, approvals, audit receipts, an
18-scenario benchmark, and an AgentDojo study. An earlier idea to build a smaller
argument-aware authorization gate was rejected because it overlapped substantially
with this work.

## Scoped originality statement

A targeted search did not identify a public benchmark with the exact combination of
an attempt/execution/harm ontology, execution-semantic mutation operators, scorer-
contract comparisons, and a framework-independent finite corpus. That is not proof
of priority and does not support a "first-ever" claim. The contribution claim must
remain limited to the released artifact, its exact cases, and its measured results.

## Adapter evidence

- [Inspect AI `ToolEvent`](https://github.com/UKGovernmentBEIS/inspect_ai/blob/main/src/inspect_ai/event/_tool.py)
  records call identity, arguments, results, structured errors, completion, and hard
  failures.
- [Inspect AI `ApprovalEvent`](https://github.com/UKGovernmentBEIS/inspect_ai/blob/main/src/inspect_ai/event/_approval.py)
  records the call and approval decision separately.
- [AgentDojo issue #168](https://github.com/ethz-spylab/agentdojo/issues/168)
  documents why attempted-call traces alone are not execution receipts.

The Inspect adapter is original glue and evidence classification around public schemas;
it is not copied Inspect code and does not claim to make generic logs sufficient for
attack-success scoring.
