"""Command-line entry point."""

from __future__ import annotations

import argparse
from pathlib import Path

from agent_eval_mutation_lab.benchmark import run_benchmark
from agent_eval_mutation_lab.report import write_reports


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the offline execution-semantic scorer benchmark."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/latest"),
        help="Directory for deterministic JSON and Markdown results.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    json_path, markdown_path = write_reports(run_benchmark(), args.output)
    print(f"Wrote {json_path}")
    print(f"Wrote {markdown_path}")


if __name__ == "__main__":
    main()

