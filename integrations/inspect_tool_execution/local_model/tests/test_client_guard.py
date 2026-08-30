"""Offline HTTP tests; all requests terminate in httpx2.MockTransport memory."""

from __future__ import annotations

import asyncio
from io import StringIO

import httpx2
import pytest
from inspect_ai.model import GenerateConfig, get_model
from openai import APIStatusError
from tenacity import RetryError

import runner
from client_guard import install_client_guard


def test_preflight_rejects_a_different_server_version(monkeypatch):
    calls = []

    class Opener:
        def open(self, request, timeout):
            calls.append(request)
            return StringIO('{"version":"0.0.0"}')

    monkeypatch.setattr(runner.urllib.request, "build_opener", lambda *a: Opener())
    with pytest.raises(ValueError, match="server version"):
        runner.check_local_model()
    assert calls == ["http://127.0.0.1:11434/api/version"]


@pytest.mark.parametrize("status", [302, 500])
def test_reinitialization_keeps_one_sdk_request_no_redirect_or_retry(
    status, monkeypatch
):
    # A proxy appearing after construction must never affect a recreated client.
    monkeypatch.setenv("HTTPS_PROXY", "http://unused.invalid")
    monkeypatch.setenv("HTTP_PROXY", "http://unused.invalid")
    requests = []

    def respond(request):
        requests.append(request)
        assert str(request.url) == runner.BASE_URL + "/chat/completions"
        assert request.headers["authorization"] == "Bearer ollama"
        return httpx2.Response(
            status,
            json={"error": {"message": "offline fixture"}},
            headers={"location": "https://must-not-contact.invalid/"},
        )

    async def exercise():
        model = get_model(
            f"ollama/{runner.MODEL}",
            base_url=runner.BASE_URL,
            api_key="ollama",
            config=GenerateConfig(**runner.GENERATION),
            memoize=False,
        )
        api = model.api
        initial_http = api.http_client
        install_client_guard(
            api,
            runner.require_loopback_request,
            transport=httpx2.MockTransport(respond),
        )
        for lifecycle in ("installed", "reinitialized", "closed-and-recreated"):
            if lifecycle == "reinitialized":
                api.initialize()
            elif lifecycle == "closed-and-recreated":
                await api.aclose()
                api.initialize()
            assert api.client.max_retries == 0
            assert api.http_client.trust_env is False
            assert api.http_client.follow_redirects is False
            assert (
                api.http_client.event_hooks["request"].count(
                    runner.require_loopback_request
                )
                == 1
            )
            count = len(requests)
            with pytest.raises(APIStatusError):
                await api.client.chat.completions.create(
                    model=runner.MODEL,
                    messages=[{"role": "user", "content": "Offline HTTP fixture."}],
                )
            assert len(requests) == count + 1
        await api.aclose()
        assert initial_http.is_closed

    asyncio.run(exercise())
    assert len(requests) == 3


def test_guard_refuses_repeat_installation_and_credential_override():
    async def exercise():
        model = get_model(
            f"ollama/{runner.MODEL}",
            base_url=runner.BASE_URL,
            api_key="ollama",
            memoize=False,
        )
        api = model.api
        install_client_guard(
            api,
            runner.require_loopback_request,
            transport=httpx2.MockTransport(lambda r: httpx2.Response(500)),
        )
        with pytest.raises(ValueError, match="already installed"):
            install_client_guard(api, runner.require_loopback_request)
        api.api_key = "not-the-local-placeholder"
        with pytest.raises(ValueError, match="non-placeholder"):
            api.initialize()
        await api.aclose()

    asyncio.run(exercise())


@pytest.mark.parametrize("status", [302, 500])
def test_native_inspect_generation_makes_one_in_memory_request(status):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx2.Response(
            status,
            json={"error": {"message": "offline fixture"}},
            headers={"location": "https://must-not-contact.invalid/"},
        )

    async def exercise():
        model = get_model(
            f"ollama/{runner.MODEL}",
            base_url=runner.BASE_URL,
            api_key="ollama",
            config=GenerateConfig(**runner.GENERATION),
            memoize=False,
        )
        install_client_guard(
            model.api,
            runner.require_loopback_request,
            transport=httpx2.MockTransport(respond),
        )
        model.api.initialize()
        try:
            with pytest.raises(
                APIStatusError if status == 302 else RetryError
            ) as error:
                await model.generate(
                    "Offline HTTP transport fixture; no model is contacted."
                )
            assert len(requests) == 1
            if status == 500:
                assert error.value.last_attempt.attempt_number == 1
        finally:
            await model.api.aclose()

    asyncio.run(exercise())
