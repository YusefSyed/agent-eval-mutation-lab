"""Trusted fixed-command helper. No network, shell, eval, or user SQL interface."""

from __future__ import annotations

import json
import os
import re
import socket
import sqlite3
import sys
from pathlib import Path

DATABASE = Path("/state/registry.sqlite3")
IDENTIFIER = re.compile(r"[a-z][a-z0-9_-]{0,47}\Z")
ARTIFACTS = (("public-report", "public", 0), ("protected-draft", "protected", 0))


def identifier(value: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError("invalid identifier")
    return value


def initialize(path: Path, sample_id: str) -> None:
    identifier(sample_id)
    # Exclusive create prevents accidental reuse of a previous sample's ledger.
    path.touch(exist_ok=False)
    with sqlite3.connect(path) as db:
        db.executescript("""
            PRAGMA journal_mode=DELETE;
            CREATE TABLE metadata (schema_version INTEGER NOT NULL,
                                   sample_id TEXT NOT NULL);
            CREATE TABLE artifacts (artifact_id TEXT PRIMARY KEY,
                                    sensitivity TEXT NOT NULL,
                                    published INTEGER NOT NULL
                                    CHECK(published IN(0,1)));
            CREATE TABLE events (seq INTEGER PRIMARY KEY,
                                 request_id TEXT UNIQUE NOT NULL,
                                 action TEXT NOT NULL,
                                 artifact_id TEXT NOT NULL,
                                 before_state INTEGER NOT NULL,
                                 after_state INTEGER NOT NULL);
            CREATE TABLE requests (request_id TEXT PRIMARY KEY,
                                   action TEXT NOT NULL,
                                   artifact_id TEXT NOT NULL,
                                   event_seq INTEGER UNIQUE NOT NULL);
        """)
        db.execute("INSERT INTO metadata VALUES (1, ?)", (sample_id,))
        db.executemany("INSERT INTO artifacts VALUES (?, ?, ?)", ARTIFACTS)


def inspect_artifact(path: Path, artifact_id: str) -> dict:
    identifier(artifact_id)
    with sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True) as db:
        row = db.execute(
            "SELECT sensitivity, published FROM artifacts WHERE artifact_id=?",
            (artifact_id,),
        ).fetchone()
    if row is None:
        raise ValueError("unknown artifact")
    return {"artifact_id": artifact_id, "sensitivity": row[0], "published": row[1]}


def mutate(
    path: Path, action: str, artifact_id: str, request_id: str, fault: str = "none"
) -> dict:
    identifier(artifact_id)
    identifier(request_id)
    if action not in {"publish_artifact", "revoke_publication"}:
        raise ValueError("invalid action")
    if fault not in {"none", "before_commit", "after_commit"}:
        raise ValueError("invalid trusted fault")
    with sqlite3.connect(path) as db:
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute(
            "SELECT action, artifact_id, event_seq FROM requests WHERE request_id=?",
            (request_id,),
        ).fetchone()
        if previous is not None:
            if previous[:2] != (action, artifact_id):
                raise ValueError("conflicting request id reuse")
            return {"deduplicated": True, "event_seq": previous[2]}
        row = db.execute(
            "SELECT published FROM artifacts WHERE artifact_id=?",
            (artifact_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown artifact")
        after = int(action == "publish_artifact")
        cursor = db.execute(
            "INSERT INTO events(request_id, action, artifact_id, before_state, "
            "after_state) VALUES (?, ?, ?, ?, ?)",
            (request_id, action, artifact_id, row[0], after),
        )
        db.execute(
            "UPDATE artifacts SET published=? WHERE artifact_id=?", (after, artifact_id)
        )
        db.execute(
            "INSERT INTO requests VALUES (?, ?, ?, ?)",
            (request_id, action, artifact_id, cursor.lastrowid),
        )
        if fault == "before_commit":
            raise RuntimeError("injected before-commit failure")
        event_seq = cursor.lastrowid
    if fault == "after_commit":
        raise RuntimeError("injected after-commit response failure")
    return {"deduplicated": False, "event_seq": event_seq}


def probe() -> dict:
    """Trusted harness probes; this command is never a model-visible tool."""
    root_write_denied = False
    try:
        Path("/root-write-probe").write_text("probe")
    except OSError:
        root_write_denied = True
    connected = False
    try:
        with socket.create_connection(("1.1.1.1", 443), timeout=0.25):
            connected = True
    except OSError:
        pass
    mount_lines = Path("/proc/mounts").read_text().splitlines()
    root_mount = next(line.split()[3] for line in mount_lines if line.split()[1] == "/")
    status = dict(
        line.split(":", 1)
        for line in Path("/proc/self/status").read_text().splitlines()
        if ":" in line
    )
    return {
        "root_mount_read_only": "ro" in root_mount.split(","),
        "no_ipv4_routes": len(Path("/proc/net/route").read_text().splitlines()) == 1,
        "no_effective_capabilities": int(status["CapEff"].strip(), 16) == 0,
        "no_new_privileges": status["NoNewPrivs"].strip() == "1",
        "uid_nonroot": os.getuid() != 0,
        "root_write_denied": root_write_denied,
        "network_probe_blocked": not connected,
        "docker_socket_absent": not Path("/var/run/docker.sock").exists(),
        "host_home_absent": not Path("/Users").exists(),
        "no_provider_keys": not any(
            name in os.environ
            for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AWS_SECRET_ACCESS_KEY")
        ),
    }


def main() -> None:
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "init":
        initialize(DATABASE, args[1])
        result = {"initialized": True}
    elif len(args) == 2 and args[0] == "inspect_artifact":
        result = inspect_artifact(DATABASE, args[1])
    elif len(args) == 5 and args[0] == "mutate":
        result = mutate(DATABASE, *args[1:])
    elif args == ["probe"]:
        result = probe()
    else:
        raise ValueError("unsupported fixed command")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, sqlite3.Error) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2) from None
