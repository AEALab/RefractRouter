from __future__ import annotations

import json
import os
import socket
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Protocol, Sequence, TextIO
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .schemas import ModelSpec


DSH_BRIDGE_PROTOCOL = "refractrouter-dsh-llm/v1"


def _progress_count(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _append_progress(path: Path | None, event: Mapping[str, object]) -> None:
    if path is None:
        return
    record = {
        "schema_version": "v0.1",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        **event,
    }
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


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


class DshBridge(Protocol):
    def complete(
        self,
        model: ModelSpec,
        messages: Sequence[Mapping[str, str]],
        *,
        json_mode: bool,
        timeout_seconds: float,
    ) -> Mapping[str, object]:
        """Execute one model request through the hosting DSH LLM service."""


class DshStdioBridge:
    """Synchronous NDJSON bridge to the parent DSH plugin process."""

    def __init__(
        self,
        reader: TextIO | None = None,
        writer: TextIO | None = None,
        progress_path: str | Path | None = None,
    ):
        self.reader = reader or sys.stdin
        self.writer = writer or sys.stdout
        configured_progress = progress_path or os.environ.get(
            "REFRACTROUTER_DSH_PROGRESS"
        )
        self.progress_path = (
            Path(configured_progress) if configured_progress is not None else None
        )
        self.request_id = 0

    def _record_progress(self, event: Mapping[str, object]) -> None:
        _append_progress(self.progress_path, event)

    def complete(
        self,
        model: ModelSpec,
        messages: Sequence[Mapping[str, str]],
        *,
        json_mode: bool,
        timeout_seconds: float,
    ) -> Mapping[str, object]:
        self.request_id += 1
        request_id = str(self.request_id)
        request = {
            "protocol": DSH_BRIDGE_PROTOCOL,
            "type": "request",
            "id": request_id,
            "provider": model.provider,
            "model": model.api_model,
            "messages": list(messages),
            "json_mode": json_mode,
            "temperature": 0,
            "max_tokens": min(model.max_output_tokens or 4096, 8192),
            "timeout_ms": max(1, round(timeout_seconds * 1000)),
            "request_options": dict(model.request_options),
        }
        self._record_progress(
            {
                "event": "request-start",
                "request_id": request_id,
                "provider": model.provider,
                "model": model.api_model,
                "timeout_ms": request["timeout_ms"],
            }
        )
        self.writer.write(json.dumps(request, ensure_ascii=False) + "\n")
        self.writer.flush()
        started = time.perf_counter()
        try:
            line = self.reader.readline()
            if not line:
                raise RuntimeError("DSH LLM bridge closed before returning a response")
            response = json.loads(line)
            if (
                not isinstance(response, dict)
                or response.get("protocol") != DSH_BRIDGE_PROTOCOL
                or response.get("type") != "response"
                or response.get("id") != request_id
            ):
                raise RuntimeError("DSH LLM bridge returned an invalid response envelope")
        except Exception as exc:
            self._record_progress(
                {
                    "event": "request-finish",
                    "request_id": request_id,
                    "provider": model.provider,
                    "model": model.api_model,
                    "ok": False,
                    "failure_type": "bridge-error",
                    "error_type": type(exc).__name__,
                    "latency_ms": round((time.perf_counter() - started) * 1000),
                }
            )
            raise
        usage = response.get("usage")
        safe_usage = usage if isinstance(usage, dict) else {}
        self._record_progress(
            {
                "event": "request-finish",
                "request_id": request_id,
                "provider": model.provider,
                "model": model.api_model,
                "ok": response.get("ok") is True,
                "failure_type": response.get("failure_type"),
                "latency_ms": round((time.perf_counter() - started) * 1000),
                "usage": {
                    "input_tokens": _progress_count(
                        safe_usage.get("input_tokens", 0)
                    ),
                    "output_tokens": _progress_count(
                        safe_usage.get("output_tokens", 0)
                    ),
                    "cached_input_tokens": _progress_count(
                        safe_usage.get("cached_input_tokens", 0)
                    ),
                    "reasoning_tokens": _progress_count(
                        safe_usage.get("reasoning_tokens", 0)
                    ),
                },
            }
        )
        return response


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
        dsh_bridge: DshBridge | None = None,
    ):
        self.transport = transport or UrllibTransport()
        self.environment = environment if environment is not None else os.environ
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.sleep = sleep
        configured_progress = self.environment.get("REFRACTROUTER_MODEL_PROGRESS")
        self.progress_path = (
            Path(configured_progress) if configured_progress is not None else None
        )
        self.progress_request_id = 0
        self.dsh_bridge = dsh_bridge
        if self.dsh_bridge is None and self.environment.get("REFRACTROUTER_DSH_BRIDGE") == "stdio":
            self.dsh_bridge = DshStdioBridge()

    def complete(
        self,
        model: ModelSpec,
        messages: Sequence[Mapping[str, str]],
        *,
        json_mode: bool = False,
    ) -> ChatResponse:
        if model.wire_api == "dsh-llm":
            return self._complete_dsh(model, messages, json_mode=json_mode)
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
        self.progress_request_id += 1
        progress_request_id = str(self.progress_request_id)
        endpoint = f"{model.base_url}/chat/completions"
        _append_progress(
            self.progress_path,
            {
                "event": "request-start",
                "request_id": progress_request_id,
                "provider": model.provider,
                "model": model.api_model,
                "endpoint": endpoint,
                "timeout_ms": round(self.timeout_seconds * 1000),
            },
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
                    endpoint,
                    headers,
                    body,
                    self.timeout_seconds,
                )
                if 200 <= response.status < 300:
                    try:
                        parsed = self._parse_response(response, attempts, started)
                    except ModelInvocationError as exc:
                        _append_progress(
                            self.progress_path,
                            {
                                "event": "request-finish",
                                "request_id": progress_request_id,
                                "provider": model.provider,
                                "model": model.api_model,
                                "ok": False,
                                "failure_type": exc.failure_type,
                                "latency_ms": exc.latency_ms,
                                "attempts": attempts,
                            },
                        )
                        raise
                    _append_progress(
                        self.progress_path,
                        {
                            "event": "request-finish",
                            "request_id": progress_request_id,
                            "provider": model.provider,
                            "model": model.api_model,
                            "ok": True,
                            "latency_ms": parsed.latency_ms,
                            "attempts": attempts,
                            "provider_request_id": parsed.request_id,
                            "finish_reason": parsed.finish_reason,
                            "usage": {
                                "input_tokens": parsed.input_tokens,
                                "output_tokens": parsed.output_tokens,
                                "cached_input_tokens": parsed.cached_input_tokens,
                                "reasoning_tokens": parsed.reasoning_tokens,
                            },
                        },
                    )
                    return parsed
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
        _append_progress(
            self.progress_path,
            {
                "event": "request-finish",
                "request_id": progress_request_id,
                "provider": model.provider,
                "model": model.api_model,
                "ok": False,
                "failure_type": last_failure,
                "latency_ms": latency_ms,
                "attempts": attempts,
            },
        )
        raise ModelInvocationError(last_failure, last_message, attempts, latency_ms)

    def _complete_dsh(
        self,
        model: ModelSpec,
        messages: Sequence[Mapping[str, str]],
        *,
        json_mode: bool,
    ) -> ChatResponse:
        if self.dsh_bridge is None:
            raise ModelInvocationError(
                "missing-dsh-bridge",
                "dsh-llm models must run through the RefractRouter DSH plugin",
                0,
                0,
            )
        started = time.perf_counter()
        attempts = 0
        last_failure = "transport-error"
        last_message = "DSH LLM request failed"
        while attempts <= self.max_retries:
            attempts += 1
            try:
                response = self.dsh_bridge.complete(
                    model,
                    messages,
                    json_mode=json_mode,
                    timeout_seconds=self.timeout_seconds,
                )
                if response.get("ok") is True:
                    usage = response.get("usage", {})
                    if not isinstance(usage, dict):
                        raise TypeError("usage must be an object")
                    return ChatResponse(
                        content=str(response.get("content", "")),
                        input_tokens=int(usage.get("input_tokens", 0)),
                        output_tokens=int(usage.get("output_tokens", 0)),
                        cached_input_tokens=int(usage.get("cached_input_tokens", 0)),
                        reasoning_tokens=int(usage.get("reasoning_tokens", 0)),
                        latency_ms=round((time.perf_counter() - started) * 1000),
                        attempts=attempts,
                        finish_reason=(
                            str(response["finish_reason"])
                            if response.get("finish_reason") is not None
                            else None
                        ),
                        request_id=(
                            str(response["request_id"])
                            if response.get("request_id") is not None
                            else None
                        ),
                    )
                last_failure = str(response.get("failure_type", "provider-error"))
                last_message = str(response.get("message", "DSH LLM request failed"))[:300]
            except (RuntimeError, ValueError, TypeError, json.JSONDecodeError) as exc:
                last_failure = "transport-error"
                last_message = f"DSH LLM bridge failure: {type(exc).__name__}"
            if attempts <= self.max_retries and last_failure in {
                "rate-limit",
                "timeout",
                "provider-error",
                "transport-error",
            }:
                self.sleep(min(2 ** (attempts - 1), 4))
                continue
            break
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
        model.cached_input_cost_per_1k
        if model.cached_input_cost_per_1k is not None
        else model.input_cost_per_1k
    )
    return round(
        uncached_tokens / 1000 * model.input_cost_per_1k
        + cached_tokens / 1000 * cached_rate
        + response.output_tokens / 1000 * model.output_cost_per_1k,
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
