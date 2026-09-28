"""把 Codex 钩子的调用身份与 JSON 事件的结构化退出码配对。"""
from __future__ import annotations

from threading import Condition
import shlex
import time

from refractrouter.client_tool_evidence import _exit_fact


def _shell_command(item):
    if not isinstance(item, dict) or item.get('type') != 'command_execution':
        return None
    try:
        parts = shlex.split(item.get('command', ''))
    except ValueError:
        return None
    if len(parts) == 3 and parts[1] in ('-lc', '-c'):
        return parts[2]
    return None


class CodexEvidenceEvents:
    """仅在命令与输出唯一匹配时，结合两条宿主事件形成工具事实。"""

    def __init__(self):
        self.condition = Condition()
        self.hooks = {}
        self.completed = []
        self.used = set()
        self.resolved = {}

    def observe_hook(self, event):
        if (not isinstance(event, dict) or event.get('hook_event_name') != 'PostToolUse'
                or event.get('tool_name') != 'Bash'
                or not isinstance(event.get('tool_use_id'), str)
                or not isinstance(event.get('tool_input'), dict)):
            return
        call_id = event['tool_use_id']
        with self.condition:
            previous = self.hooks.get(call_id)
            if previous is not None and previous != event:
                raise ValueError('Codex 同一工具调用的钩子结果相互矛盾')
            self.hooks[call_id] = event
            self.condition.notify_all()

    def observe_json_event(self, event):
        if not isinstance(event, dict) or event.get('type') != 'item.completed':
            return
        item = event.get('item')
        command = _shell_command(item)
        if (command is None or type(item.get('exit_code')) is not int
                or not isinstance(item.get('aggregated_output'), str)
                or item.get('status') not in ('completed', 'failed')):
            return
        with self.condition:
            self.completed.append({'command': command, 'code': item['exit_code'],
                                   'output': item['aggregated_output']})
            self.condition.notify_all()

    def _matched(self, call_id):
        if call_id in self.resolved:
            return self.resolved[call_id]
        hook = self.hooks.get(call_id)
        if hook is None or not isinstance(hook.get('tool_response'), str):
            return None
        command = hook['tool_input'].get('command')
        response = hook['tool_response']
        matches = [(index, item) for index, item in enumerate(self.completed)
                   if index not in self.used and item['command'] == command
                   and item['output'] == response]
        competing = [other for other_id, other in self.hooks.items()
                     if other_id != call_id and other_id not in self.resolved
                     and other.get('tool_input', {}).get('command') == command
                     and other.get('tool_response') == response]
        if len(matches) != 1 or competing:
            return None
        index, item = matches[0]
        fact = _exit_fact(call_id, 'Bash', hook['tool_input'],
                          {'exit_code': item['code'], 'output': item['output']})
        if fact is not None:
            self.used.add(index)
            self.resolved[call_id] = fact
        return fact

    def facts_for(self, call_ids, timeout=3):
        deadline = time.monotonic() + timeout
        with self.condition:
            # 未见钩子的工具可能不受支持；不为它们额外增加等待。
            pending = {cid for cid in call_ids if cid in self.hooks}
            found = {}
            while pending:
                for cid in tuple(pending):
                    fact = self._matched(cid)
                    if fact is not None:
                        found[cid] = fact
                        pending.remove(cid)
                if not pending:
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self.condition.wait(remaining)
            return list(found.values())
