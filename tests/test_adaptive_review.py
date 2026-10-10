"""自适应最终审核按真实边界执行，跳过不代表质量通过；全部无网络。"""
from dataclasses import replace
import hashlib
import json

import pytest

from refractrouter.automatic_review import VERSION, finalize, outcome
from refractrouter.live_execution import complexity_gate, review_decision
from refractrouter.configured_routing import configured_profile
from refractrouter.review_evidence import catalog, materialize
from refractrouter.task_evaluation import evaluation_messages
from refractrouter.task_plan import preview_plan
from refractrouter.task_runtime import run_task
from refractrouter.tool_runtime import StdioToolRuntime
from tests.test_automatic_cost_profiles import configuration
from tests.test_native_tool_runtime import Host
from tests.test_task_tool_evidence import CandidateClient, SCHEMAS


def decision(payload, *, tools=True, policy='adaptive', gate=None):
    gate = gate or complexity_gate(payload, '', tools_allowed=tools)
    return review_decision(payload, gate, policy=policy, tools_allowed=tools, current_rules=True)


@pytest.mark.parametrize('task', ['请写一句生日祝福', 'Explain the idea of a stack.'])
def test_available_tools_and_unknown_decomposition_do_not_force_final_review(task):
    initial = decision({'task': task}, gate={'decision': 'direct', 'forced': False,
        'reasons': ['no-positive-decomposition-evidence'], 'combination': 'uncertain-direct-with-review'})
    assert initial['required'] and initial['phase'] == 'preflight'
    final = finalize(initial, answer='简短的概念说明。')
    assert final['required'] is False and final['phase'] == 'final'
    assert final['reason'] == 'adaptive-low-risk-direct'
    assert initial['phase'] == 'preflight'  # 预检与冻结授权不可被最终结果改写。


@pytest.mark.parametrize('extra,reason', [
    ({'materials': ['原文']}, 'materials-present'),
    ({'acceptanceCriteria': ['准确']}, 'acceptance-criteria-present'),
    ({'outputConstraints': {'format': 'json'}}, 'strict-output-contract'),
    ({'task': '请查证近期事实并给出来源'}, 'task-needs-factual-verification'),
    ({'task': '请使用 Bash 执行命令'}, 'task-requires-tools'),
    ({'task': '继续分析上文', 'context': '既有任务上下文'}, 'context-dependent-request'),
])
def test_task_risks_survive_to_final_review(extra, reason):
    result = finalize(decision({'task': '回答问题', **extra}), answer='候选')
    assert result['required'] and reason in result['reason']


def test_tools_candidate_and_deterministic_defect_cannot_bypass_review():
    initial = decision({'task': '回答问题'})
    actual = finalize(initial, answer='说明', tool_evidence={'records': [{'call_id': 'one'}]})
    assert actual['tool_result_count'] == 1 and 'host-tools-used' in actual['reason']
    sourced = finalize(initial, answer='来源：https://example.test/original')
    assert 'candidate-cites-sources' in sourced['reason']
    asserted = finalize(initial, answer='我已经执行测试，测试全部通过。')
    assert 'candidate-asserts-system-state' in asserted['reason']
    defective = finalize(initial, answer='说明', known_failure={'passed': False})
    assert 'deterministic-check-failed' in defective['reason']


def test_always_and_dag_remain_required_and_legacy_contract_is_unchanged():
    payload = {'task': '普通任务'}
    gate = {'decision': 'dag', 'forced': False, 'reasons': []}
    assert finalize(decision(payload, gate=gate), answer='说明')['required']
    assert finalize(decision(payload, policy='always'), answer='说明')['required']
    old = review_decision(payload, {**gate, 'decision': 'direct'}, tools_allowed=True)
    assert old['reason'] == 'host-tools-available' and 'version' not in old


def current_run(client, *, task='请写一句生日祝福', runtime=None, policy='adaptive', revisions=1):
    c = configuration()
    c = replace(c, manifest=replace(c.manifest, models=tuple(
        replace(m, max_output_tokens=2048) for m in c.manifest.models)))
    payload = {'task': task}
    gate = complexity_gate(payload, '', tools_allowed=runtime is not None)
    review = decision(payload, tools=runtime is not None, policy=policy, gate=gate)
    plan = preview_plan(task).to_dict()
    return run_task({'task': task, 'mode': 'run', 'method': 'A', 'qualityMin': 80,
        'costMax': 100, 'latencyMaxMs': 300000, 'plan': plan, 'maxFinalRevisions': revisions},
        c.manifest, configured_profile(c, c.manifest, plan), client=client,
        production_limit=100, evaluation_limit=100, configured_application=True, configuration=c,
        tool_runtime=runtime, decision_evidence=gate, review_evidence=review)


def test_current_pipeline_skips_paid_review_even_with_host_tools_registered():
    host, client = Host(), CandidateClient(answer='生日快乐！')
    result = current_run(client, runtime=StdioToolRuntime(SCHEMAS, host))
    assert result['status'] == 'completed', result['issues']
    assert result['review']['version'] == VERSION and result['review']['status'] == 'skipped'
    assert result['review']['tool_result_count'] == 0
    assert result['evaluation'] is None and result['charged']['evaluation'] == 0
    assert len(client.calls) == 1 and not host.calls


def test_current_agent_binds_deferred_review_then_skips_actual_call(tmp_path):
    from refractrouter.agent import run_agent
    from tests.test_live_execution import authorization
    payload = {'task': '请写一句生日祝福', 'strategy': 'auto'}
    common = {'provider_config': configuration().snapshot, 'production_budget': 100,
              'evaluation_budget': 100, 'max_output_tokens': 2048}
    preview = run_agent(payload, runs_dir=tmp_path/'preflight', **common)
    assert preview['review']['version'] == VERSION and preview['review']['phase'] == 'preflight'
    assert not preview.get('calls')
    client = CandidateClient(answer='生日快乐！')
    result = run_agent({**payload, 'authorization': authorization(preview['live_authorization_preview'])},
        mode='live', execute_paid_run=True, client=client, runs_dir=tmp_path/'live', **common)
    assert result['status'] == 'completed', result['issues']
    assert result['review']['status'] == 'skipped' and result['review']['phase'] == 'final'
    assert len(client.calls) == 1


def test_real_tool_result_requires_review_without_reexecuting_tool():
    host, client = Host(), CandidateClient(tool='bash', answer='7')
    result = current_run(client, task='请使用 Bash 执行 printf 7，再回答。',
                         runtime=StdioToolRuntime(SCHEMAS, host))
    assert result['status'] == 'completed', result['issues']
    assert result['review']['tool_result_count'] == 1 and 'host-tools-used' in result['review']['reason']
    assert len(host.calls) == 1 and len(client.calls) == 3
    assert result['evaluation']['input_representation']['complete_values']
    payload = json.loads(client.calls[-1][1][-1]['content'])
    evidence = materialize(payload['evidence_catalog'], 'tool_evidence')
    assert evidence['records'][0]['arguments'] == '{"command":"printf 7"}'


class VerdictClient(CandidateClient):
    def __init__(self, mode):
        super().__init__(answer='说明')
        self.mode, self.reviews = mode, 0

    def complete(self, model, messages, **kwargs):
        response = super().complete(model, messages, **kwargs)
        if '纠正尚未交付' in messages[0]['content']:
            return replace(response, content='已修正的说明')
        if model.role == 'judge':
            self.reviews += 1
            verdict = json.loads(response.content)
            if self.reviews == 1:
                if self.mode == 'uncertain':
                    verdict['passed'] = False
                    verdict['grounding_checks'][0].update(status='UNCERTAIN', rationale='来源未提供')
                elif self.mode == 'defect':
                    verdict['passed'] = False
                    verdict['criteria'][0]['passed'] = False
                else:
                    verdict['score'] = 60
            return replace(response, content=json.dumps(verdict, ensure_ascii=False))
        return response


@pytest.mark.parametrize('mode,kind', [('uncertain', 'insufficient-evidence'),
                                     ('low-score', 'below-quality-threshold')])
def test_non_repairable_review_stops_without_extra_model_calls(mode, kind):
    client = VerdictClient(mode)
    result = current_run(client, policy='always')
    assert result['status'] == 'quality-failed', result['issues']
    assert result['review']['status'] == 'not-approved'
    assert result['review']['failure']['kind'] == kind
    assert not result['review']['failure']['repairable']
    assert len(client.calls) == 2 and 'final_correction' not in result


def test_explicit_defect_is_corrected_once_then_reviewed_without_planning():
    client = VerdictClient('defect')
    result = current_run(client, policy='always')
    assert result['status'] == 'completed', result['issues']
    assert result['final_output'] == '已修正的说明' and result['final_correction']['attempt'] == 1
    assert [c['label'] for c in result['calls']][1:] == ['final-judge', 'final-correction', 'final-judge-correction']
    assert result['calls'][0]['category'] == 'production'
    assert result['review']['failure']['kind'] == 'approved'


def test_rate_limit_is_infrastructure_failure_with_unknown_reserve_not_quality_repair():
    from refractrouter.openai_compatible import ModelInvocationError
    class Busy(CandidateClient):
        def complete(self, model, messages, **kwargs):
            if model.role == 'judge':
                self.calls.append((model, messages, kwargs))
                raise ModelInvocationError('rate-limit', '供应商私有正文不可展示', 1, 12,
                    diagnostics={'http_status': 429, 'secret': '不可展示'})
            return super().complete(model, messages, **kwargs)
    client = Busy()
    result = current_run(client, policy='always')
    assert result['status'] == 'failed' and len(client.calls) == 2
    failure = result['review']['failure']
    assert failure['kind'] == 'infrastructure-error' and failure['usage_pending']
    assert failure['transport']['http_status'] == 429 and not failure['repairable']
    assert 'secret' not in failure['transport']
    assert 'final_correction' not in result
    row = result['calls'][-1]
    assert row['status'] == 'unknown-usage' and row['charged'] == row['reserved'] > 0


def test_uncertainty_takes_priority_over_another_explicit_defect():
    row = outcome({'passed': False, 'score': 20, 'grounding_checks': [
        {'check_id': 'source-state', 'status': 'UNCERTAIN'},
        {'check_id': 'time-causality', 'status': 'FAIL'}]}, 80)
    assert row['kind'] == 'insufficient-evidence' and not row['repairable']


def test_complete_structured_evidence_preserves_values_order_pairing_and_all_origins():
    # 名称与序列化保留标记相同、空白、转义、标量等不得被误认成 Router 引用。
    raw = {'text_refs': [], 'object': {'array': []}, 'empty': '', 'space': ' \n',
           'bool': False, 'null': None, 'number': 0,
           'messages': [{'role': 'user', 'content': '原文"\\\n保持'},
                        {'role': 'tool', 'tool_call_id': 'call-one', 'content': '原文"\\\n保持'}]}
    tool = {'records': [{'call_id': 'call-one', 'arguments': '{}',
                        'content': raw['messages'][0]['content'], 'host_result': {'exitCode': 0}}]}
    task = json.dumps(raw, ensure_ascii=False)
    evidence = catalog(task, '完整候选', ['验收'], [], tool, compact=True)
    assert materialize(evidence, 'task') == raw
    assert materialize(evidence, 'tool_evidence') == tool
    assert materialize(evidence, 'candidate') == '完整候选'
    original = next(r for r in evidence['sources'] if r['text'] == raw['messages'][0]['content'])
    assert len(original['origins']) == 3
    assert evidence['task_sha256'] == hashlib.sha256(task.encode()).hexdigest()


def test_compact_review_keeps_large_complete_original_and_avoids_duplicate_serializations():
    body = '公开原始证据，不应截断。"\\\n' * 1000
    task = json.dumps({'messages': [{'role': 'tool', 'content': body}]}, ensure_ascii=False)
    evidence = {'records': [{'call_id': 'one', 'arguments': '{}', 'content': body}]}
    old = evaluation_messages(task, '候选', ['正确'], tool_evidence=evidence, evidence_refs=True)
    new = evaluation_messages(task, '候选', ['正确'], tool_evidence=evidence,
                              evidence_refs=True, compact_evidence=True)
    assert len(json.dumps(new, ensure_ascii=False).encode()) < len(json.dumps(old, ensure_ascii=False).encode()) / 2
    p = json.loads(new[-1]['content'])
    assert 'task' not in p and 'tool_evidence' not in p
    assert materialize(p['evidence_catalog'], 'task')['messages'][0]['content'] == body
    assert materialize(p['evidence_catalog'], 'tool_evidence') == evidence
