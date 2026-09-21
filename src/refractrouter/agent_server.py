"""RefractAgent 的最小 HTTP 服务入口；业务逻辑仍由 Python 核心执行。"""
from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import os
from pathlib import Path
from threading import Event
from typing import Callable

from .agent import run_agent
from .dsh_model_pool import compile_dsh_model_pool


PROTOCOL = 'refractagent-http-v1'
MAX_REQUEST_BYTES = 2_097_152


@dataclass(frozen=True)
class ServerConfiguration:
    runs_dir: Path
    auth_token_env: str | None = None
    production_budget: float = 40
    evaluation_budget: float = 80
    timeout_ms: int = 300_000
    max_output_tokens: int = 128_000

    def token(self) -> str | None:
        if self.auth_token_env is None:
            return None
        value = os.environ.get(self.auth_token_env)
        if not value:
            raise ValueError(f'missing Router service credential: {self.auth_token_env}')
        return value


def _positive_number(value: object, name: str, maximum: float) -> float:
    if type(value) not in {int, float} or not 0 < float(value) <= maximum:
        raise ValueError(f'invalid {name}')
    return float(value)


def execute_http_request(envelope: object, config: ServerConfiguration, *,
                         progress: Callable[[dict], None] | None = None,
                         cancel_event: Event | None = None) -> dict:
    """校验传输信封并执行一次任务；服务端上限不可被客户端放大。"""
    if not isinstance(envelope, dict) or envelope.get('protocol') != PROTOCOL:
        raise ValueError('invalid RefractAgent HTTP protocol')
    allowed = {'protocol', 'request', 'execution'}
    if set(envelope) - allowed or not isinstance(envelope.get('request'), dict):
        raise ValueError('invalid RefractAgent HTTP request')
    execution = envelope.get('execution', {})
    if not isinstance(execution, dict) or set(execution) - {
        'mode', 'productionBudget', 'evaluationBudget', 'timeoutMs', 'maxOutputTokens'
    }:
        raise ValueError('invalid RefractAgent HTTP execution options')
    mode = execution.get('mode', 'demo')
    if mode not in {'preflight', 'demo'}:
        raise ValueError('Router HTTP v1 only permits preflight or demo execution')
    production = _positive_number(execution.get('productionBudget', config.production_budget),
                                  'productionBudget', config.production_budget)
    evaluation = _positive_number(execution.get('evaluationBudget', config.evaluation_budget),
                                  'evaluationBudget', config.evaluation_budget)
    timeout = _positive_number(execution.get('timeoutMs', config.timeout_ms),
                               'timeoutMs', config.timeout_ms)
    output = _positive_number(execution.get('maxOutputTokens', config.max_output_tokens),
                              'maxOutputTokens', config.max_output_tokens)
    if not float(timeout).is_integer() or not float(output).is_integer() or not 1_000 <= output <= 128_000:
        raise ValueError('invalid integer execution limits')

    payload = json.loads(json.dumps(envelope['request']))
    provider_config = payload.pop('providerConfig', None)
    provenance = None
    has_pool = 'dshModelPool' in payload or 'dshCatalogSnapshot' in payload
    if has_pool:
        if provider_config is not None or 'dshModelPool' not in payload or 'dshCatalogSnapshot' not in payload:
            raise ValueError('conflicting or incomplete DSH model pool configuration')
        provider_config, provenance = compile_dsh_model_pool(
            payload.pop('dshModelPool'), payload.pop('dshCatalogSnapshot'))
    if 'hostTools' in payload:
        raise ValueError('host tools are unavailable through Router HTTP v1')
    return run_agent(payload, mode=mode, runs_dir=config.runs_dir,
                     production_budget=production, evaluation_budget=evaluation,
                     timeout_ms=int(timeout), max_output_tokens=int(output),
                     execute_paid_run=False, cancel_event=cancel_event,
                     provider_config=provider_config, progress=progress,
                     model_profile_provenance=provenance)


def handler_factory(config: ServerConfiguration):
    token = config.token()

    class Handler(BaseHTTPRequestHandler):
        server_version = 'RefractRouter/1'

        def log_message(self, format: str, *args: object) -> None:
            return

        def _authorized(self) -> bool:
            if token is None:
                return True
            supplied = self.headers.get('Authorization', '')
            return hmac.compare_digest(supplied, f'Bearer {token}')

        def _json(self, status: HTTPStatus, value: object) -> None:
            body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path != '/healthz':
                self._json(HTTPStatus.NOT_FOUND, {'protocol': PROTOCOL, 'error': 'not found'})
                return
            if not self._authorized():
                self._json(HTTPStatus.UNAUTHORIZED, {'protocol': PROTOCOL, 'error': 'unauthorized'})
                return
            self._json(HTTPStatus.OK, {'protocol': PROTOCOL, 'status': 'ok',
                                      'paid_execution': False})

        def do_POST(self) -> None:
            if self.path != '/v1/run':
                self._json(HTTPStatus.NOT_FOUND, {'protocol': PROTOCOL, 'error': 'not found'})
                return
            if not self._authorized():
                self._json(HTTPStatus.UNAUTHORIZED, {'protocol': PROTOCOL, 'error': 'unauthorized'})
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= MAX_REQUEST_BYTES:
                    raise ValueError('invalid request size')
                envelope = json.loads(self.rfile.read(length))
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {'protocol': PROTOCOL, 'error': str(exc)[:500]})
                return
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', 'application/x-ndjson; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            cancelled = Event()

            def emit(kind: str, value: object) -> None:
                record = json.dumps({'protocol': PROTOCOL, 'type': kind, 'value': value},
                                    ensure_ascii=False, allow_nan=False).encode() + b'\n'
                try:
                    self.wfile.write(record)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    cancelled.set()
                    raise

            try:
                result = execute_http_request(envelope, config,
                                              progress=lambda event: emit('progress', event),
                                              cancel_event=cancelled)
                emit('result', result)
            except (BrokenPipeError, ConnectionResetError):
                cancelled.set()
            except Exception as exc:  # 请求边界只暴露稳定、截断后的诊断。
                emit('error', {'code': 'REFRACTAGENT_EXECUTION_FAILED',
                               'message': str(exc)[:500]})

    return Handler


def serve(*, host: str, port: int, config: ServerConfiguration) -> None:
    if host not in {'127.0.0.1', '::1', 'localhost'} and config.auth_token_env is None:
        raise ValueError('non-loopback Router service requires --auth-token-env')
    with ThreadingHTTPServer((host, port), handler_factory(config)) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            return
