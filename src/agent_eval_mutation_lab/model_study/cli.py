"""CLI for local model-study preflight and format-only pilots."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from agent_eval_mutation_lab.model_study.contracts import ModelConfig
from agent_eval_mutation_lab.model_study.freeze import (
    freeze_protocol,
    load_model_identity,
)
from agent_eval_mutation_lab.model_study.ollama_adapter import (
    OllamaClient,
    model_identity_from_show,
)
from agent_eval_mutation_lab.model_study.pilot import run_format_pilot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preflight local models or run a non-benchmark format pilot."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("preflight", "pilot"):
        command = subparsers.add_parser(name)
        command.add_argument("--tag", required=True)
        command.add_argument("--output", type=Path, required=True)
        command.add_argument("--base-url", default="http://127.0.0.1:11434")
        command.add_argument("--declared-license", choices=["Apache-2.0"])
        command.add_argument("--license-source")
    pilot = subparsers.choices["pilot"]
    pilot.add_argument("--root", type=Path, default=Path.cwd())
    pilot.add_argument("--seed", type=int, default=101)
    pilot.add_argument("--timeout-seconds", type=float, default=180.0)
    freeze = subparsers.add_parser("freeze")
    freeze.add_argument("--root", type=Path, default=Path.cwd())
    freeze.add_argument("--output", type=Path, required=True)
    freeze.add_argument(
        "--model-identity",
        type=Path,
        action="append",
        required=True,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "freeze":
        plan = freeze_protocol(
            project_root=args.root.resolve(),
            output_dir=args.output.resolve(),
            models=tuple(load_model_identity(path) for path in args.model_identity),
        )
        print(args.output.resolve() / "plan.json")
        if plan["planned_terminal_trials"] != 624:
            raise SystemExit(1)
        return
    client = OllamaClient(base_url=args.base_url)
    identity = model_identity_from_show(
        tag=args.tag,
        show_payload=client.show(args.tag),
        runtime_version=client.version(),
        declared_license=args.declared_license,
        license_source=args.license_source,
    )
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if args.command == "preflight":
        path = output / "model-identity.json"
        path.write_text(
            json.dumps(asdict(identity), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(path)
        return
    config = ModelConfig(
        temperature=0.2,
        top_p=0.95,
        presence_penalty=0.0,
        repeat_penalty=1.0,
        context_tokens=8192,
        max_output_tokens=512,
    )
    report = run_format_pilot(
        project_root=args.root.resolve(),
        output_dir=output,
        client=client,
        identity=identity,
        config=config,
        seed=args.seed,
        timeout_seconds=args.timeout_seconds,
    )
    print(output / "pilot-summary.json")
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
