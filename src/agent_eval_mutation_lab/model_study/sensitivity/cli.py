"""Explicit-estimand CLI; writes only a new diagnostic directory."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict, replace
from pathlib import Path

from agent_eval_mutation_lab.reproduction import CORE_ARTIFACTS

from .bounds import Comparison, Estimand, Interval, audit_comparison, exact_json
from .io import as_object, comparison_from_payload, read_json
from .study import load_frozen_diagnostic, model_comparison, sha256


def _json(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def _interval(value: Interval | None) -> str:
    if value is None:
        return "undefined"
    if value.lower == value.upper:
        return str(value.lower)
    return f"[{value.lower}, {value.upper}]"


def write_diagnostic(
    *,
    output: Path,
    project_root: Path,
    provenance: dict[str, object],
    comparisons: Sequence[tuple[str, str, Comparison]],
    estimands: Sequence[Estimand],
) -> None:
    """Publish deterministic contracts/certificates without overwriting evidence."""

    destination = output.resolve()
    protected = (
        project_root / "src",
        project_root / "benchmarks",
        project_root / "artifacts/model-study",
        *(project_root / path.parent for path in CORE_ARTIFACTS),
    )
    if (
        output.exists()
        or output.is_symlink()
        or any(destination.is_relative_to(path.resolve()) for path in protected)
    ):
        raise ValueError("output must be a new directory outside frozen/core artifacts")
    if not estimands or len(set(estimands)) != len(estimands):
        raise ValueError("choose at least one unique explicit estimand")
    if not comparisons or len({item[:2] for item in comparisons}) != len(comparisons):
        raise ValueError("comparison labels and weighting pairs must be unique")
    contracts = []
    results = []
    lines = [
        "# Post-hoc missing-output sensitivity diagnostic",
        "",
        "**Diagnostic only. These finite completion bounds do not repair the "
        "frozen study, provide confidence intervals, or establish causal effects.**",
        "",
        "Frozen output-validity gate passed: "
        f"**{provenance.get('output_validity_gate_passed', 'not applicable')}**.",
        "A bound excluding zero cannot override that verdict.",
        "",
        "Contrast is left arm minus right arm; all numbers below are exact rationals.",
        "Every group weight and denominator is explicit in `contracts.json`.",
        "Valid-only results condition on observed valid outputs and can be selected.",
        "",
        "| Comparison | Contrast | Weighting | Estimand | Left | Right | Difference |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for label, weighting, comparison in sorted(comparisons, key=lambda item: item[:2]):
        comparison = replace(
            comparison,
            groups=tuple(
                replace(
                    group,
                    left_trial_ids=tuple(sorted(group.left_trial_ids)),
                    right_trial_ids=tuple(sorted(group.right_trial_ids)),
                )
                for group in sorted(comparison.groups, key=lambda group: group.group)
            ),
            outcomes=tuple(sorted(comparison.outcomes, key=lambda row: row.trial_id)),
        )
        contract = {"schema_version": 1, **as_object(exact_json(asdict(comparison)))}
        contract_digest = hashlib.sha256(_json(contract).encode()).hexdigest()
        contracts.append(
            {
                "label": label,
                "weighting": weighting,
                "sha256": contract_digest,
                "contract": contract,
            }
        )
        for estimand in sorted(estimands):
            report = audit_comparison(comparison, estimand)
            results.append(
                {
                    "label": label,
                    "weighting": weighting,
                    "contract_sha256": contract_digest,
                    "report": report.payload(),
                }
            )
            lines.append(
                f"| {label} | {comparison.left_arm} - {comparison.right_arm} "
                f"| {weighting} | {estimand.value} | {_interval(report.left_mean)} "
                f"| {_interval(report.right_mean)} | {_interval(report.difference)} |"
            )
    lines.extend(
        [
            "",
            "The JSON preserves weights, observed/planned denominators, "
            "missing reasons, and exact endpoint assignments.",
            "These are sharp interval hulls of binary completions; "
            "interior values need not all be attainable.",
            "An undefined valid-only group is never discarded or renormalized.",
            "",
            "Method attribution: standard bounded-outcome/partial-identification "
            "reasoning; see `research/missing-output-sensitivity.md`.",
        ]
    )
    contents = {
        "contracts.json": _json({"schema_version": 1, "comparisons": contracts}),
        "diagnostic.json": _json(
            {"schema_version": 1, "provenance": provenance, "comparisons": results}
        ),
        "diagnostic.md": "\n".join(lines) + "\n",
    }
    contents["SHA256SUMS"] = "".join(
        f"{hashlib.sha256(content.encode()).hexdigest()}  {name}\n"
        for name, content in sorted(contents.items())
    )
    destination.mkdir(parents=True)
    for name, content in contents.items():
        (destination / name).write_text(content, encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--input", type=Path, help="Explicit finite binary comparison JSON."
    )
    source.add_argument("--frozen-study", type=Path, help="Read-only repository root.")
    parser.add_argument(
        "--estimand", choices=[*(e.value for e in Estimand), "all"], required=True
    )
    parser.add_argument("--weighting", choices=["pooled", "equal_family", "both"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if (args.frozen_study is None) != (args.weighting is None):
        parser.error("--weighting is required only with --frozen-study")
    estimands = (
        tuple(Estimand) if args.estimand == "all" else (Estimand(args.estimand),)
    )
    try:
        if args.frozen_study is not None:
            root = args.frozen_study.resolve()
            study = load_frozen_diagnostic(root)
            weightings = (
                ("pooled", "equal_family")
                if args.weighting == "both"
                else (args.weighting,)
            )
            comparisons = [
                (model, weighting, model_comparison(study, model, weighting))
                for model in sorted({t.model for t in study.trials})
                for weighting in weightings
            ]
            provenance = study.provenance
        else:
            root = Path.cwd()
            comparisons = [
                (
                    "declared_comparison",
                    "declared_group_weights",
                    comparison_from_payload(read_json(args.input)),
                )
            ]
            provenance = {
                "scope": "explicit_finite_binary_contract",
                "input_sha256": sha256(args.input),
            }
        write_diagnostic(
            output=args.output,
            project_root=root,
            provenance=provenance,
            comparisons=comparisons,
            estimands=estimands,
        )
    except (ValueError, OSError, KeyError) as error:
        parser.exit(2, f"Sensitivity diagnostic refused: {error}\n")
    print(f"Wrote post-hoc diagnostic: {args.output}")


if __name__ == "__main__":
    main()
