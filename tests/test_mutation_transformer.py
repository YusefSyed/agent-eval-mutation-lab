from __future__ import annotations

import hashlib

import pytest

from agent_eval_mutation_lab.mutation_benchmark.contracts import (
    MutationSpec,
    TransformErrorCode,
)
from agent_eval_mutation_lab.mutation_benchmark.transformer import (
    MutationTransformError,
    transform_source,
)


def _sha256(value: str | bytes) -> str:
    raw = value.encode("ascii") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


def _spec(
    *,
    source_segment: str = "value > 3",
    replacement: str = "value >= 3",
    node_type: str = "Compare",
    function_name: str = "classify",
) -> MutationSpec:
    return MutationSpec(
        mutation_id="boundary-inclusive",
        function_name=function_name,
        node_type=node_type,
        expected_segment_sha256=_sha256(source_segment),
        replacement=replacement,
    )


SOURCE = b"def classify(value: int) -> bool:\n    return value > 3\n"


def test_transform_replaces_one_hash_addressed_node_and_emits_diff() -> None:
    result = transform_source(
        SOURCE,
        _spec(),
        expected_source_sha256=_sha256(SOURCE),
        filename="fixture.py",
    )

    assert result.transformed_bytes == (
        b"def classify(value: int) -> bool:\n    return value >= 3\n"
    )
    assert result.baseline_source_sha256 == _sha256(SOURCE)
    assert result.transformed_source_sha256 == _sha256(result.transformed_bytes)
    assert result.matched_segment_sha256 == _sha256("value > 3")
    assert "-    return value > 3" in result.unified_diff
    assert "+    return value >= 3" in result.unified_diff


def test_rejects_non_ascii_source() -> None:
    with pytest.raises(MutationTransformError) as raised:
        transform_source(
            b"def classify():\n    return '\xc3\xa9'\n",
            _spec(),
            expected_source_sha256="0" * 64,
        )
    assert raised.value.code is TransformErrorCode.NON_ASCII_SOURCE


def test_rejects_source_hash_drift() -> None:
    with pytest.raises(MutationTransformError) as raised:
        transform_source(SOURCE, _spec(), expected_source_sha256="0" * 64)
    assert raised.value.code is TransformErrorCode.SOURCE_DIGEST_MISMATCH


def test_rejects_parse_error_before_matching() -> None:
    source = b"def classify(:\n    pass\n"
    with pytest.raises(MutationTransformError) as raised:
        transform_source(source, _spec(), expected_source_sha256=_sha256(source))
    assert raised.value.code is TransformErrorCode.SOURCE_PARSE_ERROR


def test_rejects_missing_or_duplicate_named_function() -> None:
    with pytest.raises(MutationTransformError) as missing:
        transform_source(
            SOURCE,
            _spec(function_name="missing"),
            expected_source_sha256=_sha256(SOURCE),
        )
    assert missing.value.code is TransformErrorCode.FUNCTION_NOT_UNIQUE

    duplicate = SOURCE + b"\ndef classify(value: int) -> bool:\n    return value > 3\n"
    with pytest.raises(MutationTransformError) as repeated:
        transform_source(
            duplicate,
            _spec(),
            expected_source_sha256=_sha256(duplicate),
        )
    assert repeated.value.code is TransformErrorCode.FUNCTION_NOT_UNIQUE


def test_rejects_zero_or_multiple_target_matches() -> None:
    with pytest.raises(MutationTransformError) as zero:
        transform_source(
            SOURCE,
            _spec(source_segment="value < 3"),
            expected_source_sha256=_sha256(SOURCE),
        )
    assert zero.value.code is TransformErrorCode.TARGET_NOT_UNIQUE

    duplicate = (
        b"def classify(value: int) -> bool:\n    return value > 3 and value > 3\n"
    )
    with pytest.raises(MutationTransformError) as multiple:
        transform_source(
            duplicate,
            _spec(),
            expected_source_sha256=_sha256(duplicate),
        )
    assert multiple.value.code is TransformErrorCode.TARGET_NOT_UNIQUE


def test_rejects_non_ascii_replacement() -> None:
    with pytest.raises(MutationTransformError) as raised:
        transform_source(
            SOURCE,
            _spec(replacement="value >= \u00e9"),
            expected_source_sha256=_sha256(SOURCE),
        )
    assert raised.value.code is TransformErrorCode.REPLACEMENT_NOT_ASCII


def test_rejects_no_change() -> None:
    with pytest.raises(MutationTransformError) as raised:
        transform_source(
            SOURCE,
            _spec(replacement="value > 3"),
            expected_source_sha256=_sha256(SOURCE),
        )
    assert raised.value.code is TransformErrorCode.NO_CHANGE


def test_rejects_invalid_transformed_syntax() -> None:
    with pytest.raises(MutationTransformError) as raised:
        transform_source(
            SOURCE,
            _spec(replacement="value >"),
            expected_source_sha256=_sha256(SOURCE),
        )
    assert raised.value.code is TransformErrorCode.TRANSFORM_PARSE_ERROR


def test_rejects_transformed_source_that_parses_but_does_not_compile() -> None:
    source = (
        b"def classify(value: int) -> bool:\n"
        b"    from __future__ import braces\n"
        b"    return value > 3\n"
    )
    with pytest.raises(MutationTransformError) as raised:
        transform_source(
            source,
            _spec(),
            expected_source_sha256=_sha256(source),
        )
    assert raised.value.code is TransformErrorCode.TRANSFORM_COMPILE_ERROR
