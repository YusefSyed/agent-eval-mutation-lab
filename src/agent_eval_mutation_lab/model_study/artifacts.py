"""Atomic content-addressed storage for exact model request/response receipts."""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


class ReceiptCorruptionError(RuntimeError):
    """Stored receipt bytes do not match their content address."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ReceiptArtifact:
    digest: str
    size: int
    relative_path: str


class ContentAddressedReceiptStore:
    """Publish immutable JSON receipts by SHA-256 with atomic replacement."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def put(self, content: bytes) -> ReceiptArtifact:
        digest = hashlib.sha256(content).hexdigest()
        relative = Path("sha256") / digest[:2] / f"{digest}.json"
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != content:
                raise ReceiptCorruptionError(
                    f"receipt {digest} exists with non-matching bytes"
                )
            return ReceiptArtifact(
                digest=digest,
                size=len(content),
                relative_path=relative.as_posix(),
            )
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{digest}.",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()
        return ReceiptArtifact(
            digest=digest,
            size=len(content),
            relative_path=relative.as_posix(),
        )

    def load(self, artifact: ReceiptArtifact) -> bytes:
        path = self.root / artifact.relative_path
        if not path.is_file():
            raise ReceiptCorruptionError(f"receipt {artifact.digest} is missing")
        content = path.read_bytes()
        actual = hashlib.sha256(content).hexdigest()
        if actual != artifact.digest or len(content) != artifact.size:
            raise ReceiptCorruptionError(
                f"receipt {artifact.digest} failed digest or size validation"
            )
        return content

    def load_digest(self, digest: str) -> bytes:
        """Load a receipt from its derivable path and verify its address."""

        if len(digest) != 64 or any(
            character not in "0123456789abcdef" for character in digest
        ):
            raise ValueError("receipt digest must be lowercase SHA-256")
        relative = Path("sha256") / digest[:2] / f"{digest}.json"
        path = self.root / relative
        if not path.is_file():
            raise ReceiptCorruptionError(f"receipt {digest} is missing")
        return self.load(
            ReceiptArtifact(
                digest=digest,
                size=path.stat().st_size,
                relative_path=relative.as_posix(),
            )
        )
