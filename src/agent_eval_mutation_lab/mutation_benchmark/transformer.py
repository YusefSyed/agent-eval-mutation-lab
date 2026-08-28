"""ASCII-only, AST-addressed source mutation with fail-closed guards."""

from __future__ import annotations

import ast
import difflib
import hashlib
from dataclasses import dataclass
from typing import Protocol, cast

from agent_eval_mutation_lab.mutation_benchmark.contracts import (
    MutationSpec,
    TransformErrorCode,
    TransformResult,
)


class MutationTransformError(ValueError):
    """A mutation could not prove it changed exactly the intended AST node."""

    def __init__(self, code: TransformErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class _Span:
    start: int
    end: int


class _PositionedNode(Protocol):
    lineno: int
    end_lineno: int
    col_offset: int
    end_col_offset: int


def transform_source(
    source: bytes,
    spec: MutationSpec,
    *,
    expected_source_sha256: str,
    filename: str = "<mutation-source>",
) -> TransformResult:
    """Replace one hash-addressed node and validate the result before returning.

    The source and replacement are restricted to ASCII.  This is intentional:
    Python's AST offsets are byte offsets, and an ASCII-only contract makes the
    source-span calculation unambiguous across supported Python versions.
    """

    text = _decode_ascii(source, TransformErrorCode.NON_ASCII_SOURCE, "source")
    actual_source_digest = _sha256(source)
    if actual_source_digest != expected_source_sha256:
        raise MutationTransformError(
            TransformErrorCode.SOURCE_DIGEST_MISMATCH,
            "source SHA-256 does not match the mutation baseline",
        )
    _decode_ascii(
        spec.replacement.encode("utf-8"),
        TransformErrorCode.REPLACEMENT_NOT_ASCII,
        "replacement",
    )
    tree = _parse(text, filename, TransformErrorCode.SOURCE_PARSE_ERROR)
    function = _find_unique_function(tree, spec.function_name)
    node, segment, span = _find_unique_target(text, function, spec)
    del node
    matched_digest = _sha256(segment.encode("ascii"))
    replacement = spec.replacement
    transformed_text = text[: span.start] + replacement + text[span.end :]
    transformed_bytes = transformed_text.encode("ascii")
    if transformed_bytes == source:
        raise MutationTransformError(
            TransformErrorCode.NO_CHANGE,
            "replacement leaves source bytes unchanged",
        )
    transformed_tree = _parse(
        transformed_text, filename, TransformErrorCode.TRANSFORM_PARSE_ERROR
    )
    try:
        compile(transformed_tree, filename, "exec")
    except (SyntaxError, ValueError, TypeError) as error:
        raise MutationTransformError(
            TransformErrorCode.TRANSFORM_COMPILE_ERROR,
            f"transformed source does not compile: {error}",
        ) from error
    return TransformResult(
        mutation_id=spec.mutation_id,
        baseline_source_sha256=actual_source_digest,
        transformed_source_sha256=_sha256(transformed_bytes),
        matched_segment_sha256=matched_digest,
        transformed_bytes=transformed_bytes,
        unified_diff="".join(
            difflib.unified_diff(
                text.splitlines(keepends=True),
                transformed_text.splitlines(keepends=True),
                fromfile="baseline",
                tofile="mutated",
                n=0,
            )
        ),
    )


def _decode_ascii(source: bytes, code: TransformErrorCode, subject: str) -> str:
    try:
        return source.decode("ascii")
    except UnicodeDecodeError as error:
        raise MutationTransformError(
            code, f"{subject} must contain only ASCII"
        ) from error


def _parse(text: str, filename: str, code: TransformErrorCode) -> ast.Module:
    try:
        return ast.parse(text, filename=filename, mode="exec")
    except SyntaxError as error:
        raise MutationTransformError(
            code, f"source parsing failed: {error.msg}"
        ) from error


def _find_unique_function(
    tree: ast.Module, name: str
) -> ast.FunctionDef | ast.AsyncFunctionDef:
    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    ]
    if len(functions) != 1:
        raise MutationTransformError(
            TransformErrorCode.FUNCTION_NOT_UNIQUE,
            f"expected exactly one function named {name!r}; found {len(functions)}",
        )
    return functions[0]


def _find_unique_target(
    text: str,
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    spec: MutationSpec,
) -> tuple[ast.AST, str, _Span]:
    candidates: list[tuple[ast.AST, str, _Span]] = []
    for node in ast.walk(function):
        if type(node).__name__ != spec.node_type:
            continue
        span = _node_span(text, node)
        segment = text[span.start : span.end]
        if _sha256(segment.encode("ascii")) == spec.expected_segment_sha256:
            candidates.append((node, segment, span))
    if len(candidates) != 1:
        raise MutationTransformError(
            TransformErrorCode.TARGET_NOT_UNIQUE,
            "expected exactly one node matching type and source-segment SHA-256; "
            f"found {len(candidates)}",
        )
    return candidates[0]


def _node_span(text: str, node: ast.AST) -> _Span:
    if not hasattr(node, "lineno") or not hasattr(node, "end_lineno"):
        raise MutationTransformError(
            TransformErrorCode.TARGET_NOT_UNIQUE,
            "target node has no source position",
        )
    lines = text.splitlines(keepends=True)
    starts: list[int] = [0]
    for line in lines:
        starts.append(starts[-1] + len(line))
    positioned = cast(_PositionedNode, node)
    line_number = positioned.lineno
    end_line_number = positioned.end_lineno
    column = positioned.col_offset
    end_column = positioned.end_col_offset
    return _Span(
        start=starts[line_number - 1] + column,
        end=starts[end_line_number - 1] + end_column,
    )


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
