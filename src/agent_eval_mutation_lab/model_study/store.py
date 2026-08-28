"""Transactional SQLite ledger for resumable frozen model-study trials.

The ledger stores only hashes and operational metadata.  Trial semantic identity
comes exclusively from :class:`TrialIdentity`; requests and responses remain in
the caller-owned artifact boundary.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path, PureWindowsPath
from typing import cast

from agent_eval_mutation_lab.model_study.contracts import (
    LicenseEvidence,
    ModelConfig,
    ModelIdentity,
    StudyArm,
    TerminalStatus,
    TrialIdentity,
    TrialTerminal,
)

SCHEMA_VERSION = 1


class ModelStudyStoreInvariantError(RuntimeError):
    """The stored ledger no longer matches its frozen study plan."""


@dataclass(frozen=True, slots=True, kw_only=True)
class AttemptRecord:
    """One recorded transport attempt, whether or not it finalized a trial."""

    identity: TrialIdentity
    attempt_index: int
    status: TerminalStatus
    request_digest: str | None
    response_digest: str | None
    error_type: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    duration_ns: int | None
    finalizes_trial: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class TerminalRecord:
    """The immutable final result and receipt bytes for one trial."""

    terminal: TrialTerminal
    attempt_index: int
    request_digest: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    duration_ns: int | None
    terminal_bytes: bytes


class SqliteModelStudyStore:
    """Single-plan, append-only attempt ledger with exactly-once finalization."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _create_schema(self, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS plans (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                plan_digest TEXT NOT NULL UNIQUE,
                expected_trials INTEGER NOT NULL CHECK (expected_trials >= 0)
            );
            CREATE TABLE IF NOT EXISTS trials (
                plan_digest TEXT NOT NULL REFERENCES plans(plan_digest),
                trial_id TEXT NOT NULL,
                ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
                identity_json BLOB NOT NULL,
                terminal_status TEXT,
                terminal_attempt_index INTEGER,
                terminal_bytes BLOB,
                PRIMARY KEY (plan_digest, trial_id),
                UNIQUE (plan_digest, ordinal),
                CHECK (
                    (terminal_status IS NULL
                     AND terminal_attempt_index IS NULL
                     AND terminal_bytes IS NULL)
                    OR
                    (terminal_status IS NOT NULL
                     AND terminal_attempt_index IS NOT NULL
                     AND terminal_bytes IS NOT NULL)
                )
            );
            CREATE TABLE IF NOT EXISTS attempts (
                plan_digest TEXT NOT NULL,
                trial_id TEXT NOT NULL,
                attempt_index INTEGER NOT NULL CHECK (attempt_index >= 0),
                status TEXT NOT NULL,
                request_digest TEXT,
                response_digest TEXT,
                error_type TEXT,
                prompt_tokens INTEGER CHECK (
                    prompt_tokens IS NULL OR prompt_tokens >= 0
                ),
                completion_tokens INTEGER CHECK (
                    completion_tokens IS NULL OR completion_tokens >= 0
                ),
                duration_ns INTEGER CHECK (duration_ns IS NULL OR duration_ns >= 0),
                finalizes_trial INTEGER NOT NULL CHECK (finalizes_trial IN (0, 1)),
                PRIMARY KEY (plan_digest, trial_id, attempt_index),
                FOREIGN KEY (plan_digest, trial_id)
                    REFERENCES trials(plan_digest, trial_id)
            );
            """
        )
        existing = connection.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone()
        if existing is None:
            connection.execute(
                "INSERT INTO metadata(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
        elif existing["value"] != str(SCHEMA_VERSION):
            raise ModelStudyStoreInvariantError("unsupported model-study schema")

    def register_plan(self, *, plan_digest: str, expected_trials: int) -> None:
        """Register the one frozen plan that this database is allowed to hold."""

        _digest(plan_digest, "plan_digest")
        if expected_trials < 0:
            raise ValueError("expected_trials must be non-negative")
        with self._connect() as connection:
            self._create_schema(connection)
            row = connection.execute(
                "SELECT plan_digest, expected_trials FROM plans WHERE singleton = 1"
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO plans(singleton, plan_digest, expected_trials) "
                    "VALUES(1, ?, ?)",
                    (plan_digest, expected_trials),
                )
            elif (
                row["plan_digest"] != plan_digest
                or row["expected_trials"] != expected_trials
            ):
                raise ModelStudyStoreInvariantError(
                    "database is already bound to a different frozen plan"
                )

    def register_trials(
        self, *, plan_digest: str, identities: tuple[TrialIdentity, ...]
    ) -> None:
        """Register ordered trial identities, rejecting any identity or order drift."""

        with self._connect() as connection:
            self._create_schema(connection)
            plan = self._plan(connection, plan_digest)
            if len(identities) != plan["expected_trials"]:
                raise ModelStudyStoreInvariantError(
                    "frozen plan has a different expected trial count"
                )
            expected = [
                (ordinal, identity.trial_id, _identity_json(identity))
                for ordinal, identity in enumerate(identities)
            ]
            if len({identity.trial_id for identity in identities}) != len(identities):
                raise ModelStudyStoreInvariantError(
                    "frozen plan has duplicate trial IDs"
                )
            for ordinal, trial_id, identity_json in expected:
                connection.execute(
                    "INSERT OR IGNORE INTO trials"
                    "(plan_digest, trial_id, ordinal, identity_json) "
                    "VALUES(?, ?, ?, ?)",
                    (plan_digest, trial_id, ordinal, identity_json),
                )
            actual = connection.execute(
                "SELECT ordinal, trial_id, identity_json FROM trials "
                "WHERE plan_digest = ? ORDER BY ordinal",
                (plan_digest,),
            ).fetchall()
            actual_values = [
                (row["ordinal"], row["trial_id"], bytes(row["identity_json"]))
                for row in actual
            ]
            if actual_values != expected:
                raise ModelStudyStoreInvariantError(
                    "stored trial plan differs from frozen identity/order"
                )

    def pending_trials(self, *, plan_digest: str) -> tuple[TrialIdentity, ...]:
        """Return pending trials in frozen ordinal order."""

        with self._connect() as connection:
            self._create_schema(connection)
            self._plan(connection, plan_digest)
            rows = connection.execute(
                "SELECT identity_json FROM trials WHERE plan_digest = ? "
                "AND terminal_status IS NULL ORDER BY ordinal",
                (plan_digest,),
            ).fetchall()
        return tuple(_identity_from_json(bytes(row["identity_json"])) for row in rows)

    def terminal_trials(self, *, plan_digest: str) -> tuple[TerminalRecord, ...]:
        """Return finalized trials in frozen ordinal order."""

        with self._connect() as connection:
            self._create_schema(connection)
            self._plan(connection, plan_digest)
            rows = connection.execute(
                """
                SELECT t.identity_json, t.terminal_attempt_index, t.terminal_bytes,
                       a.status, a.request_digest, a.response_digest, a.error_type,
                       a.prompt_tokens, a.completion_tokens, a.duration_ns
                FROM trials AS t
                JOIN attempts AS a
                  ON a.plan_digest = t.plan_digest
                 AND a.trial_id = t.trial_id
                 AND a.attempt_index = t.terminal_attempt_index
                WHERE t.plan_digest = ? AND t.terminal_status IS NOT NULL
                ORDER BY t.ordinal
                """,
                (plan_digest,),
            ).fetchall()
        return tuple(_terminal_record(row) for row in rows)

    def attempts_for(
        self, *, plan_digest: str, trial_id: str
    ) -> tuple[AttemptRecord, ...]:
        """Return ordered append-only attempts for a registered trial."""

        with self._connect() as connection:
            self._create_schema(connection)
            row = connection.execute(
                "SELECT identity_json FROM trials "
                "WHERE plan_digest = ? AND trial_id = ?",
                (plan_digest, trial_id),
            ).fetchone()
            if row is None:
                raise ModelStudyStoreInvariantError("trial is not part of frozen plan")
            identity = _identity_from_json(bytes(row["identity_json"]))
            rows = connection.execute(
                "SELECT attempt_index, status, request_digest, response_digest, "
                "error_type, prompt_tokens, completion_tokens, duration_ns, "
                "finalizes_trial FROM attempts WHERE plan_digest = ? AND trial_id = ? "
                "ORDER BY attempt_index",
                (plan_digest, trial_id),
            ).fetchall()
        return tuple(_attempt_record(identity, attempt) for attempt in rows)

    def record_attempt(
        self,
        *,
        plan_digest: str,
        identity: TrialIdentity,
        attempt_index: int,
        status: TerminalStatus,
        request_digest: str | None,
        response_digest: str | None = None,
        error_type: str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        duration_ns: int | None = None,
        finalize: bool = False,
        terminal_bytes: bytes | None = None,
    ) -> bool:
        """Append one attempt and optionally atomically finalize its trial.

        Retryable transport failures and interruptions remain resumable by using
        ``finalize=False``.  Repeating exactly the same append is a no-op;
        changing an existing attempt or a final receipt raises an invariant error.
        """

        _validate_attempt(
            identity=identity,
            attempt_index=attempt_index,
            status=status,
            request_digest=request_digest,
            response_digest=response_digest,
            error_type=error_type,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration_ns=duration_ns,
            finalize=finalize,
            terminal_bytes=terminal_bytes,
        )
        with self._connect() as connection:
            self._create_schema(connection)
            trial = connection.execute(
                "SELECT identity_json, terminal_status, terminal_attempt_index, "
                "terminal_bytes FROM trials WHERE plan_digest = ? AND trial_id = ?",
                (plan_digest, identity.trial_id),
            ).fetchone()
            if trial is None:
                raise ModelStudyStoreInvariantError("trial is not part of frozen plan")
            if bytes(trial["identity_json"]) != _identity_json(identity):
                raise ModelStudyStoreInvariantError("trial identity differs from plan")
            values = _attempt_values(
                plan_digest=plan_digest,
                identity=identity,
                attempt_index=attempt_index,
                status=status,
                request_digest=request_digest,
                response_digest=response_digest,
                error_type=error_type,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                duration_ns=duration_ns,
                finalize=finalize,
            )
            if trial["terminal_status"] is not None:
                existing_final = connection.execute(
                    "SELECT status, request_digest, response_digest, error_type, "
                    "prompt_tokens, completion_tokens, duration_ns, finalizes_trial "
                    "FROM attempts WHERE plan_digest = ? AND trial_id = ? "
                    "AND attempt_index = ?",
                    (plan_digest, identity.trial_id, attempt_index),
                ).fetchone()
                if (
                    finalize
                    and trial["terminal_attempt_index"] == attempt_index
                    and bytes(trial["terminal_bytes"]) == terminal_bytes
                    and existing_final is not None
                    and tuple(existing_final) == values[3:]
                ):
                    return False
                raise ModelStudyStoreInvariantError("trial already has a final state")
            existing = connection.execute(
                "SELECT status, request_digest, response_digest, error_type, "
                "prompt_tokens, completion_tokens, duration_ns, finalizes_trial "
                "FROM attempts WHERE plan_digest = ? AND trial_id = ? "
                "AND attempt_index = ?",
                (plan_digest, identity.trial_id, attempt_index),
            ).fetchone()
            if existing is not None:
                if tuple(existing) == values[3:]:
                    return False
                raise ModelStudyStoreInvariantError(
                    "attempt index has conflicting bytes"
                )
            count = connection.execute(
                "SELECT COUNT(*) AS count FROM attempts "
                "WHERE plan_digest = ? AND trial_id = ?",
                (plan_digest, identity.trial_id),
            ).fetchone()
            if count["count"] != attempt_index:
                raise ModelStudyStoreInvariantError(
                    "attempt index must append to the existing trial ledger"
                )
            connection.execute(
                "INSERT INTO attempts"
                "(plan_digest, trial_id, attempt_index, status, request_digest, "
                "response_digest, error_type, prompt_tokens, completion_tokens, "
                "duration_ns, finalizes_trial) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                values,
            )
            if finalize:
                if terminal_bytes is None:
                    raise AssertionError(
                        "validated terminal bytes unexpectedly missing"
                    )
                changed = connection.execute(
                    "UPDATE trials SET terminal_status = ?, "
                    "terminal_attempt_index = ?, "
                    "terminal_bytes = ? WHERE plan_digest = ? AND trial_id = ? "
                    "AND terminal_status IS NULL",
                    (
                        status.value,
                        attempt_index,
                        sqlite3.Binary(terminal_bytes),
                        plan_digest,
                        identity.trial_id,
                    ),
                ).rowcount
                if changed != 1:
                    raise ModelStudyStoreInvariantError("could not finalize trial")
            return True

    def finalize_terminal(
        self,
        *,
        plan_digest: str,
        identity: TrialIdentity,
        attempt_index: int,
        status: TerminalStatus,
        request_digest: str | None,
        terminal_bytes: bytes,
        response_digest: str | None = None,
        error_type: str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        duration_ns: int | None = None,
    ) -> bool:
        """Convenience form for an attempt that definitively closes a trial."""

        return self.record_attempt(
            plan_digest=plan_digest,
            identity=identity,
            attempt_index=attempt_index,
            status=status,
            request_digest=request_digest,
            response_digest=response_digest,
            error_type=error_type,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration_ns=duration_ns,
            finalize=True,
            terminal_bytes=terminal_bytes,
        )

    def summary(self, *, plan_digest: str) -> dict[str, int]:
        """Return reproducible state counts without host-specific metadata."""

        with self._connect() as connection:
            self._create_schema(connection)
            plan = self._plan(connection, plan_digest)
            rows = connection.execute(
                "SELECT terminal_status, COUNT(*) AS count FROM trials "
                "WHERE plan_digest = ? GROUP BY terminal_status",
                (plan_digest,),
            ).fetchall()
            attempts = connection.execute(
                "SELECT COUNT(*) AS count FROM attempts WHERE plan_digest = ?",
                (plan_digest,),
            ).fetchone()
        result = {
            "expected_trials": plan["expected_trials"],
            "attempts": attempts["count"],
        }
        result["pending"] = 0
        for status in TerminalStatus:
            result[status.value] = 0
        for row in rows:
            key = row["terminal_status"] or "pending"
            result[key] = row["count"]
        return result

    def integrity_check(self, *, plan_digest: str) -> None:
        """Raise when SQLite or ledger invariants are inconsistent."""

        with self._connect() as connection:
            self._create_schema(connection)
            plan = self._plan(connection, plan_digest)
            quick = connection.execute("PRAGMA integrity_check").fetchone()
            if quick is None or quick[0] != "ok":
                raise ModelStudyStoreInvariantError("SQLite integrity check failed")
            count = connection.execute(
                "SELECT COUNT(*) AS count FROM trials WHERE plan_digest = ?",
                (plan_digest,),
            ).fetchone()
            if count["count"] != plan["expected_trials"]:
                raise ModelStudyStoreInvariantError(
                    "registered trial count differs from plan"
                )
            bad = connection.execute(
                """
                SELECT 1 FROM trials AS t
                LEFT JOIN attempts AS a
                  ON a.plan_digest = t.plan_digest
                 AND a.trial_id = t.trial_id
                 AND a.attempt_index = t.terminal_attempt_index
                WHERE t.plan_digest = ?
                  AND t.terminal_status IS NOT NULL
                  AND (a.trial_id IS NULL OR a.finalizes_trial != 1
                       OR a.status != t.terminal_status)
                """,
                (plan_digest,),
            ).fetchone()
            if bad is not None:
                raise ModelStudyStoreInvariantError(
                    "terminal trial lacks matching attempt"
                )

    def _plan(self, connection: sqlite3.Connection, plan_digest: str) -> sqlite3.Row:
        _digest(plan_digest, "plan_digest")
        row = connection.execute(
            "SELECT plan_digest, expected_trials FROM plans WHERE plan_digest = ?",
            (plan_digest,),
        ).fetchone()
        if row is None:
            raise ModelStudyStoreInvariantError("unknown frozen plan")
        return cast(sqlite3.Row, row)


def _attempt_values(
    *,
    plan_digest: str,
    identity: TrialIdentity,
    attempt_index: int,
    status: TerminalStatus,
    request_digest: str | None,
    response_digest: str | None,
    error_type: str | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    duration_ns: int | None,
    finalize: bool,
) -> tuple[object, ...]:
    return (
        plan_digest,
        identity.trial_id,
        attempt_index,
        status.value,
        request_digest,
        response_digest,
        error_type,
        prompt_tokens,
        completion_tokens,
        duration_ns,
        int(finalize),
    )


def _attempt_record(identity: TrialIdentity, row: sqlite3.Row) -> AttemptRecord:
    return AttemptRecord(
        identity=identity,
        attempt_index=row["attempt_index"],
        status=TerminalStatus(row["status"]),
        request_digest=row["request_digest"],
        response_digest=row["response_digest"],
        error_type=row["error_type"],
        prompt_tokens=row["prompt_tokens"],
        completion_tokens=row["completion_tokens"],
        duration_ns=row["duration_ns"],
        finalizes_trial=bool(row["finalizes_trial"]),
    )


def _terminal_record(row: sqlite3.Row) -> TerminalRecord:
    identity = _identity_from_json(bytes(row["identity_json"]))
    status = TerminalStatus(row["status"])
    return TerminalRecord(
        terminal=TrialTerminal(
            identity=identity,
            status=status,
            response_digest=row["response_digest"],
            error_type=row["error_type"],
        ),
        attempt_index=row["terminal_attempt_index"],
        request_digest=row["request_digest"],
        prompt_tokens=row["prompt_tokens"],
        completion_tokens=row["completion_tokens"],
        duration_ns=row["duration_ns"],
        terminal_bytes=bytes(row["terminal_bytes"]),
    )


def _validate_attempt(
    *,
    identity: TrialIdentity,
    attempt_index: int,
    status: TerminalStatus,
    request_digest: str | None,
    response_digest: str | None,
    error_type: str | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    duration_ns: int | None,
    finalize: bool,
    terminal_bytes: bytes | None,
) -> None:
    if attempt_index < 0:
        raise ValueError("attempt_index must be non-negative")
    if request_digest is not None:
        _digest(request_digest, "request_digest")
    if response_digest is not None:
        _digest(response_digest, "response_digest")
    if prompt_tokens is not None and prompt_tokens < 0:
        raise ValueError("prompt_tokens must be non-negative")
    if completion_tokens is not None and completion_tokens < 0:
        raise ValueError("completion_tokens must be non-negative")
    if duration_ns is not None and duration_ns < 0:
        raise ValueError("duration_ns must be non-negative")
    TrialTerminal(
        identity=identity,
        status=status,
        response_digest=response_digest,
        error_type=error_type,
    )
    if finalize != (terminal_bytes is not None):
        raise ValueError("terminal_bytes are required exactly when finalizing")
    if terminal_bytes is not None and not terminal_bytes:
        raise ValueError("terminal_bytes must be non-empty")


def _identity_json(identity: TrialIdentity) -> bytes:
    _validate_semantic_identity(identity)
    payload = asdict(identity)
    return (
        json.dumps(payload, allow_nan=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode()


def _identity_from_json(data: bytes) -> TrialIdentity:
    payload = json.loads(data)
    if not isinstance(payload, dict):
        raise ModelStudyStoreInvariantError("stored trial identity is not an object")
    model = payload.get("model")
    config = payload.get("config")
    if not isinstance(model, dict) or not isinstance(config, dict):
        raise ModelStudyStoreInvariantError("stored trial identity is malformed")
    return TrialIdentity(
        study_id=_string(payload, "study_id"),
        trial_id=_string(payload, "trial_id"),
        arm=StudyArm(_string(payload, "arm")),
        model=ModelIdentity(
            provider=_string(model, "provider"),
            tag=_string(model, "tag"),
            blob_digest=_string(model, "blob_digest"),
            parameter_count=_integer(model, "parameter_count"),
            quantization=_string(model, "quantization"),
            license=_string(model, "license"),
            license_evidence=LicenseEvidence(_string(model, "license_evidence")),
            license_source=_string(model, "license_source"),
            runtime_version=_string(model, "runtime_version"),
            template_digest=_string(model, "template_digest"),
        ),
        config=ModelConfig(
            temperature=_number(config, "temperature"),
            top_p=_number(config, "top_p"),
            presence_penalty=_number(config, "presence_penalty"),
            repeat_penalty=_number(config, "repeat_penalty"),
            context_tokens=_integer(config, "context_tokens"),
            max_output_tokens=_integer(config, "max_output_tokens"),
            thinking=_boolean(config, "thinking"),
            streaming=_boolean(config, "streaming"),
            tools_enabled=_boolean(config, "tools_enabled"),
            response_schema_version=_integer(config, "response_schema_version"),
        ),
        input_ref=_string(payload, "input_ref"),
        input_digest=_string(payload, "input_digest"),
        prompt_digest=_string(payload, "prompt_digest"),
        response_schema_digest=_string(payload, "response_schema_digest"),
        seed=_integer(payload, "seed"),
        replicate_index=_integer(payload, "replicate_index"),
        adapter_version=_string(payload, "adapter_version"),
    )


def _string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ModelStudyStoreInvariantError(f"stored identity has invalid {key}")
    return value


def _integer(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ModelStudyStoreInvariantError(f"stored identity has invalid {key}")
    return value


def _number(payload: dict[str, object], key: str) -> float:
    value = payload.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ModelStudyStoreInvariantError(f"stored identity has invalid {key}")
    return float(value)


def _boolean(payload: dict[str, object], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ModelStudyStoreInvariantError(f"stored identity has invalid {key}")
    return value


def _digest(value: str, field: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")


def _validate_semantic_identity(identity: TrialIdentity) -> None:
    """Keep host paths and observation times outside the semantic trial key."""

    if Path(identity.input_ref).is_absolute() or PureWindowsPath(
        identity.input_ref
    ).is_absolute():
        raise ValueError("input_ref must be a logical reference, not an absolute path")
