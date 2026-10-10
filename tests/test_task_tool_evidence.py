"""复现 #178：工具约束不能由猜对答案、模型自述或宽松 Judge 代替。"""
from tests.review_fixtures import mock_grounding_checks
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from refractrouter.task_tool_evidence import (collect_tool_evidence, tool_requirements, MAX_EVIDENCE_BYTES,
                                             check_review_capacity, validation_message)
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
                'grounding_checks': mock_grounding_checks(json.loads(messages[-1]['content'])), 'criteria': [{'criterion': c, 'passed': True, 'rationale': '通过'} for c in criteria]}))
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


class ResearchClient(CandidateClient):
    """模拟本次研究的 11 条回执；内容为合成材料，不冒充原运行回放。"""
    def complete(self, model, messages, **kwargs):
        if model.role != 'judge' and not any(m['role'] == 'tool' for m in messages):
            self.calls.append((model, deepcopy(messages), kwargs))
            names = ['skill', 'web_search', 'bash', 'web_fetch', 'web_search', 'web_fetch',
                     'web_fetch', 'bash', 'bash', 'bash', 'web_search']
            return reply(calls=[call(name, id=f'research-{i}', args=json.dumps({'query': f'资料-{i}'}))
                                for i, name in enumerate(names)])
        return super().complete(model, messages, **kwargs)


class ResearchHost(Host):
    def exchange(self, protocol, payload):
        self.calls.append(deepcopy(payload))
        name = payload['call']['function']['name']
        return {'ok': True, 'result': {
            'isError': name == 'web_fetch',
            'content': [{'type': 'text', 'text': payload['call']['id'] + '资料"\\' * 700}],
            **({'hostResult': {'exitCode': 0}} if name == 'bash' else {})}}


def research(*, refs=False, context=None, evaluation_limit=100):
    from tests.test_automatic_cost_profiles import configuration
    from refractrouter.configured_routing import configured_profile
    compiled = configuration()
    if context is not None:
        compiled = replace(compiled, manifest=replace(compiled.manifest,
            models=tuple(replace(m, context_window=context) if m.model_id == compiled.manifest.judge.model_id
                         else m for m in compiled.manifest.models)))
    task = '根据真实检索资料分析数字双碳战略；无法读取的来源请如实说明。'
    schemas = [{'name': n, 'description': n, 'parameters': {'type': 'object'}}
               for n in ('skill', 'web_search', 'web_fetch', 'bash')]
    plan = preview_plan(task).to_dict()
    host, client = ResearchHost(), ResearchClient(answer='仅依据已获得的资料；三条网页读取失败。')
    result = run_task({**REQUEST, 'task': task, 'method': 'A', 'weights': None, 'costMax': 100,
        'plan': plan, 'maxFinalRevisions': int(refs)}, compiled.manifest,
        configured_profile(compiled, compiled.manifest, plan), client=client,
        tool_runtime=StdioToolRuntime(schemas, host), production_limit=100,
        evaluation_limit=evaluation_limit, configured_application=True, configuration=compiled)
    return result, client, host


@pytest.mark.parametrize('refs', [False, True])
def test_currency_research_full_evidence_reaches_judge_without_fixed_16k_cap_or_tool_reexecution(refs):
    result, client, host = research(refs=refs)
    assert result['status'] == 'completed', result['issues']
    validation = result['tool_validation']
    assert validation['evidence_bytes'] > 65759  # 超过真实事故的规模。
    assert validation['evidence_limit_bytes'] is None
    assert validation['review_input_bound'] <= validation['review_input_limit']
    judges = [c for c in client.calls if c[0].role == 'judge']
    assert len(judges) == 1 and len(host.calls) == 11
    judge, messages, _ = judges[0]
    payload = json.loads(messages[-1]['content'])
    from refractrouter.review_evidence import materialize
    records = materialize(payload['evidence_catalog'], 'tool_evidence')['records']
    assert len(records) == 11
    assert sum(r['outcome'] == 'unclassified-error' for r in records) == 3
    for r, original in zip(records, host.calls):
        assert r['content'][0]['text'] == original['call']['id'] + '资料"\\' * 700
    assert payload['evidence_catalog']['version'] == 'review-evidence-references-v3'
    assert 'tool_evidence' not in payload  # 完整字段在结构引用中，不重复发送。
    bound = request_input_bound(messages)
    assert validation['review_input_bound'] == bound
    row = next(c for c in result['calls'] if c['label'] == 'final-judge')
    # 预留真实完整消息；结算不把容量上界冒充实际用量。
    assert row['reserved'] >= bound / 1000 * judge.input_cost_per_1k
    assert row['charged'] < row['reserved']


def test_small_judge_capacity_blocks_full_request_before_paid_review_and_preserves_receipts():
    result, client, host = research(refs=True, context=32768)
    assert result['status'] == 'tool-requirement-failed', result['issues']
    validation = result['tool_validation']
    assert validation['reason'] == 'review-input-capacity-exceeded'
    assert validation['review_input_bound'] > validation['review_input_limit']
    assert '审核未派发' in validation['message']
    assert len(host.calls) == 11 and not any(c[0].role == 'judge' for c in client.calls)
    assert result['charged']['evaluation'] == 0 and result['charged']['production'] > 0


def test_larger_evidence_never_bypasses_review_budget():
    result, client, host = research(evaluation_limit=.000001)
    assert result['status'] == 'failed', result['issues']
    assert any('evaluation-budget-exhausted' in str(i) for i in result['issues'])
    assert not any(c[0].role == 'judge' for c in client.calls) and len(host.calls) == 11
    assert result['charged']['evaluation'] == 0


def test_unknown_receipt_has_priority_over_size_and_capacity():
    unknown = record(status='execution-unconfirmed')
    unknown['result']['content'][0]['text'] = '未知' * MAX_EVIDENCE_BYTES
    for limit in (MAX_EVIDENCE_BYTES, None):
        _, validation = collect_tool_evidence(tool_requirements(TASK), [unknown], available=True,
                                            max_evidence_bytes=limit)
        validation = check_review_capacity(validation, MANIFEST.judge,
            [{'role': 'user', 'content': '长内容' * MANIFEST.judge.context_window}])
        assert validation['passed'] is False and validation['reason'] == 'host-tool-result-unconfirmed'
        assert '不会自动重新执行' in validation_message(validation)
