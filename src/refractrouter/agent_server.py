"""RefractAgent 的最小 HTTP 服务入口；业务逻辑仍由 Python 核心执行。"""
from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import os
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Callable
from urllib.parse import parse_qs, urlsplit

from .agent import run_agent
from .dsh_model_pool import compile_dsh_model_pool
from .team_service import (
    IdempotencyConflict,
    ProjectCapacityExceeded,
    TERMINAL_STATES,
    TaskStore,
    TeamConfiguration,
    TeamMember,
)


PROTOCOL = 'refractagent-http-v1'
PROTOCOL_V2 = 'refractagent-http-v2'
MAX_REQUEST_BYTES = 2_097_152


@dataclass(frozen=True)
class ServerConfiguration:
    runs_dir: Path
    auth_token_env: str | None = None
    production_budget: float = 40
    evaluation_budget: float = 80
    timeout_ms: int = 300_000
    max_output_tokens: int = 128_000
    team: TeamConfiguration | None = None

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


def _prepare_http_request(envelope: object, config: ServerConfiguration) -> dict:
    """完整校验传输信封；不解析凭证、不调用模型。"""
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
    return {
        'payload': payload, 'mode': mode, 'runs_dir': config.runs_dir,
        'production_budget': production, 'evaluation_budget': evaluation,
        'timeout_ms': int(timeout), 'max_output_tokens': int(output),
        'provider_config': provider_config, 'model_profile_provenance': provenance,
    }


def execute_http_request(envelope: object, config: ServerConfiguration, *,
                         progress: Callable[[dict], None] | None = None,
                         cancel_event: Event | None = None) -> dict:
    """校验传输信封并执行一次任务；服务端上限不可被客户端放大。"""
    prepared = _prepare_http_request(envelope, config)
    payload = prepared.pop('payload')
    return run_agent(payload, **prepared,
                     execute_paid_run=False, cancel_event=cancel_event,
                     progress=progress)


class TeamRuntime:
    """把持久任务状态与现有零付费核心执行连接起来。"""

    def __init__(self, team: TeamConfiguration):
        self.team = team
        self.store = TaskStore(team.state_path)
        self.cancel_events: dict[str, Event] = {}
        self.lock = Lock()

    def submit(self, envelope: object, member: TeamMember,
               idempotency_key: str) -> tuple[dict, bool]:
        if not isinstance(envelope, dict) or envelope.get('protocol') != PROTOCOL_V2:
            raise ValueError('invalid RefractAgent HTTP v2 protocol')
        if set(envelope) - {'protocol', 'projectId', 'request', 'execution'}:
            raise ValueError('invalid RefractAgent HTTP v2 request')
        project_id = envelope.get('projectId')
        if not isinstance(project_id, str) or project_id not in member.projects:
            raise PermissionError('project access denied')
        project = self.team.projects.get(project_id)
        if project is None:
            raise PermissionError('project access denied')
        legacy = {
            'protocol': PROTOCOL,
            'request': envelope.get('request'),
            'execution': envelope.get('execution', {}),
        }
        project_config = ServerConfiguration(
            project.runs_dir,
            production_budget=project.production_budget,
            evaluation_budget=project.evaluation_budget,
            timeout_ms=project.timeout_ms,
            max_output_tokens=project.max_output_tokens,
        )
        try:
            _prepare_http_request(legacy, project_config)
        except ValueError as exc:
            raise ValueError(str(exc).replace('HTTP v1', 'HTTP v2')) from exc
        task, reused = self.store.submit(member_id=member.id, project=project,
                                         idempotency_key=idempotency_key, envelope=envelope)
        if not reused:
            Thread(target=self._run, args=(task['taskId'], project_id), daemon=True).start()
        return task, reused

    def _run(self, task_id: str, project_id: str) -> None:
        cancelled = Event()
        with self.lock:
            self.cancel_events[task_id] = cancelled
        try:
            if not self.store.claim(task_id):
                if self.store.get(task_id)['status'] == 'cancel_requested':
                    self.store.finish(task_id, 'cancelled')
                return
            project = self.team.projects[project_id]
            source = self.store.envelope(task_id)
            legacy = {'protocol': PROTOCOL, 'request': source['request'],
                      'execution': source.get('execution', {})}
            config = ServerConfiguration(
                project.runs_dir,
                production_budget=project.production_budget,
                evaluation_budget=project.evaluation_budget,
                timeout_ms=project.timeout_ms,
                max_output_tokens=project.max_output_tokens,
            )
            result = execute_http_request(
                legacy, config,
                progress=lambda event: self.store.append_event(task_id, 'progress', event),
                cancel_event=cancelled,
            )
            self.store.finish(task_id, 'completed', result=result)
        except Exception as exc:
            self.store.finish(task_id, 'failed', error={
                'code': 'REFRACTAGENT_EXECUTION_FAILED', 'message': str(exc)[:500],
            })
        finally:
            with self.lock:
                self.cancel_events.pop(task_id, None)

    def cancel(self, task_id: str) -> dict:
        task = self.store.request_cancel(task_id)
        with self.lock:
            event = self.cancel_events.get(task_id)
        if event is not None:
            event.set()
        elif task['status'] == 'cancel_requested':
            task = self.store.finish(task_id, 'cancelled')
        return task


def handler_factory(config: ServerConfiguration):
    token = config.token()
    team_runtime = TeamRuntime(config.team) if config.team is not None else None

    class Handler(BaseHTTPRequestHandler):
        server_version = 'RefractRouter/1'

        def log_message(self, format: str, *args: object) -> None:
            return

        def _authorized(self) -> bool:
            if token is None and config.team is None:
                return True
            supplied = self.headers.get('Authorization', '')
            return ((token is not None and hmac.compare_digest(supplied, f'Bearer {token}'))
                    or self._member() is not None)

        def _member(self) -> TeamMember | None:
            if config.team is None:
                return None
            return config.team.authenticate(self.headers.get('Authorization', ''))

        def _json(self, status: HTTPStatus, value: object) -> None:
            body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            parsed = urlsplit(self.path)
            if parsed.path == '/healthz':
                if not self._authorized():
                    self._json(HTTPStatus.UNAUTHORIZED, {'protocol': PROTOCOL, 'error': 'unauthorized'})
                    return
                value = {'protocol': PROTOCOL, 'status': 'ok', 'paid_execution': False}
                if team_runtime is not None:
                    value['protocols'] = [PROTOCOL, PROTOCOL_V2]
                self._json(HTTPStatus.OK, value)
                return
            if not parsed.path.startswith('/v2/') or team_runtime is None:
                self._json(HTTPStatus.NOT_FOUND, {'protocol': PROTOCOL, 'error': 'not found'})
                return
            member = self._member()
            if member is None:
                self._json(HTTPStatus.UNAUTHORIZED, {'protocol': PROTOCOL_V2, 'error': 'unauthorized'})
                return
            if parsed.path == '/v2/projects':
                self._json(HTTPStatus.OK, {'protocol': PROTOCOL_V2, 'projects': [{
                    'id': project_id,
                    'maxConcurrentTasks': config.team.projects[project_id].max_concurrent_tasks,
                } for project_id in member.projects]})
                return
            if parsed.path == '/v2/tasks':
                query = parse_qs(parsed.query)
                try:
                    limit = int(query.get('limit', ['50'])[0])
                    if not 1 <= limit <= 100:
                        raise ValueError
                except ValueError:
                    self._json(HTTPStatus.BAD_REQUEST, {'protocol': PROTOCOL_V2, 'error': 'invalid limit'})
                    return
                requested = query.get('projectId', [])
                projects = tuple(requested) if requested else member.projects
                if any(project not in member.projects for project in projects):
                    self._json(HTTPStatus.FORBIDDEN, {'protocol': PROTOCOL_V2, 'error': 'project access denied'})
                    return
                tasks = team_runtime.store.list(
                    project_ids=projects,
                    member_id=None if member.role == 'maintainer' else member.id,
                    limit=limit, before=query.get('before', [None])[0],
                )
                self._json(HTTPStatus.OK, {'protocol': PROTOCOL_V2, 'tasks': tasks})
                return
            parts = parsed.path.strip('/').split('/')
            if len(parts) not in {3, 4} or parts[:2] != ['v2', 'tasks']:
                self._json(HTTPStatus.NOT_FOUND, {'protocol': PROTOCOL_V2, 'error': 'not found'})
                return
            task_id = parts[2]
            try:
                task = team_runtime.store.get(task_id)
            except KeyError:
                self._json(HTTPStatus.NOT_FOUND, {'protocol': PROTOCOL_V2, 'error': 'task not found'})
                return
            if task['projectId'] not in member.projects or (
                member.role != 'maintainer' and task['memberId'] != member.id
            ):
                self._json(HTTPStatus.FORBIDDEN, {'protocol': PROTOCOL_V2, 'error': 'task access denied'})
                return
            if len(parts) == 3:
                self._json(HTTPStatus.OK, {'protocol': PROTOCOL_V2, **task})
                return
            if parts[3] != 'events':
                self._json(HTTPStatus.NOT_FOUND, {'protocol': PROTOCOL_V2, 'error': 'not found'})
                return
            query = parse_qs(parsed.query)
            try:
                after = int(query.get('after', ['0'])[0])
                if after < 0:
                    raise ValueError
            except ValueError:
                self._json(HTTPStatus.BAD_REQUEST, {'protocol': PROTOCOL_V2, 'error': 'invalid event cursor'})
                return
            follow = query.get('follow', ['false'])[0].lower() == 'true'
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', 'application/x-ndjson; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            try:
                while True:
                    events = team_runtime.store.events(task_id, after)
                    for event in events:
                        record = json.dumps({'protocol': PROTOCOL_V2, 'taskId': task_id, **event},
                                            ensure_ascii=False, allow_nan=False).encode() + b'\n'
                        self.wfile.write(record)
                        self.wfile.flush()
                        after = event['sequence']
                    task = team_runtime.store.get(task_id)
                    if not follow or task['status'] in TERMINAL_STATES:
                        return
                    with team_runtime.store.changed:
                        team_runtime.store.changed.wait(timeout=1)
            except (BrokenPipeError, ConnectionResetError):
                return

        def do_POST(self) -> None:
            parsed = urlsplit(self.path)
            if parsed.path == '/v1/run':
                if not self._authorized():
                    self._json(HTTPStatus.UNAUTHORIZED, {'protocol': PROTOCOL, 'error': 'unauthorized'})
                    return
                self._run_v1()
                return
            if not parsed.path.startswith('/v2/') or team_runtime is None:
                self._json(HTTPStatus.NOT_FOUND, {'protocol': PROTOCOL, 'error': 'not found'})
                return
            member = self._member()
            if member is None:
                self._json(HTTPStatus.UNAUTHORIZED, {'protocol': PROTOCOL_V2, 'error': 'unauthorized'})
                return
            if parsed.path == '/v2/tasks':
                key = self.headers.get('Idempotency-Key', '')
                try:
                    envelope = self._read_json()
                    task, reused = team_runtime.submit(envelope, member, key)
                except PermissionError as exc:
                    self._json(HTTPStatus.FORBIDDEN, {'protocol': PROTOCOL_V2, 'error': str(exc)})
                    return
                except IdempotencyConflict as exc:
                    self._json(HTTPStatus.CONFLICT, {'protocol': PROTOCOL_V2, 'error': str(exc)})
                    return
                except ProjectCapacityExceeded as exc:
                    self._json(HTTPStatus.TOO_MANY_REQUESTS, {'protocol': PROTOCOL_V2, 'error': str(exc)})
                    return
                except (ValueError, json.JSONDecodeError) as exc:
                    self._json(HTTPStatus.BAD_REQUEST, {'protocol': PROTOCOL_V2, 'error': str(exc)[:500]})
                    return
                self._json(HTTPStatus.OK if reused else HTTPStatus.ACCEPTED,
                           {'protocol': PROTOCOL_V2, 'reused': reused, **task})
                return
            parts = parsed.path.strip('/').split('/')
            if len(parts) != 4 or parts[:2] != ['v2', 'tasks'] or parts[3] != 'cancel':
                self._json(HTTPStatus.NOT_FOUND, {'protocol': PROTOCOL_V2, 'error': 'not found'})
                return
            try:
                task = team_runtime.store.get(parts[2])
            except KeyError:
                self._json(HTTPStatus.NOT_FOUND, {'protocol': PROTOCOL_V2, 'error': 'task not found'})
                return
            if task['projectId'] not in member.projects or (
                member.role != 'maintainer' and task['memberId'] != member.id
            ):
                self._json(HTTPStatus.FORBIDDEN, {'protocol': PROTOCOL_V2, 'error': 'task access denied'})
                return
            task = team_runtime.cancel(parts[2])
            self._json(HTTPStatus.ACCEPTED, {'protocol': PROTOCOL_V2, **task})

        def _read_json(self) -> object:
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= MAX_REQUEST_BYTES:
                    raise ValueError('invalid request size')
                return json.loads(self.rfile.read(length))
            except UnicodeDecodeError as exc:
                raise ValueError('invalid request encoding') from exc

        def _run_v1(self) -> None:
            try:
                envelope = self._read_json()
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
    if (host not in {'127.0.0.1', '::1', 'localhost'}
            and config.auth_token_env is None and config.team is None):
        raise ValueError('non-loopback Router service requires --auth-token-env or --service-config')
    with ThreadingHTTPServer((host, port), handler_factory(config)) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            return
