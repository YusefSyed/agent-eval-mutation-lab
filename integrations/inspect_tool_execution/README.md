# Persisted tool effects through Inspect

This optional integration uses Inspect's native approval, model-loop, tool, log,
and Docker interfaces around a synthetic SQLite publication registry. A separate
read-only scorer checks actual database history and final state. Publishing here
only changes a database flag; no content is externally hosted.

## Two separate evidence sets

| Execution | Evidence | Observed result |
| --- | --- | --- |
| Mock model, actual Docker tools | 13 deterministic fault fixtures | All expected effects and dispatches matched in two runs; normalized reports and database snapshots were byte-identical. |
| Local Qwen model, actual Docker tools | 24 samples: six benign/adversarial note pairs, repeated twice | Both 12-sample groups completed the permitted task with note exposure before publication; zero forbidden attempts/effects, unknown outcomes, errors, or retries. |

The [deterministic receipt](../../artifacts/inspect-tool-execution/v1/RECEIPT.md)
records denial, approval modification, commit-before-error, rollback, transient
publication/revoke, duplicate/conflicting requests, and false response-text checks.
These are controlled software fixtures, not model-behavior results.

The [completed local-model report](../../artifacts/inspect-tool-execution/local-v1/REPORT.md)
records model-selected tool calls under frozen inputs. All 72 live tool calls were
approved; the model never proposed protected publication, so the live run did not
exercise rejection or fault-injection paths. Neither evidence set establishes a
general safety or failure rate.

The standard-library core, generic Inspect log adapter, and separate frozen
624-trial study are unchanged. The deterministic and local-model integrations have
separate dependency locks. [PROTOCOL.md](PROTOCOL.md) defines the deterministic
acceptance boundary; the completed follow-on's exact inputs are in the
[local-model manifest](local_model/manifest.json).

## Reproduce deterministic acceptance

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
debugging; the independent full-suite verifier rejects partial runs. Every sample
gets a new container. Outputs include synthetic SQLite snapshots, normalized JSON,
and operational Inspect logs. Only the first two are deterministic; logs include
timestamps and generated run IDs. This acceptance path needs no API key or model
download. The pinned public Python image may need an initial anonymous pull.

See [local_model/README.md](local_model/README.md) to review the completed model run
or inspect its frozen execution configuration.

If Docker's desktop credential helper stalls on a public pull, an optional
**task-local** empty Docker config can be used with the existing daemon endpoint
explicitly selected. Preserve Compose plugin discovery in that config if needed.
Do not edit global Docker auth settings, copy credentials, or change the daemon.
This workaround is not required on ordinary Docker/Compose installations.
