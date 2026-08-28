from pathlib import Path

import pytest

from agent_eval_mutation_lab.model_study.artifacts import (
    ContentAddressedReceiptStore,
    ReceiptCorruptionError,
)


def test_receipts_are_content_addressed_idempotent_and_verified(
    tmp_path: Path,
) -> None:
    store = ContentAddressedReceiptStore(tmp_path)
    content = b'{"request":"exact"}\n'
    first = store.put(content)
    second = store.put(content)
    assert first == second
    assert first.relative_path.startswith("sha256/")
    assert store.load(first) == content

    path = tmp_path / first.relative_path
    path.write_bytes(b"corrupt\n")
    with pytest.raises(ReceiptCorruptionError, match="digest or size"):
        store.load(first)
    with pytest.raises(ReceiptCorruptionError, match="non-matching"):
        store.put(content)
