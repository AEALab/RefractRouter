"""Codex CLI 可选适配层：配对原生工具事件，再把事实附于标准模型请求。"""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
import secrets
import subprocess
import sys
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .evidence_events import CodexEvidenceEvents


def _call_ids(request):
    return [item['call_id'] for item in request.get('input', [])
            if isinstance(item, dict) and item.get('type') == 'function_call_output'
            and isinstance(item.get('call_id'), str)]


def create_proxy(router_base, events, hook_secret, router_token=''):
    router_base = router_base.rstrip('/')
    if not router_base.startswith(('http://127.0.0.1:', 'http://localhost:', 'https://')):
        raise ValueError('Router 地址必须为本机或 HTTPS')
    if not router_base.endswith('/v1'):
        raise ValueError('Router 地址必须以 /v1 结束')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def _respond(self, status, data, content_type='application/json'):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _relay(self, method, data=None):
            headers = {'Content-Type':'application/json'}
            if router_token:
                headers['Authorization'] = 'Bearer ' + router_token
            upstream = Request(router_base + self.path.removeprefix('/v1'),
                               data, headers, method=method)
            try:
                response = urlopen(upstream, timeout=180)
            except HTTPError as error:
                self._respond(error.code, error.read())
                return
            with response:
                kind = response.headers.get('Content-Type', 'application/json')
                self.send_response(response.status)
                self.send_header('Content-Type', kind)
                self.send_header('Connection', 'close')
                self.end_headers()
                self.close_connection = True
                while chunk := response.read1(65536):
                    self.wfile.write(chunk)
                    self.wfile.flush()

        def do_GET(self):
            if self.path != '/v1/models':
                self._respond(404, b'{}')
                return
            self._relay('GET')

        def do_POST(self):
            size = int(self.headers.get('Content-Length', '0'))
            if size < 1 or size > 8 * 1024 * 1024:
                self._respond(413, b'{}')
                return
            raw = self.rfile.read(size)
            if self.path == '/hook':
                if self.headers.get('Authorization') != 'Bearer ' + hook_secret:
                    self._respond(401, b'{}')
                    return
                try:
                    events.observe_hook(json.loads(raw))
                    self._respond(200, b'{"accepted":true}')
                except (ValueError, KeyError):
                    self._respond(400, b'{}')
                return
            if self.path not in ('/v1/responses', '/v1/chat/completions'):
                self._respond(404, b'{}')
                return
            try:
                request = json.loads(raw)
                if self.path == '/v1/responses':
                    metadata = request.setdefault('metadata', {})
                    if not isinstance(metadata, dict):
                        raise ValueError('metadata 必须为对象')
                    metadata['refract_tool_evidence_policy'] = 'confirmed'
                    raw = json.dumps(request, ensure_ascii=False).encode()
                    facts = events.facts_for(_call_ids(request))
                    # 事实通过同一 Router 的专用入口保存，由核心负责历史配对。
                    for fact in facts:
                        headers = {'Content-Type':'application/json'}
                        if router_token:
                            headers['Authorization'] = 'Bearer ' + router_token
                        receipt = Request(router_base + '/tool-evidence',
                            json.dumps(fact, ensure_ascii=False).encode(), headers, method='POST')
                        with urlopen(receipt, timeout=3):
                            pass
                self._relay('POST', raw)
            except (ValueError, HTTPError) as error:
                self._respond(400, json.dumps({'error':{'message':str(error)}}).encode())

    return ThreadingHTTPServer(('127.0.0.1', 0), Handler)


def run(router_base, codex_args, *, provider='refract', router_token='', diagnostics=None,
        hook_command=None):
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', provider):
        raise ValueError('Codex provider 名称无效')
    events = CodexEvidenceEvents()
    hook_secret = secrets.token_urlsafe(32)
    proxy = create_proxy(router_base, events, hook_secret, router_token)
    worker = Thread(target=proxy.serve_forever, daemon=True)
    worker.start()
    base = f'http://127.0.0.1:{proxy.server_port}'
    args = ['codex', 'exec', '--json', '-c',
            'model_providers.' + provider + '.base_url=' + json.dumps(base + '/v1'),
            *codex_args]
    if hook_command:
        # 仅供临时验收；日常使用由 Codex 自己加载并信任用户配置的钩子。
        hooks = ('hooks.PostToolUse=[{matcher="^Bash$",hooks=['
                 '{type="command",command=' + json.dumps(hook_command) + '}]}]')
        args[3:3] = ['-c', hooks]
    env = {**os.environ, 'REFRACTROUTER_CODEX_ADAPTER_URL':base,
           'REFRACTROUTER_CODEX_ADAPTER_TOKEN':hook_secret}
    try:
        process = subprocess.Popen(args, env=env, text=True, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, bufsize=1)
        def relay_errors():
            for line in process.stderr:
                sys.stderr.write(line)
        stderr_thread = Thread(target=relay_errors, daemon=True)
        stderr_thread.start()
        for line in process.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            try:
                events.observe_json_event(json.loads(line))
            except ValueError:
                pass
        code = process.wait()
        stderr_thread.join(timeout=1)
        if events.completed and not events.hooks:
            print('Codex 未启用 RefractRouter PostToolUse 钩子；工具结果保持无法分类。',
                  file=sys.stderr)
        elif events.hooks and len(events.resolved) < len(events.hooks):
            print('部分 Codex 工具事件无法唯一配对；这些结果保持无法分类。', file=sys.stderr)
        if diagnostics is not None:
            diagnostics.update(hookIds=list(events.hooks), completed=events.completed,
                               resolvedIds=list(events.resolved))
        return code
    finally:
        proxy.shutdown()
        proxy.server_close()


def main():
    parser = argparse.ArgumentParser(description='以工具事实适配层启动 Codex CLI')
    parser.add_argument('--router-base', required=True, help='RefractRouter 的 /v1 Base URL')
    parser.add_argument('--provider', default='refract')
    parser.add_argument('codex_args', nargs=argparse.REMAINDER)
    options = parser.parse_args()
    args = options.codex_args[1:] if options.codex_args[:1] == ['--'] else options.codex_args
    return run(options.router_base, args, provider=options.provider,
               router_token=os.environ.get('REFRACTROUTER_TOKEN', ''))


if __name__ == '__main__':
    raise SystemExit(main())
