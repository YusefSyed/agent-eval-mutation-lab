from __future__ import annotations

from pathlib import Path

import pytest

from agent_eval_mutation_lab.model_study.contracts import (
    LicenseEvidence,
    ModelConfig,
    ModelIdentity,
    StudyArm,
    TerminalStatus,
    TrialIdentity,
    build_trial_identity,
)
from agent_eval_mutation_lab.model_study.store import (
    ModelStudyStoreInvariantError,
    SqliteModelStudyStore,
)


def _digest(character: str) -> str:
    return character * 64


def _identity(replicate_index: int) -> TrialIdentity:
    return build_trial_identity(
        study_id="frozen-study",
        arm=StudyArm.DIRECT,
        model=ModelIdentity(
            provider="ollama",
            tag="model:tag",
            blob_digest=_digest("a"),
            parameter_count=1,
            quantization="Q4_K_M",
            license="Apache-2.0",
            license_evidence=LicenseEvidence.LOCAL_MANIFEST,
            license_source="ollama:/api/show",
            runtime_version="0.33.1",
            template_digest=_digest("b"),
        ),
        config=ModelConfig(
            temperature=0.2,
            top_p=0.95,
            presence_penalty=0.0,
            repeat_penalty=1.0,
            context_tokens=8192,
            max_output_tokens=512,
        ),
        input_ref=f"input-{replicate_index:04d}",
        input_digest=_digest("c"),
        prompt_digest=_digest("d"),
        response_schema_digest=_digest("e"),
        seed=101,
        replicate_index=replicate_index,
        adapter_version="1",
    )


def _store(
    tmp_path: Path,
) -> tuple[SqliteModelStudyStore, str, tuple[TrialIdentity, ...]]:
    store = SqliteModelStudyStore(tmp_path / "study.sqlite")
    plan_digest = _digest("f")
    identities = (_identity(0), _identity(1))
    store.register_plan(plan_digest=plan_digest, expected_trials=len(identities))
    store.register_trials(plan_digest=plan_digest, identities=identities)
    return store, plan_digest, identities


def test_resumable_attempts_and_exactly_once_terminal_commit(tmp_path: Path) -> None:
    store, plan_digest, identities = _store(tmp_path)
    first = identities[0]
    assert store.record_attempt(
        plan_digest=plan_digest,
        identity=first,
        attempt_index=0,
        status=TerminalStatus.TRANSPORT_ERROR,
        request_digest=_digest("1"),
        error_type="OllamaTransportError",
    )
    assert store.record_attempt(
        plan_digest=plan_digest,
        identity=first,
        attempt_index=1,
        status=TerminalStatus.INTERRUPTED,
        request_digest=_digest("2"),
    )
    assert store.pending_trials(plan_digest=plan_digest) == identities
    receipt = b'{"status":"complete"}\n'
    assert store.finalize_terminal(
        plan_digest=plan_digest,
        identity=first,
        attempt_index=2,
        status=TerminalStatus.COMPLETE,
        request_digest=_digest("3"),
        response_digest=_digest("4"),
        prompt_tokens=32,
        completion_tokens=8,
        duration_ns=123,
        terminal_bytes=receipt,
    )
    assert not store.finalize_terminal(
        plan_digest=plan_digest,
        identity=first,
        attempt_index=2,
        status=TerminalStatus.COMPLETE,
        request_digest=_digest("3"),
        response_digest=_digest("4"),
        prompt_tokens=32,
        completion_tokens=8,
        duration_ns=123,
        terminal_bytes=receipt,
    )
    assert store.pending_trials(plan_digest=plan_digest) == (identities[1],)
    terminal = store.terminal_trials(plan_digest=plan_digest)
    assert terminal[0].terminal.status is TerminalStatus.COMPLETE
    assert terminal[0].terminal_bytes == receipt
    assert [attempt.status for attempt in store.attempts_for(
        plan_digest=plan_digest, trial_id=first.trial_id
    )] == [
        TerminalStatus.TRANSPORT_ERROR,
        TerminalStatus.INTERRUPTED,
        TerminalStatus.COMPLETE,
    ]
    assert store.summary(plan_digest=plan_digest) == {
        "expected_trials": 2,
        "attempts": 3,
        "pending": 1,
        "complete": 1,
        "invalid_response": 0,
        "transport_error": 0,
        "timed_out": 0,
        "interrupted": 0,
    }
    store.integrity_check(plan_digest=plan_digest)


def test_registration_identity_order_and_terminal_receipt_conflicts_fail_closed(
    tmp_path: Path,
) -> None:
    store, plan_digest, identities = _store(tmp_path)
    with pytest.raises(ModelStudyStoreInvariantError, match="identity/order"):
        store.register_trials(plan_digest=plan_digest, identities=identities[::-1])

    first = identities[0]
    store.finalize_terminal(
        plan_digest=plan_digest,
        identity=first,
        attempt_index=0,
        status=TerminalStatus.INVALID_RESPONSE,
        request_digest=_digest("1"),
        response_digest=_digest("2"),
        terminal_bytes=b"invalid-receipt",
    )
    with pytest.raises(ModelStudyStoreInvariantError, match="final state"):
        store.finalize_terminal(
            plan_digest=plan_digest,
            identity=first,
            attempt_index=0,
            status=TerminalStatus.INVALID_RESPONSE,
            request_digest=_digest("1"),
            response_digest=_digest("2"),
            terminal_bytes=b"different-receipt",
        )


def test_attempt_conflict_rolls_back_without_partial_finalization(
    tmp_path: Path,
) -> None:
    store, plan_digest, identities = _store(tmp_path)
    first = identities[0]
    store.record_attempt(
        plan_digest=plan_digest,
        identity=first,
        attempt_index=0,
        status=TerminalStatus.TRANSPORT_ERROR,
        request_digest=_digest("1"),
        error_type="OllamaTransportError",
    )
    with pytest.raises(ModelStudyStoreInvariantError, match="conflicting bytes"):
        store.finalize_terminal(
            plan_digest=plan_digest,
            identity=first,
            attempt_index=0,
            status=TerminalStatus.COMPLETE,
            request_digest=_digest("2"),
            response_digest=_digest("3"),
            terminal_bytes=b"must-not-commit",
        )
    assert store.pending_trials(plan_digest=plan_digest) == identities
    attempts = store.attempts_for(plan_digest=plan_digest, trial_id=first.trial_id)
    assert len(attempts) == 1
    assert attempts[0].status is TerminalStatus.TRANSPORT_ERROR
    assert store.terminal_trials(plan_digest=plan_digest) == ()
