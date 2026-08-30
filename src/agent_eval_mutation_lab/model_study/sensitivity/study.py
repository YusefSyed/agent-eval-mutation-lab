"""Read-only frozen-artifact verification and post-hoc binary outcome adapter."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, fields
from fractions import Fraction
from pathlib import Path

from agent_eval_mutation_lab.model_study.analysis import AnalyzedTrial, analyze_trials
from agent_eval_mutation_lab.model_study.artifacts import ContentAddressedReceiptStore
from agent_eval_mutation_lab.model_study.contracts import StudyArm, TerminalStatus
from agent_eval_mutation_lab.model_study.export import EXPORT_FILES
from agent_eval_mutation_lab.model_study.freeze import FROZEN_FILES
from agent_eval_mutation_lab.model_study.run_plan import (
    FrozenStudyPlan,
    load_frozen_study,
)
from agent_eval_mutation_lab.models import Prediction

from .bounds import Comparison, GroupPlan, Outcome
from .io import as_integer, as_object, as_string, exact_keys, read_json, read_jsonl

VALIDITY_CHECKS = (
    "validity_at_least_95_percent_each_model_arm",
    "validity_gap_at_most_5pp_each_model",
)


@dataclass(frozen=True, slots=True)
class FrozenDiagnostic:
    trials: tuple[AnalyzedTrial, ...]
    families: tuple[str, ...]
    provenance: dict[str, object]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_manifest(root: Path, expected_files: tuple[str, ...]) -> dict[str, object]:
    """Require complete checksum and size manifests, not merely listed-file checks."""

    expected = set(expected_files)
    if len(expected) != len(expected_files):
        raise ValueError("expected artifact names must be unique")
    sums: dict[str, str] = {}
    for line in (root / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        parts = line.split("  ", maxsplit=1)
        if len(parts) != 2 or parts[1] in sums:
            raise ValueError("invalid or duplicate SHA256SUMS entry")
        digest, name = parts
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("checksum must be a lowercase SHA-256 digest")
        sums[name] = digest
    if set(sums) != expected | {"MANIFEST.json"}:
        raise ValueError("checksum manifest does not cover the exact artifact set")
    for name, digest in sums.items():
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("artifact path escapes the declared artifact boundary")
        if not path.is_file() or sha256(path) != digest:
            raise ValueError(f"artifact checksum mismatch: {name}")
    manifest = as_object(read_json(root / "MANIFEST.json"))
    if as_integer(manifest.get("schema_version")) != 1:
        raise ValueError("unsupported artifact manifest schema")
    entries = as_object(manifest.get("files"))
    if set(entries) != expected:
        raise ValueError("file manifest does not cover the exact artifact set")
    for name, raw_identity in entries.items():
        identity = as_object(raw_identity)
        exact_keys(identity, {"sha256", "size"})
        if (
            identity["sha256"] != sums[name]
            or as_integer(identity["size"]) != (root / name).stat().st_size
        ):
            raise ValueError("file identity disagrees with checksum or size")
    return manifest


def _verify_receipts(root: Path, identity: dict[str, object]) -> None:
    exact_keys(identity, {"object_count", "tree_sha256"})
    receipts = ContentAddressedReceiptStore(root)
    digest = hashlib.sha256()
    paths = sorted(root.rglob("*.json"))
    for path in paths:
        key = path.stem
        relative = path.relative_to(root)
        if relative != Path("sha256") / key[:2] / f"{key}.json" or path.is_symlink():
            raise ValueError("receipt path is not its declared content address")
        content = receipts.load_digest(key)
        encoded = relative.as_posix().encode()
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    if (
        as_integer(identity["object_count"]) != len(paths)
        or identity["tree_sha256"] != digest.hexdigest()
    ):
        raise ValueError("receipt-store manifest mismatch")


def _prediction(value: object) -> Prediction:
    if value is None or type(value) is bool:
        return value
    raise ValueError("semantic prediction must be true, false, or null")


def _probability(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError("probability must be a finite number or null")
    if not math.isfinite(value):
        raise ValueError("probability must be finite")
    return float(value)


def join_trials(
    plan: FrozenStudyPlan,
    rows: tuple[dict[str, object], ...],
    oracle_rows: tuple[dict[str, object], ...],
) -> tuple[AnalyzedTrial, ...]:
    """Rejoin frozen oracle labels and validate every planned terminal identity."""

    oracle: dict[str, tuple[str, Prediction]] = {}
    for row in oracle_rows:
        reference = as_string(row.get("input_ref"))
        if reference in oracle:
            raise ValueError("duplicate oracle input reference")
        oracle[reference] = (
            as_string(row.get("family")),
            _prediction(row.get("expected")),
        )
    if set(oracle) != {trial.input_ref for trial in plan.trials}:
        raise ValueError("oracle does not cover the complete planned input set")
    planned = {trial.identity.trial_id: trial for trial in plan.trials}
    if len(planned) != len(plan.trials):
        raise ValueError("duplicate trial ID in frozen plan")
    joined: dict[str, AnalyzedTrial] = {}
    expected_fields = {field.name for field in fields(AnalyzedTrial)}
    for row in rows:
        exact_keys(row, expected_fields)
        trial_id = as_string(row["trial_id"])
        if trial_id in joined:
            raise ValueError("duplicate canonical trial ID")
        if trial_id not in planned:
            raise ValueError("canonical trial is outside the frozen plan")
        trial = planned[trial_id]
        family, expected = oracle[trial.input_ref]
        identity = trial.identity
        if (
            row["input_ref"] != trial.input_ref
            or row["model"] != identity.model.tag
            or row["arm"] != identity.arm.value
            or as_integer(row["seed"]) != identity.seed
            or row["family"] != family
            or _prediction(row["expected"]) is not expected
        ):
            raise ValueError("canonical trial disagrees with frozen identity or oracle")
        joined[trial_id] = AnalyzedTrial(
            trial_id=trial_id,
            input_ref=trial.input_ref,
            family=family,
            model=identity.model.tag,
            arm=identity.arm,
            seed=identity.seed,
            status=TerminalStatus(as_string(row["status"])),
            prediction=_prediction(row["prediction"]),
            expected=expected,
            probability_harm=_probability(row["probability_harm"]),
            probability_no_harm=_probability(row["probability_no_harm"]),
            probability_unknown=_probability(row["probability_unknown"]),
        )
    if set(joined) != set(planned):
        raise ValueError("canonical terminals do not cover every planned trial")
    return tuple(joined[trial.identity.trial_id] for trial in plan.trials)


def load_frozen_diagnostic(project_root: Path) -> FrozenDiagnostic:
    """Verify existing evidence without opening SQLite or invoking inference/export."""

    frozen = project_root / "benchmarks/model-study-v1/frozen"
    canonical = project_root / "artifacts/model-study/v1"
    frozen_manifest = verify_manifest(frozen, FROZEN_FILES)
    manifest = verify_manifest(canonical, EXPORT_FILES)
    for filename in FROZEN_FILES:
        if (frozen / filename).read_bytes() != (canonical / filename).read_bytes():
            raise ValueError("canonical protocol copy differs from frozen source")
    plan = load_frozen_study(project_root=project_root, frozen_dir=frozen)
    if (
        manifest.get("protocol_digest") != plan.protocol_digest
        or manifest.get("study_id") != plan.study_id
        or frozen_manifest.get("study_id") != plan.study_id
        or as_integer(manifest.get("trial_count")) != len(plan.trials)
    ):
        raise ValueError("canonical manifest disagrees with the frozen plan")
    _verify_receipts(canonical / "objects", as_object(manifest.get("receipt_store")))
    trials = join_trials(
        plan,
        read_jsonl(canonical / "trials.jsonl"),
        read_jsonl(frozen / "oracle-ledger.jsonl"),
    )
    recomputed = analyze_trials(trials)
    if json.dumps(
        read_json(canonical / "metrics.json"), sort_keys=True, allow_nan=False
    ) != json.dumps(recomputed.payload(), sort_keys=True, allow_nan=False):
        raise ValueError("frozen metrics disagree with public offline analysis")
    if manifest.get("positive_claim_gates_passed") is not recomputed.gates.passed:
        raise ValueError("manifest gate verdict disagrees with frozen analysis")
    validity = {name: recomputed.gates.checks[name] for name in VALIDITY_CHECKS}
    provenance: dict[str, object] = {
        "scope": "post_hoc_diagnostic_only_not_preregistered_inference",
        "study_id": plan.study_id,
        "protocol_digest": plan.protocol_digest,
        "frozen_checksums_sha256": sha256(frozen / "SHA256SUMS"),
        "canonical_checksums_sha256": sha256(canonical / "SHA256SUMS"),
        "canonical_manifest_sha256": sha256(canonical / "MANIFEST.json"),
        "planned_terminal_count": len(plan.trials),
        "valid_count": sum(trial.valid for trial in trials),
        "invalid_count": sum(not trial.valid for trial in trials),
        "output_validity_checks": validity,
        "output_validity_gate_passed": all(validity.values()),
        "positive_claim_gates_passed": recomputed.gates.passed,
        "claim_boundary": (
            "No sensitivity bound overrides the frozen validity verdict "
            "or establishes an intervention benefit."
        ),
        "integrity_boundary": (
            "Local checksum/manifest consistency, not an authenticity signature "
            "or receipt re-scoring."
        ),
    }
    return FrozenDiagnostic(
        trials, tuple(sorted({t.family for t in trials})), provenance
    )


def outcome_from_trial(trial: AnalyzedTrial, group: str) -> Outcome:
    # COMPLETE + prediction=None is a valid semantic 'unknown', not missing.
    return Outcome(
        trial.trial_id,
        trial.arm.value,
        group,
        int(trial.prediction == trial.expected) if trial.valid else None,
        None if trial.valid else trial.status.value,
    )


def model_comparison(study: FrozenDiagnostic, model: str, weighting: str) -> Comparison:
    if weighting not in {"pooled", "equal_family"}:
        raise ValueError("explicit pooled or equal_family weighting is required")
    records = tuple(trial for trial in study.trials if trial.model == model)
    if not records:
        raise ValueError("model is absent from the frozen study")
    groups = study.families if weighting == "equal_family" else ("all_trials",)
    outcomes = tuple(
        outcome_from_trial(t, t.family if weighting == "equal_family" else "all_trials")
        for t in records
    )
    left, right = StudyArm.EVIDENCE_FIRST.value, StudyArm.DIRECT.value
    plans = []
    for group in groups:
        left_ids = tuple(
            sorted(o.trial_id for o in outcomes if o.group == group and o.arm == left)
        )
        right_ids = tuple(
            sorted(o.trial_id for o in outcomes if o.group == group and o.arm == right)
        )
        plans.append(
            GroupPlan(
                group,
                Fraction(1, len(groups)),
                len(left_ids),
                len(right_ids),
                left_ids,
                right_ids,
            )
        )
    return Comparison(left, right, tuple(plans), outcomes)
