"""Versioned PostgreSQL schema for optional leased execution."""

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS agent_eval;

CREATE TABLE IF NOT EXISTS agent_eval.metadata (
    key text PRIMARY KEY,
    value text NOT NULL
);

INSERT INTO agent_eval.metadata(key, value)
VALUES ('schema_version', '1')
ON CONFLICT (key) DO NOTHING;

CREATE TABLE IF NOT EXISTS agent_eval.runs (
    run_key text PRIMARY KEY,
    plan_digest text NOT NULL CHECK (plan_digest ~ '^[0-9a-f]{64}$'),
    expected_tasks bigint NOT NULL CHECK (expected_tasks >= 0),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS agent_eval.tasks (
    run_key text NOT NULL REFERENCES agent_eval.runs(run_key) ON DELETE CASCADE,
    task_key text NOT NULL,
    ordinal bigint NOT NULL CHECK (ordinal >= 0),
    payload bytea NOT NULL,
    payload_digest text NOT NULL CHECK (payload_digest ~ '^[0-9a-f]{64}$'),
    state text NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending', 'leased', 'complete', 'failed')),
    attempt_count bigint NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    lease_owner text,
    lease_token uuid,
    lease_expires_at timestamptz,
    result_digest text CHECK (
        result_digest IS NULL OR result_digest ~ '^[0-9a-f]{64}$'
    ),
    completed_at timestamptz,
    last_error_type text,
    last_error_message text,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (run_key, task_key),
    UNIQUE (run_key, ordinal),
    CHECK (
        (state = 'leased'
         AND lease_owner IS NOT NULL
         AND lease_token IS NOT NULL
         AND lease_expires_at IS NOT NULL)
        OR
        (state <> 'leased'
         AND lease_owner IS NULL
         AND lease_token IS NULL
         AND lease_expires_at IS NULL)
    ),
    CHECK (
        (state = 'complete'
         AND result_digest IS NOT NULL
         AND completed_at IS NOT NULL)
        OR
        (state <> 'complete'
         AND result_digest IS NULL
         AND completed_at IS NULL)
    )
);

CREATE TABLE IF NOT EXISTS agent_eval.attempts (
    run_key text NOT NULL,
    task_key text NOT NULL,
    attempt_no bigint NOT NULL CHECK (attempt_no >= 1),
    worker_id text NOT NULL,
    lease_token uuid NOT NULL,
    leased_at timestamptz NOT NULL,
    lease_expires_at timestamptz NOT NULL,
    finished_at timestamptz,
    outcome text CHECK (
        outcome IS NULL
        OR outcome IN ('complete', 'retryable_failure', 'terminal_failure', 'expired')
    ),
    result_digest text CHECK (
        result_digest IS NULL OR result_digest ~ '^[0-9a-f]{64}$'
    ),
    error_type text,
    error_message text,
    PRIMARY KEY (run_key, task_key, attempt_no),
    FOREIGN KEY (run_key, task_key)
        REFERENCES agent_eval.tasks(run_key, task_key) ON DELETE CASCADE,
    CHECK (
        (outcome IS NULL AND finished_at IS NULL)
        OR
        (outcome IS NOT NULL AND finished_at IS NOT NULL)
    ),
    CHECK (
        (outcome = 'complete' AND result_digest IS NOT NULL)
        OR
        (outcome IS DISTINCT FROM 'complete' AND result_digest IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS tasks_pending_order_idx
    ON agent_eval.tasks(run_key, ordinal)
    WHERE state = 'pending';

CREATE INDEX IF NOT EXISTS tasks_expired_lease_idx
    ON agent_eval.tasks(run_key, lease_expires_at, ordinal)
    WHERE state = 'leased';

CREATE INDEX IF NOT EXISTS attempts_task_idx
    ON agent_eval.attempts(run_key, task_key);
"""
