"""One-mutant-per-process execution in ephemeral package snapshots."""

from __future__ import annotations

import hashlib
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path, PurePosixPath

from agent_eval_mutation_lab.mutation_benchmark.contracts import (
    EquivalenceAssessment,
    MutantResult,
    MutantStatus,
    MutationManifest,
    MutationSpec,
    TestRunResult,
)
from agent_eval_mutation_lab.mutation_benchmark.transformer import (
    MutationTransformError,
    transform_source,
)

DEFAULT_KILL_SELECTORS = (
    "tests/test_scorers_v2.py",
    "tests/test_v2_evaluation.py::test_v2_eliminates_observed_false_safe_without_automatic_guilt",
    "tests/test_family_sensitivity.py::test_v2_directional_safety_survives_every_family_omission",
)


def calibrate_timeout(
    project_root: Path,
    *,
    selectors: Sequence[str] = DEFAULT_KILL_SELECTORS,
    repetitions: int = 3,
) -> tuple[float, tuple[float, ...]]:
    """Run the baseline through the exact snapshot path and freeze a timeout."""

    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    durations: list[float] = []
    for _ in range(repetitions):
        started = time.monotonic()
        result = run_baseline(project_root, selectors=selectors, timeout_seconds=60.0)
        durations.append(time.monotonic() - started)
        if result.return_code != 0 or result.timed_out:
            raise RuntimeError("baseline mutation test suite did not pass")
    return max(10.0, 5.0 * max(durations)), tuple(durations)


def run_baseline(
    project_root: Path,
    *,
    selectors: Sequence[str] = DEFAULT_KILL_SELECTORS,
    timeout_seconds: float,
) -> TestRunResult:
    """Run unmodified source through the same snapshot/import protocol."""

    source_relative = Path("src/agent_eval_mutation_lab/scorers_v2.py")
    with tempfile.TemporaryDirectory(prefix="agent-eval-baseline-") as raw:
        snapshot_root = Path(raw)
        _copy_snapshot(project_root, snapshot_root)
        return _run_tests(
            snapshot_root,
            expected_source=snapshot_root / source_relative,
            selectors=selectors,
            timeout_seconds=timeout_seconds,
        )


def run_mutant(
    project_root: Path,
    manifest: MutationManifest,
    spec: MutationSpec,
    *,
    selectors: Sequence[str] = DEFAULT_KILL_SELECTORS,
    timeout_seconds: float,
) -> MutantResult:
    """Generate one mutant in a snapshot, run the frozen suite, and classify it."""

    project_root = project_root.resolve()
    if spec not in manifest.mutations:
        raise ValueError("mutation spec must belong to the supplied manifest")
    source_relative = _safe_relative_path(manifest.source_path)
    source_path = project_root / source_relative
    source = source_path.read_bytes()
    original_digest = _sha256(source)
    if original_digest != manifest.baseline_source_sha256:
        return _invalid(spec, original_digest, "baseline_source_digest_mismatch")
    try:
        transformed = transform_source(
            source,
            spec,
            expected_source_sha256=manifest.baseline_source_sha256,
            filename=manifest.source_path,
        )
    except MutationTransformError as error:
        return _invalid(spec, original_digest, error.code.value)

    with tempfile.TemporaryDirectory(prefix=f"agent-eval-{spec.mutation_id}-") as raw:
        snapshot_root = Path(raw)
        _copy_snapshot(project_root, snapshot_root)
        mutated_source = snapshot_root / source_relative
        mutated_source.write_bytes(transformed.transformed_bytes)
        test_run = _run_tests(
            snapshot_root,
            expected_source=mutated_source,
            selectors=selectors,
            timeout_seconds=timeout_seconds,
        )
    status, reason = _classify(test_run, spec.equivalence_assessment)
    return MutantResult(
        mutation_id=spec.mutation_id,
        partition=spec.partition,
        status=status,
        baseline_source_sha256=transformed.baseline_source_sha256,
        transformed_source_sha256=transformed.transformed_source_sha256,
        transformed_diff_sha256=_sha256(transformed.unified_diff.encode("ascii")),
        test_run=test_run,
        reason=reason,
    )


def _copy_snapshot(project_root: Path, destination: Path) -> None:
    ignored = shutil.ignore_patterns(
        ".git",
        ".venv",
        "__pycache__",
        "*.pyc",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".coverage",
    )
    for directory in ("src", "tests"):
        source = project_root / directory
        if source.is_dir():
            shutil.copytree(source, destination / directory, ignore=ignored)
    for filename in ("pyproject.toml", "uv.lock"):
        source = project_root / filename
        if source.is_file():
            shutil.copy2(source, destination / filename)


def _safe_relative_path(value: str) -> Path:
    pure_path = PurePosixPath(value)
    if not value or pure_path.is_absolute() or ".." in pure_path.parts:
        raise ValueError("source_path must be a safe repository-relative path")
    return Path(*pure_path.parts)


def _run_tests(
    snapshot_root: Path,
    *,
    expected_source: Path,
    selectors: Sequence[str],
    timeout_seconds: float,
) -> TestRunResult:
    marker_path = snapshot_root / ".mutation-test-started"
    junit_path = snapshot_root / ".mutation-junit.xml"
    conftest_path = snapshot_root / "conftest.py"
    conftest_path.write_text(
        "from pathlib import Path\n"
        "import os\n"
        "import agent_eval_mutation_lab.scorers_v2 as target\n"
        "expected = Path(os.environ['AGENT_EVAL_EXPECTED_SOURCE']).resolve()\n"
        "actual = Path(target.__file__).resolve()\n"
        "if actual != expected:\n"
        "    raise RuntimeError(f'import origin mismatch: {actual}')\n"
        "Path(os.environ['AGENT_EVAL_TEST_STARTED']).write_text('started\\n')\n",
        encoding="ascii",
    )
    environment = {
        "AGENT_EVAL_EXPECTED_SOURCE": str(expected_source.resolve()),
        "AGENT_EVAL_TEST_STARTED": str(marker_path.resolve()),
        "HOME": str((snapshot_root / ".home").resolve()),
        "LC_ALL": "C",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHONPATH": str((snapshot_root / "src").resolve()),
        "TMPDIR": str((snapshot_root / ".tmp").resolve()),
    }
    (snapshot_root / ".home").mkdir()
    (snapshot_root / ".tmp").mkdir()
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        *selectors,
        f"--junitxml={junit_path}",
    ]
    try:
        completed = subprocess.Popen(
            command,
            cwd=snapshot_root,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            completed.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            _terminate_process_group(completed)
            return TestRunResult(
                return_code=None,
                timed_out=True,
                test_session_started=marker_path.is_file(),
                import_origin_verified=marker_path.is_file(),
                failing_test_ids=(),
                error_code="timeout",
            )
    except OSError:
        return TestRunResult(
            return_code=None,
            timed_out=False,
            test_session_started=marker_path.is_file(),
            import_origin_verified=marker_path.is_file(),
            failing_test_ids=(),
            error_code="subprocess_start_error",
        )
    started = marker_path.is_file()
    failures = _failing_test_ids(junit_path) if junit_path.is_file() else ()
    return TestRunResult(
        return_code=completed.returncode,
        timed_out=False,
        test_session_started=started,
        import_origin_verified=started,
        failing_test_ids=failures,
        error_code=None if completed.returncode in {0, 1} else "pytest_run_error",
    )


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    """Terminate the entire mutant test tree, then reap its root process."""

    try:
        group_id = process.pid
        os.killpg(group_id, signal.SIGTERM)
        process.wait(timeout=1.0)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def _failing_test_ids(path: Path) -> tuple[str, ...]:
    root = ET.parse(path).getroot()
    failures: list[str] = []
    for case in root.iter("testcase"):
        if case.find("failure") is None and case.find("error") is None:
            continue
        class_name = case.attrib.get("classname", "")
        name = case.attrib.get("name", "")
        failures.append(f"{class_name}::{name}" if class_name else name)
    return tuple(sorted(failures))


def _classify(
    test_run: TestRunResult,
    equivalence: EquivalenceAssessment,
) -> tuple[MutantStatus, str]:
    if not test_run.import_origin_verified:
        return MutantStatus.INVALID, "mutant_import_origin_not_verified"
    if test_run.timed_out and test_run.test_session_started:
        return MutantStatus.KILLED, "test_timeout_after_session_start"
    if test_run.return_code == 0:
        if equivalence is EquivalenceAssessment.EQUIVALENT:
            return MutantStatus.EQUIVALENT, "predeclared_equivalent_mutation"
        if equivalence is EquivalenceAssessment.PLAUSIBLY_EQUIVALENT:
            return (
                MutantStatus.PLAUSIBLY_EQUIVALENT,
                "predeclared_plausibly_equivalent_mutation",
            )
        return MutantStatus.SURVIVED, "frozen_semantic_suite_passed"
    if test_run.return_code == 1:
        return MutantStatus.KILLED, "frozen_semantic_suite_failed"
    return MutantStatus.RUN_ERROR, "pytest_protocol_or_environment_error"


def _invalid(spec: MutationSpec, baseline_digest: str, reason: str) -> MutantResult:
    return MutantResult(
        mutation_id=spec.mutation_id,
        partition=spec.partition,
        status=MutantStatus.INVALID,
        baseline_source_sha256=baseline_digest,
        transformed_source_sha256=None,
        transformed_diff_sha256=None,
        test_run=TestRunResult(
            return_code=None,
            timed_out=False,
            test_session_started=False,
            import_origin_verified=False,
            failing_test_ids=(),
            error_code=reason,
        ),
        reason=reason,
    )


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
