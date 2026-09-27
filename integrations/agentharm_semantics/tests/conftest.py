import pytest


@pytest.fixture(autouse=True)
def no_runtime_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def deny(*args: object, **kwargs: object) -> None:
        raise RuntimeError("Network is disabled in audit tests")

    monkeypatch.setattr("socket.create_connection", deny)
    monkeypatch.setattr("socket.socket.connect", deny)
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("HF_DATASETS_OFFLINE", "1")
