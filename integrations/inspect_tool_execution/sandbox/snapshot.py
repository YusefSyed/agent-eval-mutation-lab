"""Harness-only consistent SQLite export; never exposed in the model tool list."""

import sqlite3
from pathlib import Path

source = Path("/state/registry.sqlite3")
target = Path("/state/evidence.sqlite3")
# Each sample exports once. Refuse an old snapshot instead of silently reusing it.
target.touch(exist_ok=False)
with sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True) as reader:
    reader.execute("PRAGMA query_only=ON")
    with sqlite3.connect(target) as writer:
        reader.backup(writer)
