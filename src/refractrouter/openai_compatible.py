from __future__ import annotations

import json
import os
import socket
import time
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .schemas import ModelSpec


@dataclass(frozen=True, slots=True)
class TransportResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


class HttpTransport(Protocol):
    def post(
        self,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout_seconds: float,
    ) -> TransportResponse:
        """Send one HTTP POST request."""


class UrllibTransport:
    def post(
        self,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout_seconds: float,
    ) -> TransportResponse:
        request = Request(url, data=body, headers=dict(headers), method="POST")
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                return TransportResponse(
                    status=response.status,
                    headers=dict(response.headers.items()),
                    body=response.read(),
                )
        except HTTPError as exc:
            return TransportResponse(
                status=exc.code,
                headers=dict(exc.headers.items()) if exc.headers else {},
                body=exc.read(),
            )


@dataclass(frozen=True, slots=True)
class ChatResponse:
    content: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    reasoning_tokens: int
    latency_ms: int
    attempts: int
    finish_reason: str | None
    request_id: str | None


class ModelInvocationError(RuntimeError):
    def __init__(self, failure_type: str, message: str, attempts: int, latency_ms: int):
        super().__init__(message)
        self.failure_type = failure_type
        self.attempts = attempts
        self.latency_ms = latency_ms


class OpenAICompatibleClient:
    """Minimal non-streaming Chat Completions client with auditable retries."""

    def __init__(
        self,
        *,
        transport: HttpTransport | None = None,
        environment: Mapping[str, str] | None = None,
        timeout_seconds: float = 120.0,
        max_retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.transport = transport or UrllibTransport()
        self.environment = environment if environment is not None else os.environ
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.sleep = sleep

    def complete(
        self,
        model: ModelSpec,
        messages: Sequence[Mapping[str, str]],
        *,
        json_mode: bool = False,
    ) -> ChatResponse:
        if not model.base_url or not model.api_key_env or not model.api_model:
            raise ModelInvocationError(
                "invalid-model-config", "Model is missing API configuration", 0, 0
            )
        api_key = self.environment.get(model.api_key_env)
        if not api_key:
            raise ModelInvocationError(
                "missing-api-key",
                f"Required environment variable is not set: {model.api_key_env}",
                0,
                0,
            )
        payload: dict[str, object] = {
            "model": model.api_model,
            "messages": list(messages),
            "temperature": 0,
            "max_completion_tokens": min(model.max_output_tokens or 4096, 8192),
            **dict(model.request_options),
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "refractrouter/0.1",
        }
        started = time.perf_counter()
        attempts = 0
        last_failure = "transport-error"
        last_message = "Model request failed"
        while attempts <= self.max_retries:
            attempts += 1
            try:
                response = self.transport.post(
                    f"{model.base_url}/chat/completions",
                    headers,
                    body,
                    self.timeout_seconds,
                )
                if 200 <= response.status < 300:
                    return self._parse_response(response, attempts, started)
                last_failure = _http_failure_type(response.status)
                last_message = _safe_error_message(response.status, response.body)
                if response.status not in {408, 409, 429} and response.status < 500:
                    break
            except (TimeoutError, socket.timeout) as exc:
                last_failure = "timeout"
                last_message = type(exc).__name__
            except URLError as exc:
                last_failure = "transport-error"
                last_message = type(exc.reason).__name__
            if attempts <= self.max_retries:
                self.sleep(min(2 ** (attempts - 1), 4))
        latency_ms = round((time.perf_counter() - started) * 1000)
        raise ModelInvocationError(last_failure, last_message, attempts, latency_ms)

    @staticmethod
    def _parse_response(
        response: TransportResponse,
        attempts: int,
        started: float,
    ) -> ChatResponse:
        try:
            data = json.loads(response.body.decode("utf-8"))
            choice = data["choices"][0]
            content = _message_content(choice["message"]["content"])
            usage = data.get("usage", {})
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            latency_ms = round((time.perf_counter() - started) * 1000)
            raise ModelInvocationError(
                "invalid-response", f"Invalid Chat Completions response: {type(exc).__name__}", attempts, latency_ms
            ) from exc
        prompt_details = usage.get("prompt_tokens_details") or usage.get("input_tokens_details") or {}
        completion_details = usage.get("completion_tokens_details") or usage.get("output_tokens_details") or {}
        latency_ms = round((time.perf_counter() - started) * 1000)
        headers = {key.lower(): value for key, value in response.headers.items()}
        return ChatResponse(
            content=content,
            input_tokens=int(usage.get("prompt_tokens", usage.get("input_tokens", 0))),
            output_tokens=int(usage.get("completion_tokens", usage.get("output_tokens", 0))),
            cached_input_tokens=int(prompt_details.get("cached_tokens", 0)),
            reasoning_tokens=int(completion_details.get("reasoning_tokens", 0)),
            latency_ms=latency_ms,
            attempts=attempts,
            finish_reason=choice.get("finish_reason"),
            request_id=headers.get("x-request-id") or data.get("id"),
        )


def model_response_cost(model: ModelSpec, response: ChatResponse) -> float:
    cached_tokens = min(response.cached_input_tokens, response.input_tokens)
    uncached_tokens = response.input_tokens - cached_tokens
    cached_rate = (
        model.cached_input_cost_per_1k_usd
        if model.cached_input_cost_per_1k_usd is not None
        else model.input_cost_per_1k_usd
    )
    return round(
        uncached_tokens / 1000 * model.input_cost_per_1k_usd
        + cached_tokens / 1000 * cached_rate
        + response.output_tokens / 1000 * model.output_cost_per_1k_usd,
        8,
    )


def _message_content(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [
            str(item.get("text", ""))
            for item in value
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        return "".join(parts)
    raise TypeError("Unsupported message content")


def _http_failure_type(status: int) -> str:
    if status == 429:
        return "rate-limit"
    if status in {401, 403}:
        return "authentication"
    if status == 408:
        return "timeout"
    if status >= 500:
        return "provider-error"
    return "request-error"


def _safe_error_message(status: int, body: bytes) -> str:
    try:
        data = json.loads(body.decode("utf-8"))
        message = data.get("error", {}).get("message", "")
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        message = ""
    clean = " ".join(str(message).split())[:300]
    return f"HTTP {status}" + (f": {clean}" if clean else "")
