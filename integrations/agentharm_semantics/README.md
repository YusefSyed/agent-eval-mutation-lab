# AgentHarm transcript semantics audit

This optional integration runs pinned AgentHarm grading code on controlled benign transcripts. It records response association, scoreable-call selection and a benign email-link criterion alongside separately observed fixture files. It supports discussion of [Inspect Evals review #2290](https://github.com/UKGovernmentBEIS/inspect_evals/issues/2290). It does not change AgentHarm's grading policy or task version.

## Reproduce

Use Python 3.12 and the repository's pinned uv version. Dependency installation needs network access. The audit and tests use a mock model and block runtime socket connections; no model API key, GPU or benchmark dataset download is needed.

```sh
cd integrations/agentharm_semantics
uv tool run --from uv==0.12.5 uv sync --frozen --group dev --python 3.12
.venv/bin/python -m pytest
.venv/bin/ruff check src tests
.venv/bin/mypy src tests
.venv/bin/agentharm-semantics-audit --output ../../tmp/agentharm-audit
.venv/bin/agentharm-semantics-audit --output ../../artifacts/agentharm-semantics/v1 --verify
```

The first audit command writes `results.json`, `REPORT.md` and `SHA256SUMS` to a new output directory. Operational Python/distribution versions are printed separately, so they do not change canonical observations when the pinned source and outputs are identical. The verification command regenerates the report in a fresh temporary directory and compares every output byte with the committed packet. Nonempty output directories are preserved. Use a new directory for a changed experiment.

## Pinned code and purpose

- Inspect Evals: `4bd4bb9bc62830be9684ae2ab3804e7cd818af7a`, AgentHarm task version `8-B`.
- Inspect AI: `ce5617d35a19a2f4ed0e30f00110126fe0be8f3e`.
- `uv.lock` pins dependencies. The report includes the lock digest and hashes of the grading helpers, selected benign grader, scorer, task metadata, AgentHarm license and relevant Inspect call-execution sources. Changed source or lock bytes are rejected before the audit runs. Run from the synced source checkout; a standalone installed wheel without that lockfile is insufficient for verification.

AgentHarm's license includes an additional safety/security purpose restriction. This work is for evaluating and improving AI-safety measurement. The full notice is preserved in [UPSTREAM_LICENSE.txt](UPSTREAM_LICENSE.txt). The upstream implementation is imported as a dependency; its dataset and grader source are not copied into this integration. The repository's standard-library core and frozen model-study artifacts remain separate.

## What executes

The fixture publisher writes a small JSON artifact in a temporary directory. The audit reads those files after grading. The publisher and observer belong to the same controlled fixture; the files are not independent upstream execution evidence. No website is contacted. Image and email tool messages are scripted, and no image service or email sender is invoked.

Fourteen helper fixtures cover ordered calls, validation rejection, missing responses, empty successful responses, retries, injected error labels and externally reordered responses. Timeout and output-limit labels are injected around a controlled write. They do not exercise Inspect's timer, tool timeout or output-truncation mechanisms.

Three paired fixtures have identical visible transcripts and helper outputs with different recorded file effects. They demonstrate the information missing from these constructed transcripts. They do not establish how frequently such histories occur in deployed agents.

Seven fixtures run the upstream benign `grade_fake_news_source` function with animal-rescue content. The semantic judge uses `mockllm/model` with a fixed pass output for nonempty content. The deterministic `correct_email_content` criterion is the subject of comparison. A matching-link positive control and a wrong-link negative control accompany the absence/error cases. In five selected fixtures, the criterion gives credit despite the email containing no publication link. The code uses an empty string in a substring check.

Two tests replay controlled messages through an Inspect `Task` and AgentHarm's `combined_scorer`, checking the numerical score. These test scoring integration rather than a normal agent/tool execution loop. Fixture-state references never enter the scorer's sample metadata.

## Interpretation and review boundaries

Response IDs are inferred from the fixture's distinct argument values. Identical-argument ambiguity is rejected by the audit. A missing response is reported separately from a matched response. The two association mismatches occur in a partial transcript and an externally reordered transcript. Inspect's completed tool execution preserves declared response order, so no native parallel-execution defect is claimed.

The [AgentHarm paper](https://arxiv.org/abs/2410.09024) describes multi-step, argument-aware rubrics with synthetic tools. It does not settle the reviewed edge-case policy for rejected, incomplete or post-execution-error histories. An attempted call, harmful willingness, execution and effects are different constructs. The current helpers' choice to retain missing-response calls is a documented legacy policy. This audit records it without imposing a replacement.

The fixtures are a development catalog selected to examine known concerns. They are not held-out model samples, an attack-success rate, a population safety estimate or a new evaluation result comparable with the paper's model scores. The reported criterion means use mocked semantic judgments. No model behavior or safety improvement was demonstrated.

Any scoring change, historical-result recomputation or task-version change needs maintainer direction. The current contribution is an executable evidence packet for their review. No incremental AgentHarm scoring PR is opened by this code. Prepared with OpenAI Codex; artifact existence does not establish unaided contributor mastery.
