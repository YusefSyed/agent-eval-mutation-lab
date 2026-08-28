"""Offline replay, oracle join, analysis, and canonical study export."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict
from pathlib import Path

from agent_eval_mutation_lab.model_study.analysis import (
    AnalysisReport,
    AnalyzedTrial,
    analyze_trials,
    render_markdown,
)
from agent_eval_mutation_lab.model_study.artifacts import (
    ContentAddressedReceiptStore,
)
from agent_eval_mutation_lab.model_study.contracts import TerminalStatus
from agent_eval_mutation_lab.model_study.ollama_adapter import build_chat_request
from agent_eval_mutation_lab.model_study.run_plan import (
    FrozenStudyPlan,
    FrozenTrial,
    load_frozen_study,
)
from agent_eval_mutation_lab.model_study.runtime import normalize_response
from agent_eval_mutation_lab.model_study.store import SqliteModelStudyStore
from agent_eval_mutation_lab.models import Prediction

EXPORT_FILES = (
    "plan.json",
    "inputs.jsonl",
    "oracle-ledger.jsonl",
    "prompt-manifest.json",
    "response-schemas.json",
    "model-manifest.json",
    "trials.jsonl",
    "metrics.json",
    "report.md",
)


def export_completed_study(
    *,
    project_root: Path,
    frozen_dir: Path,
    output_dir: Path,
) -> tuple[AnalysisReport, tuple[Path, ...]]:
    """Replay all receipts and export only after all 624 trials finalize."""

    plan = load_frozen_study(project_root=project_root, frozen_dir=frozen_dir)
    trials = build_analyzed_trials(
        plan=plan,
        frozen_dir=frozen_dir,
        output_dir=output_dir,
    )
    report = analyze_trials(trials)
    for filename in (
        "plan.json",
        "inputs.jsonl",
        "oracle-ledger.jsonl",
        "prompt-manifest.json",
        "response-schemas.json",
        "model-manifest.json",
    ):
        shutil.copy2(frozen_dir / filename, output_dir / filename)
    _write_jsonl(
        output_dir / "trials.jsonl",
        [_analyzed_payload(trial) for trial in trials],
    )
    _write_json(output_dir / "metrics.json", report.payload())
    (output_dir / "report.md").write_text(
        render_markdown(report), encoding="utf-8"
    )
    manifest = {
        "schema_version": 1,
        "study_id": plan.study_id,
        "protocol_digest": plan.protocol_digest,
        "trial_count": len(trials),
        "positive_claim_gates_passed": report.gates.passed,
        "files": {
            filename: _file_identity(output_dir / filename)
            for filename in EXPORT_FILES
        },
        "receipt_store": _receipt_store_identity(output_dir / "objects"),
    }
    _write_json(output_dir / "MANIFEST.json", manifest)
    sums = [
        f"{_sha256(output_dir / filename)}  {filename}"
        for filename in (*EXPORT_FILES, "MANIFEST.json")
    ]
    (output_dir / "SHA256SUMS").write_text(
        "\n".join(sums) + "\n", encoding="ascii"
    )
    return report, tuple(output_dir / filename for filename in EXPORT_FILES)


def build_analyzed_trials(
    *,
    plan: FrozenStudyPlan,
    frozen_dir: Path,
    output_dir: Path,
) -> tuple[AnalyzedTrial, ...]:
    """Replay receipts and join the coordinator-only oracle ledger."""

    ledger = SqliteModelStudyStore(output_dir / "run.sqlite3")
    summary = ledger.summary(plan_digest=plan.protocol_digest)
    if summary["pending"] != 0 or sum(
        summary[status.value] for status in TerminalStatus
    ) != len(plan.trials):
        raise RuntimeError("model study is incomplete; canonical export is forbidden")
    terminals = ledger.terminal_trials(plan_digest=plan.protocol_digest)
    if len(terminals) != len(plan.trials):
        raise RuntimeError("terminal ledger does not cover the frozen trial plan")
    oracle = _oracle_ledger(frozen_dir / "oracle-ledger.jsonl")
    by_id = {trial.identity.trial_id: trial for trial in plan.trials}
    receipts = ContentAddressedReceiptStore(output_dir / "objects")
    analyzed = []
    for terminal in terminals:
        identity = terminal.terminal.identity
        trial = by_id.get(identity.trial_id)
        if trial is None:
            raise ValueError("terminal trial is outside the frozen plan")
        terminal_payload = _object(
            json.loads(terminal.terminal_bytes), "terminal bytes"
        )
        _verify_request_receipt(trial, terminal.request_digest, receipts)
        normalized = _replay_response(trial, terminal_payload, receipts)
        family, expected = oracle[trial.input_ref]
        analyzed.append(
            _analyzed_trial(
                trial=trial,
                terminal_status=terminal.terminal.status,
                terminal_payload=terminal_payload,
                normalized=normalized,
                family=family,
                expected=expected,
            )
        )
    return tuple(analyzed)


def _replay_response(
    trial: FrozenTrial,
    terminal: dict[str, object],
    receipts: ContentAddressedReceiptStore,
) -> dict[str, object] | None:
    status = TerminalStatus(_string(terminal, "status"))
    response_digest = terminal.get("response_sha256")
    stored_normalized = terminal.get("normalized")
    if status not in {TerminalStatus.COMPLETE, TerminalStatus.INVALID_RESPONSE}:
        if response_digest is not None or stored_normalized is not None:
            raise ValueError("response-free terminal contains response data")
        return None
    if not isinstance(response_digest, str):
        raise ValueError("response-bearing terminal lacks response digest")
    raw_response = _object(
        json.loads(receipts.load_digest(response_digest)), "Ollama response"
    )
    message = _object(raw_response.get("message"), "Ollama message")
    content = _string(message, "content")
    try:
        replayed = normalize_response(trial, content)
    except (json.JSONDecodeError, ValueError):
        if status is not TerminalStatus.INVALID_RESPONSE:
            raise ValueError("complete terminal no longer replays as valid") from None
        if stored_normalized is not None:
            raise ValueError(
                "invalid terminal unexpectedly stores normalized output"
            ) from None
        return None
    if status is not TerminalStatus.COMPLETE or replayed != stored_normalized:
        raise ValueError("terminal normalization does not match replayed response")
    return replayed


def _verify_request_receipt(
    trial: FrozenTrial,
    request_digest: str | None,
    receipts: ContentAddressedReceiptStore,
) -> None:
    if request_digest is None:
        raise ValueError("terminal trial lacks request digest")
    expected = build_chat_request(
        tag=trial.identity.model.tag,
        system_prompt=trial.prompt,
        model_input=trial.payload,
        response_schema=trial.response_schema,
        config=trial.identity.config,
        seed=trial.identity.seed,
    )
    if receipts.load_digest(request_digest) != expected:
        raise ValueError("stored request bytes differ from frozen trial request")


def _analyzed_trial(
    *,
    trial: FrozenTrial,
    terminal_status: TerminalStatus,
    terminal_payload: dict[str, object],
    normalized: dict[str, object] | None,
    family: str,
    expected: Prediction,
) -> AnalyzedTrial:
    prediction: Prediction = None
    harm: float | None = None
    no_harm: float | None = None
    unknown: float | None = None
    if normalized is not None:
        prediction = _prediction(normalized.get("prediction"))
        structured = _object(
            normalized.get("structured_response"), "structured response"
        )
        probabilities = _object(structured.get("probabilities"), "probabilities")
        harm = _number(probabilities, "harm_established")
        no_harm = _number(probabilities, "no_harm_established")
        unknown = _number(probabilities, "insufficient_evidence")
    if terminal_payload.get("trial_id") != trial.identity.trial_id:
        raise ValueError("terminal trial ID does not match frozen trial")
    return AnalyzedTrial(
        trial_id=trial.identity.trial_id,
        input_ref=trial.input_ref,
        family=family,
        model=trial.identity.model.tag,
        arm=trial.identity.arm,
        seed=trial.identity.seed,
        status=terminal_status,
        prediction=prediction,
        expected=expected,
        probability_harm=harm,
        probability_no_harm=no_harm,
        probability_unknown=unknown,
    )


def _oracle_ledger(path: Path) -> dict[str, tuple[str, Prediction]]:
    result: dict[str, tuple[str, Prediction]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        payload = _object(json.loads(line), "oracle record")
        input_ref = _string(payload, "input_ref")
        value = (_string(payload, "family"), _prediction(payload.get("expected")))
        if input_ref in result and result[input_ref] != value:
            raise ValueError("oracle ledger has conflicting input reference")
        result[input_ref] = value
    if len(result) != 52:
        raise ValueError("oracle ledger must contain exactly 52 inputs")
    return result


def _analyzed_payload(trial: AnalyzedTrial) -> dict[str, object]:
    payload = asdict(trial)
    payload["arm"] = trial.arm.value
    payload["status"] = trial.status.value
    return payload


def _receipt_store_identity(root: Path) -> dict[str, object]:
    files = sorted(root.rglob("*.json"))
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix().encode()
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return {"object_count": len(files), "tree_sha256": digest.hexdigest()}


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _write_jsonl(path: Path, values: list[dict[str, object]]) -> None:
    path.write_bytes(b"".join(_canonical_json(value) for value in values))


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, allow_nan=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode()


def _file_identity(path: Path) -> dict[str, object]:
    return {"sha256": _sha256(path), "size": path.stat().st_size}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _object(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{context} must be an object with string keys")
    return value


def _string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _number(payload: dict[str, object], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")
    return float(value)


def _prediction(value: object) -> Prediction:
    if value is None or type(value) is bool:
        return value
    raise ValueError("prediction must be true, false, or null")
