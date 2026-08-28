"""Dependency-free Ollama transport for the optional live model study."""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from agent_eval_mutation_lab.model_study.contracts import (
    LicenseEvidence,
    ModelConfig,
    ModelIdentity,
)


class OllamaTransportError(RuntimeError):
    """A request failed before a complete Ollama response was received."""


class OllamaTimeoutError(OllamaTransportError):
    """A request exceeded its declared transport deadline."""


class HTTPTransport(Protocol):
    def request(
        self,
        *,
        method: str,
        url: str,
        body: bytes | None,
        timeout_seconds: float,
    ) -> bytes: ...


class UrllibTransport:
    """Small injectable transport; live I/O is never required by package tests."""

    def request(
        self,
        *,
        method: str,
        url: str,
        body: bytes | None,
        timeout_seconds: float,
    ) -> bytes:
        request = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                content = response.read()
                if not isinstance(content, bytes):
                    raise OllamaTransportError("Ollama response was not bytes")
                return content
        except TimeoutError as error:
            raise OllamaTimeoutError("Ollama request timed out") from error
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as error:
            raise OllamaTransportError("Ollama request failed") from error


@dataclass(frozen=True, slots=True, kw_only=True)
class OllamaChatReceipt:
    """Exact request/response bytes plus bounded operational counters."""

    request_bytes: bytes
    response_bytes: bytes
    response_content: str
    prompt_tokens: int | None
    completion_tokens: int | None
    total_duration_ns: int | None


class OllamaClient:
    """Native `/api` client with explicit schema, decoding, and timeout inputs."""

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:11434",
        transport: HTTPTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._transport = transport or UrllibTransport()

    def version(self, *, timeout_seconds: float = 5.0) -> str:
        payload = _json_object(
            self._transport.request(
                method="GET",
                url=f"{self._base_url}/api/version",
                body=None,
                timeout_seconds=timeout_seconds,
            ),
            "version response",
        )
        version = payload.get("version")
        if not isinstance(version, str) or not version:
            raise ValueError("Ollama version response is missing version")
        return version

    def show(self, tag: str, *, timeout_seconds: float = 10.0) -> dict[str, object]:
        return _json_object(
            self._transport.request(
                method="POST",
                url=f"{self._base_url}/api/show",
                body=_canonical_json({"model": tag}),
                timeout_seconds=timeout_seconds,
            ),
            "show response",
        )

    def chat(
        self,
        *,
        tag: str,
        system_prompt: str,
        model_input: Mapping[str, object],
        response_schema: dict[str, object],
        config: ModelConfig,
        seed: int,
        timeout_seconds: float,
    ) -> OllamaChatReceipt:
        request_bytes = build_chat_request(
            tag=tag,
            system_prompt=system_prompt,
            model_input=model_input,
            response_schema=response_schema,
            config=config,
            seed=seed,
        )
        return self.send_chat_request(
            request_bytes=request_bytes,
            timeout_seconds=timeout_seconds,
        )

    def send_chat_request(
        self,
        *,
        request_bytes: bytes,
        timeout_seconds: float,
    ) -> OllamaChatReceipt:
        """Send already-frozen request bytes and preserve the exact response."""

        response_bytes = self._transport.request(
            method="POST",
            url=f"{self._base_url}/api/chat",
            body=request_bytes,
            timeout_seconds=timeout_seconds,
        )
        payload = _json_object(response_bytes, "chat response")
        message = payload.get("message")
        if not isinstance(message, dict):
            raise ValueError("Ollama chat response is missing message")
        content = message.get("content")
        if not isinstance(content, str):
            raise ValueError("Ollama chat response message has no text content")
        return OllamaChatReceipt(
            request_bytes=request_bytes,
            response_bytes=response_bytes,
            response_content=content,
            prompt_tokens=_optional_int(payload.get("prompt_eval_count")),
            completion_tokens=_optional_int(payload.get("eval_count")),
            total_duration_ns=_optional_int(payload.get("total_duration")),
        )


def build_chat_request(
    *,
    tag: str,
    system_prompt: str,
    model_input: Mapping[str, object],
    response_schema: dict[str, object],
    config: ModelConfig,
    seed: int,
) -> bytes:
    """Build the complete canonical request without performing I/O."""

    if seed < 0:
        raise ValueError("seed must be non-negative")
    payload = {
        "model": tag,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps(
                    model_input,
                    allow_nan=False,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            },
        ],
        "stream": config.streaming,
        "think": config.thinking,
        "format": response_schema,
        "options": {
            "temperature": config.temperature,
            "top_p": config.top_p,
            "presence_penalty": config.presence_penalty,
            "repeat_penalty": config.repeat_penalty,
            "num_ctx": config.context_tokens,
            "num_predict": config.max_output_tokens,
            "seed": seed,
        },
    }
    if config.tools_enabled:
        raise ValueError("model study protocol forbids tool use")
    return _canonical_json(payload)


def model_identity_from_show(
    *,
    tag: str,
    show_payload: dict[str, object],
    runtime_version: str,
    declared_license: str | None = None,
    license_source: str | None = None,
) -> ModelIdentity:
    """Derive a pinned model identity from Ollama's local manifest response."""

    modelfile = _string(show_payload, "modelfile")
    digest = _blob_digest(modelfile)
    details = _object(show_payload.get("details"), "details")
    model_info = _object(show_payload.get("model_info"), "model_info")
    parameter_count = model_info.get("general.parameter_count")
    if type(parameter_count) is not int or parameter_count < 1:
        raise ValueError("model_info has no positive general.parameter_count")
    quantization = details.get("quantization_level")
    if not isinstance(quantization, str) or not quantization:
        raise ValueError("details has no quantization_level")
    license_value = show_payload.get("license")
    if isinstance(license_value, str) and license_value:
        if "Apache License" not in license_value or "Version 2.0" not in license_value:
            raise ValueError("model license is not recognized as Apache-2.0")
        license_name = "Apache-2.0"
        license_evidence = LicenseEvidence.LOCAL_MANIFEST
        license_reference = "ollama:/api/show"
    else:
        if declared_license != "Apache-2.0" or not license_source:
            raise ValueError(
                "local manifest omits license; declared license and source are required"
            )
        license_name = declared_license
        license_evidence = LicenseEvidence.UPSTREAM_MODEL_CARD
        license_reference = license_source
    template = _string(show_payload, "template")
    return ModelIdentity(
        provider="ollama",
        tag=tag,
        blob_digest=digest,
        parameter_count=parameter_count,
        quantization=quantization,
        license=license_name,
        license_evidence=license_evidence,
        license_source=license_reference,
        runtime_version=runtime_version,
        template_digest=hashlib.sha256(template.encode()).hexdigest(),
    )


def _blob_digest(modelfile: str) -> str:
    for line in modelfile.splitlines():
        if not line.startswith("FROM "):
            continue
        marker = "sha256-"
        source = line.removeprefix("FROM ").strip()
        if marker not in source:
            break
        digest = source.rsplit(marker, maxsplit=1)[-1]
        if len(digest) == 64 and all(
            character in "0123456789abcdef" for character in digest
        ):
            return digest
        break
    raise ValueError("modelfile does not contain a pinned SHA-256 blob")


def _json_object(value: bytes, context: str) -> dict[str, object]:
    try:
        payload = json.loads(value)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError(f"{context} is not valid UTF-8 JSON") from error
    return _object(payload, context)


def _object(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{context} must be an object with string keys")
    return value


def _string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _optional_int(value: object) -> int | None:
    return value if type(value) is int else None


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode()
