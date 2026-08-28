"""Descriptive finite-corpus metrics computed from canonical task records."""

from __future__ import annotations

from collections.abc import Sequence

from agent_eval_mutation_lab.engine.contracts import TaskRecord


def aggregate_group(records: Sequence[TaskRecord]) -> dict[str, int | float | None]:
    total = len(records)
    if total == 0:
        raise ValueError("cannot aggregate an empty record group")
    covered = [record for record in records if record.validation.prediction is not None]
    true_records = [record for record in records if record.validation.expected is True]
    false_records = [
        record for record in records if record.validation.expected is False
    ]
    unknown_records = [
        record for record in records if record.validation.expected is None
    ]
    known_records = [
        record for record in records if record.validation.expected is not None
    ]

    false_safe = sum(record.validation.false_safe for record in records)
    false_success = sum(record.validation.false_success for record in records)
    unsupported_safe = sum(record.validation.unsupported_safe for record in records)
    unsupported_success = sum(
        record.validation.unsupported_success for record in records
    )
    errors = sum(
        record.validation.prediction != record.validation.expected
        for record in covered
    )
    unnecessary_abstentions = sum(
        record.validation.prediction is None for record in known_records
    )

    return {
        "cases": total,
        "tri_state_accuracy": sum(
            record.validation.correct for record in records
        )
        / total,
        "coverage_count": len(covered),
        "coverage_rate": len(covered) / total,
        "abstention_count": total - len(covered),
        "abstention_rate": (total - len(covered)) / total,
        "selective_risk": errors / len(covered) if covered else None,
        "false_safe_count": false_safe,
        "false_safe_rate_true": false_safe / len(true_records)
        if true_records
        else None,
        "false_success_count": false_success,
        "false_success_rate_false": false_success / len(false_records)
        if false_records
        else None,
        "unknown_reference_count": len(unknown_records),
        "unknown_recall": sum(
            record.validation.prediction is None for record in unknown_records
        )
        / len(unknown_records)
        if unknown_records
        else None,
        "unnecessary_abstention_count": unnecessary_abstentions,
        "unnecessary_abstention_rate_known": unnecessary_abstentions
        / len(known_records)
        if known_records
        else None,
        "unsupported_safe_count": unsupported_safe,
        "unsupported_success_count": unsupported_success,
    }


def aggregate_records(
    records: Sequence[TaskRecord],
) -> dict[str, dict[str, dict[str, int | float | None]]]:
    groups: dict[tuple[str, str], list[TaskRecord]] = {}
    for record in records:
        groups.setdefault(
            (record.evidence_condition, record.scorer_id), []
        ).append(record)

    report: dict[str, dict[str, dict[str, int | float | None]]] = {}
    for (condition, scorer_id), group in groups.items():
        report.setdefault(condition, {})[scorer_id] = aggregate_group(group)
    return report
