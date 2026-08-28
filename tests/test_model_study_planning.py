from __future__ import annotations

import json
from pathlib import Path

from agent_eval_mutation_lab.model_study.planning import (
    build_model_study_inputs,
    model_record_payload,
    oracle_record_payload,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_plan_has_52_model_safe_records_and_separate_oracle_ledger() -> None:
    model_records, oracle_records = build_model_study_inputs(PROJECT_ROOT)
    assert len(model_records) == 52
    assert len(oracle_records) == 52
    assert [record.input_ref for record in model_records] == [
        record.input_ref for record in oracle_records
    ]
    assert len({record.input_ref for record in model_records}) == 52
    assert all(len(record.payload_digest) == 64 for record in model_records)

    live_bytes = json.dumps(
        [model_record_payload(record) for record in model_records], sort_keys=True
    )
    forbidden = (
        "case_id",
        "family",
        "evidence_condition",
        "expected",
        "attack_success",
        "oracle",
    )
    assert not any(field in live_bytes for field in forbidden)

    analysis_bytes = json.dumps(
        [oracle_record_payload(record) for record in oracle_records], sort_keys=True
    )
    assert "evidence_condition" in analysis_bytes
    assert "expected" in analysis_bytes


def test_model_plan_is_byte_stable() -> None:
    first, _ = build_model_study_inputs(PROJECT_ROOT)
    second, _ = build_model_study_inputs(PROJECT_ROOT)
    first_bytes = json.dumps(
        [model_record_payload(record) for record in first],
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    second_bytes = json.dumps(
        [model_record_payload(record) for record in second],
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    assert first_bytes == second_bytes
