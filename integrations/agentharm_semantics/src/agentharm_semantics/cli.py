"""Generate or verify a deterministic AgentHarm observation report."""

import argparse
import asyncio
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

from agentharm_semantics.audit import canonical, run_audit, verify_observations
from agentharm_semantics.provenance import runtime_environment, verify_upstream


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# AgentHarm transcript and effect audit",
        "",
        (
            "The pinned upstream graders ran on controlled benign fixtures. "
            "The source was not changed. Semantic model judgments use Inspect's "
            "mock model. These observations do not measure model safety or a "
            "population failure rate."
        ),
        "",
        "## Helper observations",
        "",
        "| Case | Eligible calls | Fixture-inferred ID | Response status | Effects |",
        "| --- | ---: | --- | --- | ---: |",
    ]
    for row in report["helper_cases"]:
        h = row["helper"]
        lines.append(
            f"| {row['case']} | {h['eligible_call_count']} "
            f"| {h['fixture_inferred_call_id']} "
            f"| {h['response_association']} | {len(row['fixture_publications'])} |"
        )
    lines += ["", "## Identical transcript, different effects", ""]
    for pair in report["indistinguishable_pairs"]:
        lines.append(
            f"- {pair['cases'][0]} and {pair['cases'][1]} have identical transcripts "
            "and helper outputs, while separately observed fixture files differ."
        )
    lines += [
        "",
        "## Benign grader criterion",
        "",
        (
            "All cases call the upstream benign `grade_fake_news_source` rubric "
            "with animal-rescue content. No email is sent and no website is contacted."
        ),
        "",
        "| Case | Email-link credit | Nonempty link present | Criterion mean |",
        "| --- | --- | --- | ---: |",
    ]
    for row in report["grader_cases"]:
        lines.append(
            f"| {row['case']} | {row['criteria']['correct_email_content']} "
            f"| {row['reference_nonempty_publication_link_in_email']} "
            f"| {row['criterion_mean']:.6f} |"
        )
    lines += [
        "",
        "## Interpretation limits",
        "",
        (
            "The timeout and output-limit rows inject synthetic ToolCallError "
            "labels around a controlled file write. They do not exercise Inspect's "
            "deadline or output-truncation mechanisms. Publication files are "
            "separately observed fixture state, not upstream tool state. Image "
            "and email messages are scripted fixtures."
        ),
        "",
        (
            "Selected IDs are inferred from the fixture's distinct argument "
            "values; ambiguous identical-argument calls are rejected by the "
            "audit. Missing responses have a separate status from matched ones. "
            "The Inspect integration tests replay these transcripts through "
            "Task and combined_scorer; they do not run a normal agent/tool loop."
        ),
        "",
        (
            "An error or missing response alone does not identify whether the "
            "controlled publication effect occurred. Which calls a benchmark should "
            "credit remains a measurement-policy decision. The response-pairing "
            "observations concern partial or externally reordered transcripts; "
            "Inspect's completed tool execution normally preserves declared "
            "response order."
        ),
        "",
        (
            "The email criterion gives credit in five fixtures whose body contains "
            "no publication link. The code tests an empty string as a substring. "
            "These are observations of a boolean criterion with mocked semantic "
            "judgments, not evidence that a model achieved a harmful task or that "
            "every affected input occurs in a normal evaluation."
        ),
        "",
        (
            "The maintainers' AgentHarm review #2290 governs any resulting "
            "score-policy or version change. This packet proposes fixture coverage "
            "and discussion; it does not replace their benchmark definition."
        ),
        "",
    ]
    return "\n".join(lines)


def generate() -> dict[str, bytes]:
    provenance = verify_upstream()
    with (
        TemporaryDirectory(prefix="agentharm-audit-") as temporary,
        patch(
            "socket.create_connection",
            side_effect=RuntimeError("Network is disabled in this audit"),
        ),
        patch(
            "socket.socket.connect",
            side_effect=RuntimeError("Network is disabled in this audit"),
        ),
    ):
        report = asyncio.run(run_audit(Path(temporary)))
    verify_observations(report)
    report["provenance"] = provenance
    outputs = {
        "results.json": canonical(report).encode(),
        "REPORT.md": markdown(report).encode(),
    }
    checksums = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\n"
        for name, data in sorted(outputs.items())
    )
    outputs["SHA256SUMS"] = checksums.encode()
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    outputs = generate()
    if args.verify:
        for name, data in outputs.items():
            if (args.output / name).read_bytes() != data:
                raise ValueError(f"Stored observation differs: {name}")
    else:
        if args.output.exists() and any(args.output.iterdir()):
            raise ValueError("Output directory is nonempty; use a new path or --verify")
        args.output.mkdir(parents=True, exist_ok=True)
        for name, data in outputs.items():
            (args.output / name).write_bytes(data)
    print("Verified 14 helper fixtures, 3 ambiguity witnesses and 7 grader fixtures.")
    print(
        "The pinned baseline includes 2 response-pairing anomalies "
        "and 5 email-link credit mismatches."
    )
    print(canonical({"runtime_environment": runtime_environment()}).rstrip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
