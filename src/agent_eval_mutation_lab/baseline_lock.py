"""Verify frozen benchmark files against a versioned SHA-256 lock."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_lock(lock_path: Path, root: Path) -> dict[str, Any]:
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    files = payload.get("files")
    if not isinstance(files, dict):
        raise ValueError("lock.files must be an object")

    results: list[dict[str, Any]] = []
    for raw_name, raw_expected in sorted(files.items()):
        if not isinstance(raw_name, str) or not isinstance(raw_expected, str):
            raise ValueError("lock file names and hashes must be strings")
        path = root / raw_name
        actual = _sha256(path) if path.is_file() else None
        results.append(
            {
                "path": raw_name,
                "expected": raw_expected,
                "actual": actual,
                "matches": actual == raw_expected,
            }
        )
    return {
        "schema_version": 1,
        "lock": str(lock_path),
        "root": str(root),
        "verified": all(result["matches"] for result in results),
        "files": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a frozen benchmark lock.")
    parser.add_argument(
        "--lock",
        type=Path,
        default=Path("artifacts/baseline-v1/LOCK.json"),
    )
    parser.add_argument("--root", type=Path, default=Path("."))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = verify_lock(args.lock, args.root)
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["verified"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

