"""Resumable serial execution of the checksum-frozen local-model study."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_eval_mutation_lab.model_study.artifacts import (
    ContentAddressedReceiptStore,
)
from agent_eval_mutation_lab.model_study.contracts import (
    LicenseEvidence,
    StudyArm,
    TerminalStatus,
)
from agent_eval_mutation_lab.model_study.ollama_adapter import (
    OllamaClient,
    OllamaTimeoutError,
    OllamaTransportError,
    build_chat_request,
    model_identity_from_show,
)
from agent_eval_mutation_lab.model_study.run_plan import (
    FrozenStudyPlan,
    FrozenTrial,
    load_frozen_study,
)
from agent_eval_mutation_lab.model_study.schemas import (
    parse_direct_response,
    parse_evidence_first_response,
)
from agent_eval_mutation_lab.model_study.store import SqliteModelStudyStore
from agent_eval_mutation_lab.model_study.validation import validate_evidence_ledger


def run_frozen_study(
    *,
    project_root: Path,
    frozen_dir: Path,
    output_dir: Path,
    client: OllamaClient,
    timeout_seconds: float,
    max_new_trials: int | None = None,
) -> dict[str, Any]:
    """Execute pending trials in frozen order with exactly one transport retry."""

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if max_new_trials is not None and max_new_trials < 0:
        raise ValueError("max_new_trials must be non-negative")
    plan = load_frozen_study(project_root=project_root, frozen_dir=frozen_dir)
    _verify_local_models(plan, client)
    output_dir.mkdir(parents=True, exist_ok=True)
    ledger = SqliteModelStudyStore(output_dir / "run.sqlite3")
    receipts = ContentAddressedReceiptStore(output_dir / "objects")
    ledger.register_plan(
        plan_digest=plan.protocol_digest,
        expected_trials=len(plan.trials),
    )
    ledger.register_trials(
        plan_digest=plan.protocol_digest,
        identities=tuple(trial.identity for trial in plan.trials),
    )
    by_id = {trial.identity.trial_id: trial for trial in plan.trials}
    pending = ledger.pending_trials(plan_digest=plan.protocol_digest)
    selected = (
        pending if max_new_trials is None else pending[:max_new_trials]
    )
    executed = 0
    interrupted = False
    for identity in selected:
        trial = by_id[identity.trial_id]
        try:
            _run_one(
                plan=plan,
                trial=trial,
                client=client,
                ledger=ledger,
                receipts=receipts,
                timeout_seconds=timeout_seconds,
            )
        except KeyboardInterrupt:
            interrupted = True
            break
        executed += 1
    ledger.integrity_check(plan_digest=plan.protocol_digest)
    summary = ledger.summary(plan_digest=plan.protocol_digest)
    return {
        "schema_version": 1,
        "study_id": plan.study_id,
        "protocol_digest": plan.protocol_digest,
        "executed_this_run": executed,
        "resumed_before_run": len(plan.trials) - len(pending),
        "interrupted": interrupted,
        **summary,
    }


def _run_one(
    *,
    plan: FrozenStudyPlan,
    trial: FrozenTrial,
    client: OllamaClient,
    ledger: SqliteModelStudyStore,
    receipts: ContentAddressedReceiptStore,
    timeout_seconds: float,
) -> None:
    identity = trial.identity
    request_bytes = build_chat_request(
        tag=identity.model.tag,
        system_prompt=trial.prompt,
        model_input=trial.payload,
        response_schema=trial.response_schema,
        config=identity.config,
        seed=identity.seed,
    )
    request_artifact = receipts.put(request_bytes)
    while True:
        attempts = ledger.attempts_for(
            plan_digest=plan.protocol_digest,
            trial_id=identity.trial_id,
        )
        attempt_index = len(attempts)
        transport_failures = sum(
            attempt.status is TerminalStatus.TRANSPORT_ERROR for attempt in attempts
        )
        try:
            receipt = client.send_chat_request(
                request_bytes=request_bytes,
                timeout_seconds=timeout_seconds,
            )
        except KeyboardInterrupt:
            ledger.record_attempt(
                plan_digest=plan.protocol_digest,
                identity=identity,
                attempt_index=attempt_index,
                status=TerminalStatus.INTERRUPTED,
                request_digest=request_artifact.digest,
            )
            raise
        except OllamaTimeoutError as error:
            _finalize_error(
                plan=plan,
                trial=trial,
                ledger=ledger,
                attempt_index=attempt_index,
                status=TerminalStatus.TIMED_OUT,
                request_digest=request_artifact.digest,
                error=error,
            )
            return
        except OllamaTransportError as error:
            if transport_failures == 0:
                ledger.record_attempt(
                    plan_digest=plan.protocol_digest,
                    identity=identity,
                    attempt_index=attempt_index,
                    status=TerminalStatus.TRANSPORT_ERROR,
                    request_digest=request_artifact.digest,
                    error_type=type(error).__name__,
                )
                continue
            _finalize_error(
                plan=plan,
                trial=trial,
                ledger=ledger,
                attempt_index=attempt_index,
                status=TerminalStatus.TRANSPORT_ERROR,
                request_digest=request_artifact.digest,
                error=error,
            )
            return
        response_artifact = receipts.put(receipt.response_bytes)
        status = TerminalStatus.COMPLETE
        error_type: str | None = None
        normalized: dict[str, object] | None = None
        try:
            normalized = _normalize_response(trial, receipt.response_content)
        except (json.JSONDecodeError, ValueError) as error:
            status = TerminalStatus.INVALID_RESPONSE
            error_type = type(error).__name__
        terminal = _terminal_bytes(
            trial=trial,
            status=status,
            request_digest=request_artifact.digest,
            response_digest=response_artifact.digest,
            error_type=error_type,
            normalized=normalized,
        )
        ledger.finalize_terminal(
            plan_digest=plan.protocol_digest,
            identity=identity,
            attempt_index=attempt_index,
            status=status,
            request_digest=request_artifact.digest,
            response_digest=response_artifact.digest,
            error_type=error_type,
            prompt_tokens=receipt.prompt_tokens,
            completion_tokens=receipt.completion_tokens,
            duration_ns=receipt.total_duration_ns,
            terminal_bytes=terminal,
        )
        return


def _normalize_response(
    trial: FrozenTrial,
    content: str,
) -> dict[str, object]:
    payload = json.loads(content)
    if trial.identity.arm is StudyArm.DIRECT:
        parsed = parse_direct_response(payload)
        return {
            "prediction": parsed.prediction,
            "structured_response": payload,
        }
    parsed_evidence = parse_evidence_first_response(payload)
    validate_evidence_ledger(parsed_evidence, trial.payload)
    return {
        "prediction": parsed_evidence.prediction,
        "structured_response": payload,
    }


def _finalize_error(
    *,
    plan: FrozenStudyPlan,
    trial: FrozenTrial,
    ledger: SqliteModelStudyStore,
    attempt_index: int,
    status: TerminalStatus,
    request_digest: str,
    error: Exception,
) -> None:
    error_type = type(error).__name__
    terminal = _terminal_bytes(
        trial=trial,
        status=status,
        request_digest=request_digest,
        response_digest=None,
        error_type=error_type,
        normalized=None,
    )
    ledger.finalize_terminal(
        plan_digest=plan.protocol_digest,
        identity=trial.identity,
        attempt_index=attempt_index,
        status=status,
        request_digest=request_digest,
        error_type=error_type,
        terminal_bytes=terminal,
    )


def _terminal_bytes(
    *,
    trial: FrozenTrial,
    status: TerminalStatus,
    request_digest: str,
    response_digest: str | None,
    error_type: str | None,
    normalized: dict[str, object] | None,
) -> bytes:
    payload = {
        "schema_version": 1,
        "trial_id": trial.identity.trial_id,
        "input_ref": trial.input_ref,
        "arm": trial.identity.arm.value,
        "model_blob_digest": trial.identity.model.blob_digest,
        "seed": trial.identity.seed,
        "replicate_index": trial.identity.replicate_index,
        "status": status.value,
        "request_sha256": request_digest,
        "response_sha256": response_digest,
        "error_type": error_type,
        "normalized": normalized,
    }
    return _canonical_json(payload)


def _verify_local_models(plan: FrozenStudyPlan, client: OllamaClient) -> None:
    runtime_version = client.version()
    for expected in plan.models:
        upstream = expected.license_evidence is LicenseEvidence.UPSTREAM_MODEL_CARD
        actual = model_identity_from_show(
            tag=expected.tag,
            show_payload=client.show(expected.tag),
            runtime_version=runtime_version,
            declared_license=expected.license if upstream else None,
            license_source=expected.license_source if upstream else None,
        )
        if actual != expected:
            raise ValueError(f"local model identity drift: {expected.tag}")


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, allow_nan=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode()
