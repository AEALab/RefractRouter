"""客户端工具钩子的最小适配；只采集宿主事实，不执行工具或选择模型。"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from urllib.request import Request, urlopen

EVIDENCE_VERSION = 'refract-tool-evidence-v1'


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def _exit_fact(call_id, name, args, result):
    if not isinstance(call_id, str) or not call_id or not isinstance(args, dict):
        return None
    if not isinstance(result, dict):
        return None
    code = result.get('exit_code', result.get('exitCode'))
    status = result.get('status')
    if code is not None and type(code) is not int:
        return None
    if code is None and status not in (
            'blocked', 'pending_approval', 'disabled', 'degraded', 'cancelled',
            'yielded_to_background'):
        return None
    if status in ('blocked', 'pending_approval', 'disabled'):
        outcome = 'denied'
    elif status in ('degraded',) or code == 124 and result.get('error'):
        outcome = 'infrastructure'
    elif status in ('cancelled', 'yielded_to_background'):
        outcome = 'unconfirmed'
    elif result.get('error'):
        outcome = 'unclassified-error'
    else:
        outcome = 'completed' if code == 0 else 'failed'
    # 同一工具、实参和真实退出状态；不扫描或信任 stdout 中的成败措辞。
    arguments = {key: value for key, value in args.items()
                 if key not in ('description', 'statusMessage')}
    return {'version': EVIDENCE_VERSION, 'callId': call_id, 'status': outcome,
            'kind': 'unknown', 'fingerprint': _hash([name, arguments,
                {'exitCode': code} if outcome == 'failed' else None])}


def from_hermes_hook(event):
    """Hermes terminal 的 JSON 包络由宿主生成，tool_call_id 对应模型调用。"""
    if not isinstance(event, dict) or event.get('tool_name') != 'terminal':
        return None
    result = event.get('result')
    try:
        result = json.loads(result) if isinstance(result, str) else result
    except ValueError:
        return None
    return _exit_fact(event.get('tool_call_id'), 'terminal', event.get('args'), result)


def from_codex_hook(event):
    """Codex 仅在 PostToolUse 提供结构化退出状态时提升工具证据。"""
    if (not isinstance(event, dict) or event.get('hook_event_name') != 'PostToolUse'
            or event.get('tool_name') != 'Bash'):
        return None
    response = event.get('tool_response')
    # model-facing 字符串可能含用户输出，绝不在其中搜索“exit code”。
    return _exit_fact(event.get('tool_use_id'), 'Bash', event.get('tool_input'), response)


def post_to_router(fact, *, base_url=None, token=None):
    if fact is None:
        return False
    base_url = base_url or os.environ.get('REFRACTROUTER_URL')
    if not base_url or not base_url.startswith(('http://127.0.0.1:', 'http://localhost:',
                                               'https://')):
        raise ValueError('工具证据接入需要本机 Router URL 或 HTTPS 地址')
    token = token if token is not None else os.environ.get('REFRACTROUTER_TOKEN', '')
    payload = json.dumps(fact, ensure_ascii=False).encode()
    req = Request(base_url.rstrip('/') + '/tool-evidence', payload,
                  {'Content-Type': 'application/json',
                   **({'Authorization': 'Bearer ' + token} if token else {})},
                  method='POST')
    with urlopen(req, timeout=3) as response:
        accepted = json.load(response)
    if accepted.get('callId') != fact['callId'] or accepted.get('accepted') is not True:
        raise ValueError('Router 未确认工具证据')
    return True


def codex_hook_main():
    event = json.load(sys.stdin)
    adapter = os.environ.get('REFRACTROUTER_CODEX_ADAPTER_URL')
    if adapter:
        secret = os.environ.get('REFRACTROUTER_CODEX_ADAPTER_TOKEN', '')
        request = Request(adapter.rstrip('/') + '/hook',
                          json.dumps(event, ensure_ascii=False).encode(),
                          {'Content-Type':'application/json', 'Authorization':'Bearer ' + secret},
                          method='POST')
        try:
            with urlopen(request, timeout=3) as response:
                return 0 if response.status == 200 else 1
        except Exception as exc:
            print('RefractRouter Codex 适配器未收到工具事件：' + str(exc), file=sys.stderr)
            return 1
    fact = from_codex_hook(event)
    if fact is None:
        return 0
    try:
        post_to_router(fact)
    except Exception as exc:
        print('RefractRouter 工具证据未送达：' + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(codex_hook_main())
