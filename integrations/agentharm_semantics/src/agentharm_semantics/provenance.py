"""Bind observations to the inspected benchmark source."""

import hashlib
import importlib.metadata
import json
import platform
from importlib.resources import files
from pathlib import Path
from typing import Any

import inspect_ai
from inspect_evals.agentharm.benchmark import grading_utils


def verify_upstream() -> dict[str, Any]:
    expected = json.loads(
        files("agentharm_semantics").joinpath("upstream.json").read_text()
    )
    package = Path(grading_utils.__file__).resolve().parents[2]
    actual = {
        name: hashlib.sha256((package / name).read_bytes()).hexdigest()
        for name in expected["files"]
    }
    if actual != expected["files"]:
        raise ValueError(
            "Upstream source changed; review the contract before updating pins"
        )
    inspect_package = Path(inspect_ai.__file__).resolve().parent
    actual_inspect = {
        name: hashlib.sha256((inspect_package / name).read_bytes()).hexdigest()
        for name in expected["inspect_ai_files"]
    }
    if actual_inspect != expected["inspect_ai_files"]:
        raise ValueError("Inspect core source changed; review the audit contract")
    lockfile = Path(__file__).resolve().parents[2] / "uv.lock"
    if not lockfile.is_file():
        raise ValueError("Audit lockfile missing; run from the synced source checkout")
    if (
        hashlib.sha256(lockfile.read_bytes()).hexdigest()
        != expected["audit_lock_sha256"]
    ):
        raise ValueError("Audit lockfile changed; review dependencies and provenance")
    return dict(expected)


def runtime_environment() -> dict[str, str]:
    """Return operational versions separately from the canonical observations."""
    return {
        "python": platform.python_version(),
        "inspect_ai_version": importlib.metadata.version("inspect_ai"),
        "inspect_evals_version": importlib.metadata.version("inspect_evals"),
    }
