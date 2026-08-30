# Persisted tool effects through Inspect

This standalone integration uses Inspect's real approval, agent-loop, tool, log,
and Docker interfaces around a synthetic SQLite publication registry. A separate
read-only scorer checks actual database history and final state. Publishing here
only changes a database flag; no content is publicly hosted.

The deterministic runner uses Inspect's mock model. It proves integration behavior,
not live agent choices or general safety. See [PROTOCOL.md](PROTOCOL.md) for the trust
boundary, failure semantics, acceptance contract, and proposed local-model follow-on.
The repository's frozen benchmark and model study remain unchanged.

From this directory, with Python 3.12+, uv, Docker, and Compose available:

```sh
uv sync --frozen --dev
uv run pytest
uv run ruff check .
uv run inspect-tool-execution --output tmp/run-one
uv run inspect-tool-execution --output tmp/run-two
uv run python -m inspect_tool_execution.verify tmp/run-one --compare tmp/run-two
```

Output directories must be new or empty. `--case CASE_ID` selects one fixture for
debugging; the independent full-suite verifier rejects partial runs.
Every sample gets a new container. Outputs include raw synthetic SQLite snapshots,
normalized JSON, and operational Inspect logs. Only the first two are deterministic;
the logs include timestamps and generated run IDs. No API key or model download is
needed. The pinned public Python image may need an initial anonymous pull.

If Docker's desktop credential helper stalls on a public pull, an optional
**task-local** empty Docker config can be used with the existing daemon endpoint
explicitly selected. Preserve Compose plugin discovery in that config if needed.
Do not edit global Docker auth settings, copy credentials, or change the daemon.
This local workaround is not required on ordinary Docker/Compose installations.
