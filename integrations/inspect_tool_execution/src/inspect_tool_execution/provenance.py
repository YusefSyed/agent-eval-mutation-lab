"""Content identity for the standalone checkout and its execution inputs."""

from __future__ import annotations

import hashlib
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]


def source_hashes() -> dict[str, str]:
    paths = [PROJECT / name for name in ("pyproject.toml", "uv.lock", "cases.json")]
    paths += sorted((PROJECT / "src").rglob("*.py"))
    paths += [p for p in sorted((PROJECT / "sandbox").iterdir()) if p.is_file()]
    return {
        str(p.relative_to(PROJECT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in paths
    }
