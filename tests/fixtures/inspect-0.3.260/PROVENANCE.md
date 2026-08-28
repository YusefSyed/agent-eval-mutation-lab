# Inspect fixture provenance

`approved.json` and `rejected.json` are minimized, sanitized excerpts from genuine
plain-JSON logs generated locally with Inspect AI `0.3.260`, its `mockllm/model`,
one synthetic tool, and an approval policy. Tool-call IDs were retained because
correlation is the behavior under test; high-entropy event IDs and exact timestamps
were removed or normalized.

`timeout.json` is a schema-conforming synthetic negative fixture based on Inspect's
documented `ToolEvent` and `ToolCallError(type="timeout")` contracts. It is not
presented as a captured timeout run.

The genuine run established:

- approval and tool events correlate on `call.id` / `tool.id`;
- an approved successful call has a result and completion timestamp; and
- a rejected call produces `ApprovalEvent(decision="reject")` plus a correlated
  `ToolEvent(error.type="approval")` with no tool result.

Regeneration helper:

```text
uv run --with inspect-ai research/generate_inspect_fixture.py --output tmp/inspect-fixtures
```

