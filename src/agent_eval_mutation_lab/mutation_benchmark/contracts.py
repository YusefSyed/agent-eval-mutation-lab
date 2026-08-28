"""Immutable contracts for deterministic, source-level mutations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TransformErrorCode(StrEnum):
    """Reasons a source transformation is rejected rather than guessed."""

    NON_ASCII_SOURCE = "non_ascii_source"
    SOURCE_DIGEST_MISMATCH = "source_digest_mismatch"
    SOURCE_PARSE_ERROR = "source_parse_error"
    FUNCTION_NOT_UNIQUE = "function_not_unique"
    TARGET_NOT_UNIQUE = "target_not_unique"
    REPLACEMENT_NOT_ASCII = "replacement_not_ascii"
    NO_CHANGE = "no_change"
    TRANSFORM_PARSE_ERROR = "transform_parse_error"
    TRANSFORM_COMPILE_ERROR = "transform_compile_error"


class MutationPartition(StrEnum):
    """Catalog provenance; development results are never scored as held out."""

    DEVELOPMENT = "development"
    HELD_OUT = "held_out"


class MutantStatus(StrEnum):
    """Result classes with explicit denominator boundaries."""

    KILLED = "killed"
    SURVIVED = "survived"
    INVALID = "invalid"
    EQUIVALENT = "equivalent"
    PLAUSIBLY_EQUIVALENT = "plausibly_equivalent"
    RUN_ERROR = "run_error"


class EquivalenceAssessment(StrEnum):
    """Predeclared review outcome for a mutation's semantic distinctness."""

    NONE = "none"
    EQUIVALENT = "equivalent"
    PLAUSIBLY_EQUIVALENT = "plausibly_equivalent"


@dataclass(frozen=True, slots=True, kw_only=True)
class MutationSpec:
    """One exact AST node replacement guarded by two content digests.

    ``node_type`` is deliberately the Python AST class name (for example,
    ``"Compare"`` or ``"Call"``), instead of a lossy project-local enum.
    """

    mutation_id: str
    function_name: str
    node_type: str
    expected_segment_sha256: str
    replacement: str
    partition: MutationPartition = MutationPartition.DEVELOPMENT
    operator_id: str = "exact_source_replacement"
    semantic_rule: str = ""
    expected_semantic_change: str = ""
    activation_case: str = ""
    equivalence_assessment: EquivalenceAssessment = EquivalenceAssessment.NONE


@dataclass(frozen=True, slots=True, kw_only=True)
class MutationManifest:
    """A source identity and ordered set of independently addressable specs."""

    schema_version: int
    source_path: str
    baseline_source_sha256: str
    mutations: tuple[MutationSpec, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class TransformResult:
    """Auditable in-memory result of one successful source mutation."""

    mutation_id: str
    baseline_source_sha256: str
    transformed_source_sha256: str
    matched_segment_sha256: str
    transformed_bytes: bytes
    unified_diff: str


@dataclass(frozen=True, slots=True, kw_only=True)
class TestRunResult:
    """Normalized test-protocol outcome; wall-clock timing is noncanonical."""

    return_code: int | None
    timed_out: bool
    test_session_started: bool
    import_origin_verified: bool
    failing_test_ids: tuple[str, ...]
    error_code: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class MutantResult:
    """One classified mutant result."""

    mutation_id: str
    partition: MutationPartition
    status: MutantStatus
    baseline_source_sha256: str
    transformed_source_sha256: str | None
    transformed_diff_sha256: str | None
    test_run: TestRunResult
    reason: str
