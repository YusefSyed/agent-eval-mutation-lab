"""CLI for the isolated v2 semantic mutation benchmark."""

from __future__ import annotations

import argparse
from pathlib import Path

from agent_eval_mutation_lab.mutation_benchmark.benchmark import (
    run_benchmark,
    write_reports,
)
from agent_eval_mutation_lab.mutation_benchmark.catalog import load_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the predeclared v2 scorer semantic mutation benchmark."
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("benchmarks/mutations-v2-development.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/mutation-benchmark"),
    )
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    manifest_path = args.manifest
    if not manifest_path.is_absolute():
        manifest_path = root / manifest_path
    output_path = args.output
    if not output_path.is_absolute():
        output_path = root / output_path
    manifest = load_manifest(manifest_path)
    report = run_benchmark(
        root,
        manifest,
        timeout_seconds=args.timeout_seconds,
    )
    json_path, markdown_path = write_reports(report, output_path)
    print(json_path)
    print(markdown_path)


if __name__ == "__main__":
    main()
