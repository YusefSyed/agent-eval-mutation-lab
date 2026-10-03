"""Private fixed-command per-invocation telemetry; never reads DB history."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import registry

RECEIPTS = Path("/state/receipts")


def produce(
    database: Path,
    directory: Path,
    sample: str,
    invocation: str,
    function: str,
    arguments: dict[str, str],
    fault: str = "none",
) -> dict:
    registry.identifier(sample)
    registry.identifier(invocation)
    if fault not in {"none", "before_commit", "after_commit"}:
        raise ValueError("invalid trusted fault")
    expected = {"artifact_id"}
    if function != "inspect_artifact":
        expected.add("request_id")
    if set(arguments) != expected:
        raise ValueError("invalid arguments")
    for value in arguments.values():
        registry.identifier(value)
    receipt = {
        "sample_id": sample,
        "invocation_id": invocation,
        "function": function,
        "arguments": arguments,
        "disposition": "unknown",
        "effects": [],
        "effects_complete": False,
    }
    directory.mkdir(exist_ok=True)
    # Reserve before any SQL effect. A crash/write failure leaves an invalid
    # incomplete sidecar, never a complete empty-effect certificate.
    with (directory / (invocation + ".json")).open("x") as stream:
        error = None
        result = None
        try:
            if function == "inspect_artifact":
                result = registry.inspect_artifact(database, arguments["artifact_id"])
                receipt.update(disposition="success", effects_complete=True)
            else:
                result = registry.mutate(
                    database,
                    function,
                    arguments["artifact_id"],
                    arguments["request_id"],
                    "before_commit" if fault == "before_commit" else "none",
                )
                receipt.update(disposition="success", effects_complete=True)
                if not result["deduplicated"]:
                    receipt["effects"] = [
                        {
                            "key": arguments["artifact_id"] + ".published",
                            "operation": "set",
                            "value": int(function == "publish_artifact"),
                        }
                    ]
                    if fault == "after_commit":
                        receipt["disposition"] = "partial"
                        error = RuntimeError("injected after-commit response failure")
        except Exception as caught:
            error = caught
            if (
                fault == "before_commit"
                and type(caught) is RuntimeError
                and str(caught) == "injected before-commit failure"
            ):
                receipt.update(disposition="failed", effects_complete=True)
        stream.write(json.dumps(receipt, sort_keys=True) + "\n")
    if error is not None:
        raise error
    assert result is not None
    return result


def main() -> None:
    sample, invocation, function, encoded, fault = sys.argv[1:]
    result = produce(
        registry.DATABASE,
        RECEIPTS,
        sample,
        invocation,
        function,
        json.loads(encoded),
        fault,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2) from None
