"""复现 #178：工具约束不能由猜对答案、模型自述或宽松 Judge 代替。"""
from copy import deepcopy
import json

import pytest

from refractrouter.task_tool_evidence import collect_tool_evidence, tool_requirements, MAX_EVIDENCE_BYTES
from refractrouter.task_runtime import run_task, _shared_judge_forecast
from refractrouter.task_evaluation import evaluation_messages
from refractrouter.task_budget import request_input_bound
from refractrouter.task_plan import preview_plan
from refractrouter.tool_runtime import StdioToolRuntime
from tests.test_text_tasks import MANIFEST, PROFILE, REQUEST
from tests.test_native_tool_runtime import Host, call, reply

TASK = '有限验收：请先使用 Bash 工具执行 printf 7，再只根据工具标准输出回答数字。不要编辑文件或调用其他工具。'
SCHEMAS = [{'name': 'bash', 'description': '宿主命令工具', 'parameters': {'type': 'object'}},
           {'name': 'read', 'description': '宿主读文件工具', 'parameters': {'type': 'object'}}]


@pytest.mark.parametrize('task, expected', [
    (TASK, {'required': True, 'tools': ['bash']}),
    ('Use the Bash tool to run printf 7.', {'required': True, 'tools': ['bash']}),
    ('调用工具后再回答', {'required': True, 'tools': []}),
    ('请分别使用 Bash 读取这两个文件', {'required': True, 'tools': ['bash']}),
    ('不要使用 Bash，只回答 7', {'required': False, 'tools': []}),
    ('计算 18 + 24，只回答结果数字。不调用工具。', {'required': False, 'tools': []}),
    ('不使用 Bash，只回答数字', {'required': False, 'tools': []}),
    ('不运行测试。请使用 Bash 读取文件', {'required': True, 'tools': ['bash']}),
    ('可以使用 Bash，但不要求', {'required': False, 'tools': []}),
    ('解释「使用 Bash 工具」的意思', {'required': False, 'tools': []}),
    ('Explain how to use Bash.', {'required': False, 'tools': []}),
    ('示例：```使用 Bash 工具```。只回答数字', {'required': False, 'tools': []}),
    ('如果需要，再使用 Bash', {'required': False, 'tools': []}),
])
def test_explicit_requirement_is_not_tool_availability_or_quoted_material(task, expected):
    assert tool_requirements(task, SCHEMAS) == expected


def record(*, status='completed', error=False, host=None, code=None, name='bash'):
    return {'node': 'answer', 'call': call(name, args='{"command":"printf 7"}'), 'status': status,
            'result': {'isError': error, 'content': [{'type': 'text', 'text': '7'}],
                       **({'hostResult': host} if host else {}), **({'error': {'code': code}} if code else {})}}


@pytest.mark.parametrize('row, outcome, passed', [
    (record(host={'exitCode': 0}), 'completed', True),
    (record(host={'exitCode': 1}), 'task-failed', True),
    (record(), 'returned', True),
    (record(error=True, code='PERMISSION_DENIED'), 'denied', False),
    (record(error=True, code='TRANSPORT'), 'infrastructure-error', False),
    (record(error=True), 'unclassified-error', False),
    (record(status='execution-unconfirmed'), 'unconfirmed', False),
    (record(host={'exitCode': 0, 'aborted': True}), 'unconfirmed', False),
    (record(status='cancelled-before-dispatch'), 'not-dispatched', False),
    (record(name='read'), 'returned', False),
])
def test_only_current_host_receipt_counts_and_failure_is_not_success(row, outcome, passed):
    evidence, validation = collect_tool_evidence(tool_requirements(TASK, SCHEMAS), [row], available=True)
    assert evidence['records'][0]['outcome'] == outcome
    assert validation['passed'] is passed
    assert 'content' not in validation['records'][0]  # 对外审计不复制敏感原文。


class CandidateClient:
    max_retries = 0
    def __init__(self, tool=None, answer='7'):
        self.tool, self.answer, self.calls = tool, answer, []

    def complete(self, model, messages, **kwargs):
        self.calls.append((model, deepcopy(messages), kwargs))
        if model.role == 'judge':
            criteria = json.loads(messages[-1]['content'])['criteria']
            return reply(json.dumps({'score': 100, 'passed': True, 'rationale': '故意宽松的模拟评审',
                'criteria': [{'criterion': c, 'passed': True, 'rationale': '通过'} for c in criteria]}))
        if self.tool and not any(m['role'] == 'tool' for m in messages):
            return reply(calls=[call(self.tool, args='{"command":"printf 7"}')])
        return reply(self.answer)


def run(client, runtime, **extra):
    plan = preview_plan(TASK).to_dict()
    return run_task({**REQUEST, 'task': TASK, 'plan': plan}, MANIFEST, {**PROFILE, 'kind': 'empirical'},
                    client=client, production_limit=100, evaluation_limit=100, tool_runtime=runtime, **extra)


@pytest.mark.parametrize('answer', ['7', '我已经调用 Bash，结果是 7'])
def test_correct_guess_cannot_pass_even_if_judge_would_approve(answer):
    client, host = CandidateClient(answer=answer), Host()
    result = run(client, StdioToolRuntime(SCHEMAS, host))
    assert result['status'] == 'tool-requirement-failed'
    assert result['final_output'] == answer
    assert result['evaluation'] is None and result['charged']['evaluation'] == 0
    assert result['review']['status'] == 'blocked-tool-evidence'
    assert not host.calls and len(client.calls) == 1


def test_real_tool_receipt_and_arguments_reach_judge_without_repeating_tool():
    host = Host({'isError': False, 'content': [{'type': 'text', 'text': '7'}], 'hostResult': {'exitCode': 0}})
    client = CandidateClient('bash')
    result = run(client, StdioToolRuntime(SCHEMAS, host))
    assert result['status'] == 'completed', result['issues']
    assert len(host.calls) == 1 and len(client.calls) == 3
    judged = json.loads(client.calls[-1][1][-1]['content'])
    assert judged['tool_evidence']['records'][0]['arguments'] == '{"command":"printf 7"}'
    assert judged['tool_evidence']['records'][0]['outcome'] == 'completed'
    assert not client.calls[-1][2].get('tools')


def test_denial_is_honest_incomplete_and_is_not_retried():
    host = Host({'isError': True, 'content': [{'type': 'text', 'text': '禁止执行'}],
                 'error': {'code': 'PERMISSION_DENIED'}})
    result = run(CandidateClient('bash', '权限被拒绝，无法获取结果。'), StdioToolRuntime(SCHEMAS, host))
    assert result['status'] == 'tool-requirement-failed'
    assert result['tool_validation']['records'][0]['outcome'] == 'denied'
    assert len(host.calls) == 1 and result['charged']['evaluation'] == 0


def test_missing_tool_runtime_and_skipped_review_cannot_bypass_gate():
    result = run(CandidateClient(), None, review_evidence={'required': False})
    assert result['status'] == 'tool-requirement-failed'
    assert result['evaluation'] is None


def test_old_task_receipt_does_not_satisfy_new_task():
    runtime = StdioToolRuntime(SCHEMAS, Host())
    runtime.execute(call('bash', id='previous-task'), 'answer')
    result = run(CandidateClient(), runtime)
    assert result['status'] == 'tool-requirement-failed'
    assert result['tool_validation']['records'] == []


def test_evidence_is_bounded_without_silent_truncation_and_forecast_covers_nested_json():
    evidence, summary = collect_tool_evidence(tool_requirements(TASK), [record()], available=True)
    before = request_input_bound(evaluation_messages(TASK, '7', []))
    after = request_input_bound(evaluation_messages(TASK, '7', [], tool_evidence=evidence))
    assert after - before <= summary['evidence_bytes'] <= MAX_EVIDENCE_BYTES
    judge = MANIFEST.judge
    models = {m.model_id: m for m in MANIFEST.candidates}
    difference = (_shared_judge_forecast(judge, TASK, [], models, tool_evidence=True)
                  - _shared_judge_forecast(judge, TASK, [], models))
    assert difference == pytest.approx(MAX_EVIDENCE_BYTES * judge.input_cost_per_1k / 1000)
    large = record()
    large['result']['content'][0]['text'] = '"\\' * MAX_EVIDENCE_BYTES
    complete, summary = collect_tool_evidence(tool_requirements(TASK), [large], available=True)
    assert summary['passed'] is False and summary['reason'] == 'tool-evidence-envelope-exceeded'
    assert complete['records'][0]['content'] == large['result']['content']


def test_rejected_candidate_releases_review_protection_and_preserves_unit_costs():
    from tests.test_automatic_mixed_configuration import config
    from refractrouter.application_config import compile_configuration
    from refractrouter.configured_routing import configured_profile
    raw = config()
    compiled = compile_configuration(raw)
    plan = preview_plan(TASK).to_dict()
    profile = configured_profile(compiled, compiled.manifest, plan)
    result = run_task({**REQUEST, 'task': TASK, 'method': 'A', 'weights': None, 'plan': plan,
        'costMaxByUnit': {'AFP': 100, 'CNY': 100}}, compiled.manifest, profile,
        client=CandidateClient(), tool_runtime=StdioToolRuntime(SCHEMAS, Host()),
        production_limit={'AFP': 100, 'CNY': 100}, evaluation_limit={'AFP': 100, 'CNY': 100},
        configured_application=True, configuration=compiled)
    assert result['status'] == 'tool-requirement-failed', result['issues']
    assert result['review']['protection']['status'] == 'released-unspent'
    assert all(result['charged'][unit]['evaluation'] == 0 for unit in ('AFP', 'CNY'))
    assert result['calls'] and all(c['status'] == 'billed' for c in result['calls'])
