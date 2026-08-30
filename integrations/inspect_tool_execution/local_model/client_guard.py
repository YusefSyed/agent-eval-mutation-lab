"""Instance-scoped lifecycle guard for Inspect 0.3.260's native Ollama client."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import httpx2
from openai import DefaultAsyncHttpxClient


def install_client_guard(
    api,
    request_guard: Callable[[httpx2.Request], Awaitable[None]],
    *,
    transport: httpx2.AsyncBaseTransport | None = None,
) -> None:
    """Keep native initialization while restoring local-only transport controls.

    `transport` is used only by offline tests with an in-memory MockTransport.
    Install immediately after get_model(), before any request. No global provider
    registration, API implementation, or native generation behavior is replaced.
    """
    if getattr(api, "_local_guard_installed", False):
        raise ValueError("client guard is already installed")
    initial_http = api.http_client
    native_initialize = api.initialize
    native_aclose = api.aclose

    def secure_http_client() -> DefaultAsyncHttpxClient:
        return DefaultAsyncHttpxClient(
            trust_env=False, follow_redirects=False, transport=transport
        )

    def guarded_initialize() -> None:
        native_initialize()
        # A credential override hook must not replace the dummy local value.
        if api.api_key != "ollama" or api.client.api_key != "ollama":
            raise ValueError("non-placeholder local credential refused")
        api.client.max_retries = 0
        api.http_client.follow_redirects = False
        if api.http_client.trust_env:
            raise RuntimeError("proxy/environment HTTP transport refused")
        hooks = api.http_client.event_hooks["request"]
        if request_guard not in hooks:
            hooks.append(request_guard)
        if api.client.max_retries != 0 or api.http_client.follow_redirects:
            raise RuntimeError("local transport controls did not apply")

    async def guarded_aclose() -> None:
        try:
            await native_aclose()
        finally:
            # The initial native client was never used, but close its resources too.
            await initial_http.aclose()

    # Native initialize() also calls this factory when a client has been closed.
    api._create_http_client = secure_http_client
    api.http_client = secure_http_client()
    api.initialize = guarded_initialize
    api.aclose = guarded_aclose
    api._local_guard_installed = True
    api.initialize()
