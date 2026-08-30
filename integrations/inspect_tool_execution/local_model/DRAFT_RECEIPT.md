# Local-model draft verification receipt

Date: 2026-08-30. This receipt records pre-freeze checks, before any live inference.
The manifest was draft during these checks; execution requires a reviewed frozen
manifest and its exact SHA-256. Subsequent execution status is recorded separately.

Verified before freeze review:

- 26 pure contract/negative tests pass, including independent rejection of an
  unknown summary that conceals a valid forbidden-effect database snapshot.
- Two opt-in real Inspect/Docker smoke cases pass using scripted mock model outputs.
  They verify actual public publication, a denied protected attempt, the prescribed
  logical request ID, both preceding artifact reads, and low-trust note exposure in
  the specific model request that produced each publication decision.
- Native Inspect model-event message pools and long-string attachments are resolved
  with its public helpers before deriving decision exposure. Later note exposure
  cannot retroactively count as exposure at an earlier publication decision.
- Limited/error samples preserve independently observed harmful snapshots; clean
  incomplete snapshots remain unknown. A logging-loss regression independently
  re-reads a real exported forbidden-effect database.
- Missing logs use null exact observations and explicit gate-observed lower bounds.
  Summaries expose denominators for complete/unknown attempt and exposure records.
- Read-only `/api/version` pins and verifies Ollama server `0.33.1`.
  Read-only `/api/tags` confirms the exact Qwen model digest. Read-only `/api/show`
  confirms completion, vision, tools, and thinking capabilities. Preflight supports
  installations where `/api/tags` omits capabilities.
- The instance-scoped native-client lifecycle guard persists its secure HTTP-client
  factory and reapplies restrictions after `initialize()` and closed-client
  recreation. Offline 302/500 tests confirm one request at both SDK and native
  Inspect generation layers, without redirects or extra retry attempts. All those
  HTTP responses come from in-memory MockTransport; no model endpoint is contacted.
- `parallel_tool_calls=false` is advisory because Ollama 0.33.1 ignores it. Inspect
  executes these tools serially; sibling proposals still share one model-decision
  context and cannot acquire exposure from an earlier sibling execution.
- The SDK transport guard, dummy local credential, process-local proxy exclusion,
  disabled redirects, zero SDK/Inspect/sample/task retries, no fallback, exact
  24-sample preservation, and draft execution gate have focused negative checks.
- Ruff passes. The deterministic integration and its versioned evidence are unchanged.

The declared model is `qwen3.5:9b-q4_K_M`, digest
`6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`, at literal
`http://127.0.0.1:11434/v1`. The Qwen model, generation settings, limits, prompt strings, order, and case bytes
are unchanged by these final amendments. Exact prompts, 24 note conditions, order, settings,
limits, and source digests are in `manifest.json` and `cases.json`.

Commands used in this standalone directory:

```sh
uv run pytest
RUN_DOCKER_SMOKE=1 uv run pytest tests/test_mock_smoke.py
uv run ruff check .
uv run python runner.py preflight
```

The local Docker credential-helper workaround from the deterministic integration
was applied only through task-local environment/configuration when running the
mock smoke checks. No global Docker configuration was changed.

Next action at this pre-freeze checkpoint: review the exact manifest, case strings, runner, and independent
re-scorer. If accepted, mark only that manifest approved, record its new byte hash,
and execute once into a new output directory. Preserve all failed, limited, and
not-run samples; do not tune or retry under the same identity. The enforcing gate
means an absence of protected effects is not evidence of model safety. Live model
results and any public claims must remain separate from these mock-only checks.
