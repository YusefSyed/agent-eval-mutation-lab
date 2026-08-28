"""Atomic content-addressed storage for canonical task records."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from agent_eval_mutation_lab.engine.canonical import (
    canonical_json_bytes,
    sha256_bytes,
    task_record_from_payload,
    task_record_payload,
)
from agent_eval_mutation_lab.engine.contracts import (
    ArtifactCorruptionError,
    StoredArtifact,
    TaskRecord,
)


class ContentAddressedStore:
    """Immutable JSON objects keyed by the SHA-256 of their exact bytes."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, digest: str) -> Path:
        if len(digest) != 64 or any(
            character not in "0123456789abcdef" for character in digest
        ):
            raise ValueError("artifact digest must be lowercase SHA-256")
        return self.root / "sha256" / digest[:2] / f"{digest}.json"

    def put_task_record(self, record: TaskRecord) -> StoredArtifact:
        content = canonical_json_bytes(task_record_payload(record))
        digest = sha256_bytes(content)
        path = self._path(digest)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if sha256_bytes(path.read_bytes()) != digest:
                raise ArtifactCorruptionError(
                    f"existing object does not match digest {digest}"
                )
        else:
            descriptor, raw_name = tempfile.mkstemp(
                prefix=f".{digest}.", suffix=".tmp", dir=path.parent
            )
            temporary = Path(raw_name)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        return StoredArtifact(
            digest=digest,
            media_type="application/json",
            size=len(content),
            relative_path=path.relative_to(self.root).as_posix(),
        )

    def load_task_record(self, artifact: StoredArtifact) -> TaskRecord:
        path = self.root / artifact.relative_path
        if not path.is_file():
            raise ArtifactCorruptionError(
                f"artifact {artifact.digest} is missing"
            )
        content = path.read_bytes()
        actual = sha256_bytes(content)
        if actual != artifact.digest or len(content) != artifact.size:
            raise ArtifactCorruptionError(
                f"artifact {artifact.digest} failed digest or size validation"
            )
        try:
            payload = json.loads(content)
            return task_record_from_payload(payload)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            raise ArtifactCorruptionError(
                f"artifact {artifact.digest} is not a valid task record"
            ) from error
