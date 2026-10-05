"""单任务真实执行门禁；全部使用确定性模拟客户端。"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from refractrouter.agent import run_agent
from refractrouter.openai_compatible import ChatResponse
from refractrouter.decomposition_decision import build_request, parse_answer
from refractrouter.live_execution import (authorization_binding, complexity_gate,
                                           create_authorization_preview,
                                           review_decision, validate_authorization)
from refractrouter.tool_runtime import StdioToolRuntime
from tests.test_text_tasks import Client


ROOT = Path(__file__).resolve().parents[1]


class CompactClient:
    """无网络模型夹具：规划、执行和评审均返回可核验用量。"""
    def __init__(self):
        self.calls = []

    def complete(self, model, messages, *, json_mode=False):
        self.calls.append((model.model_id, messages))
        system = messages[0]['content']
        if 'DAG 规划器' in system:
            content = json.dumps({'reason': '先独立核对两项材料，再汇总', 'nodes': [
                {'id': 'facts', 'type': 'extraction', 'job': '核对第一项事实',
                 'parents': [], 'difficulty': 'medium', 'risk': 'medium'},
                {'id': 'risks', 'type': 'verification', 'job': '核对第二项风险',
                 'parents': [], 'difficulty': 'medium', 'risk': 'medium'},
                {'id': 'answer', 'type': 'generation', 'job': '汇总事实与风险',
                 'parents': ['facts', 'risks'], 'difficulty': 'medium', 'risk': 'medium'}]})
        elif model.role == 'judge':
            criteria = json.loads(messages[-1]['content'])['criteria']
            content = json.dumps({'score': 92, 'passed': True, 'rationale': '已覆盖',
                'criteria': [{'criterion': item, 'passed': True, 'rationale': '已核对'}
                             for item in criteria]}, ensure_ascii=False)
        elif json_mode:
            fields = json.loads(messages[-1]['content'])['contract']['output']['fields']
            content = json.dumps({key: '已核对' for key in fields}, ensure_ascii=False)
        else:
            content = '完整答复'
        return ChatResponse(content, 100, 80, 0, 0, 10, 1, 'stop', 'mock-route')


class SingleNodeClient(CompactClient):
    """规划器明确认为无需拆分，仍保留实际规划调用与用量。"""
    def complete(self, model, messages, *, json_mode=False):
        response = super().complete(model, messages, json_mode=json_mode)
        if 'DAG 规划器' not in messages[0]['content']:
            return response
        plan = {'reason': '单轮可完成', 'nodes': [
            {'id': 'answer', 'type': 'generation', 'job': '完整回答原任务',
             'parents': [], 'difficulty': 'medium', 'risk': 'medium'}]}
        return replace(response, content=json.dumps(plan, ensure_ascii=False))


def config():
    raw = json.loads((ROOT / 'data/schema/refractagent-providers-v4-example.json').read_text())
    raw['security']['dataMode'] = 'synthetic'
    raw['providers'][1] = {'id': 'local', 'type': 'openai-compatible',
                           'baseUrl': 'https://local.example/v1', 'deployment': 'local'}
    return raw


def authorization(preview):
    return {key: preview[key] for key in (
        'schema_version', 'authorization_id', 'issued_at', 'expires_at', 'preview_sha256')}


def test_zero_call_gate_is_deterministic_and_forced_direct_cannot_bypass_tools():
    simple = complexity_gate({'task': '现在应该可以了吧'}, '', policy='auto')
    assert simple['decision'] == 'direct' and simple['reasons'] == ['short-single-deliverable']
    assert complexity_gate({'task': '分别比较两个方案，然后汇总'}, '', policy='auto')['decision'] == 'dag'
    assert complexity_gate({'task': '简短回答', 'outputConstraints': {'maxCharacters': 20}}, '', policy='auto')['decision'] == 'dag'
    assert complexity_gate({'task': '根据材料回答', 'materials': [{'id': 'one'}]}, '', policy='auto')['decision'] == 'direct'
    assert complexity_gate({'task': '根据材料回答', 'materials': [{'id': 'one'}, {'id': 'two'}]}, '', policy='auto')['decision'] == 'dag'
    assert complexity_gate({'task': '读取仓库并运行测试'}, '', policy='direct')['decision'] == 'blocked-tools'


def test_negated_tool_request_does_not_claim_tools_are_required():
    task = '请用一句话说明路径是哪一类；不要读取文件，也不要调用工具。'
    gate = complexity_gate({'task': task}, '', tools_allowed=False)
    assert gate['decision'] == 'direct'
    assert 'explicit-tool-requirement' not in gate['reasons']
    assert complexity_gate({'task':'Please do not call a tool.'}, '', tools_allowed=False)['decision'] == 'direct'
    assert complexity_gate({'task':'请读取文件后说明路径'}, '', tools_allowed=False)['decision'] == 'blocked-tools'


def local_evidence(task, context, choice, confidence=.9):
    request = build_request(task, context)
    probabilities = {item: (confidence if item == choice else (1-confidence)/2)
                     for item in ('SEPARABLE', 'COUPLED', 'UNKNOWN')}
    return {"contract": request["contract"], "ruleVersion": request["ruleVersion"],
            "inputSha256": request["inputSha256"],
            **parse_answer({"choice": choice, "probabilities": probabilities}, threshold=.65),
            "model": "laya-fixture", "revision": "test", "latencyMs": 3,
            "queueMs": 1, "usage": {"questions": 1}, "experimental": True}


def test_v3_coupled_evidence_selects_direct_without_skipping_review_or_permissions():
    task = '这是一段很长的单一流水线任务。' * 50
    coupled = complexity_gate({'task': task}, '', decomposition=local_evidence(task, '', 'COUPLED'))
    assert coupled['rule_decision'] == 'dag' and coupled['decision'] == 'direct'
    assert coupled['combination'] == 'coupled-sequential-work'
    strict_task = '按严格格式完成一项连续任务'
    strict_payload = {'task': strict_task, 'outputConstraints': {'maxCharacters': 100}}
    strict = complexity_gate(strict_payload, '', decomposition=local_evidence(strict_task, '', 'COUPLED'))
    assert strict['decision'] == 'direct'
    assert review_decision(strict_payload, strict)['required']
    tool_task = '运行测试后根据堆栈修改代码，再运行测试'
    evidence = local_evidence(tool_task, '', 'COUPLED')
    assert complexity_gate({'task': tool_task}, '', decomposition=evidence)['decision'] == 'blocked-tools'
    allowed = complexity_gate({'task': tool_task}, '', decomposition=evidence, tools_allowed=True)
    assert allowed['decision'] == 'direct'
    assert review_decision({'task': tool_task}, allowed, tools_allowed=True)['required']
    old = {**local_evidence(strict_task, '', 'COUPLED'), 'ruleVersion': 'automatic-decomposition-hybrid-v2'}
    legacy = complexity_gate(strict_payload, '', decomposition=old)
    assert legacy['decision'] == 'dag'
    assert legacy['combination'] == 'hard-rules-preserved-over-local-coupled'
    short = '分别核对两个互不依赖的来源'
    separable = complexity_gate({'task': short}, '', decomposition=local_evidence(short, '', 'SEPARABLE'))
    assert separable['decision'] == 'dag' and 'local-separable' in separable['reasons']


def test_preflight_binds_local_decision_to_live_input(tmp_path):
    raw = config()
    task, context = '简短但可分离的两个检查', ''
    evidence = local_evidence(task, context, 'SEPARABLE')
    payload = {'task': task, 'context': context, 'strategy': 'auto',
               'decompositionDecision': evidence}
    preview = run_agent(payload, provider_config=raw, runs_dir=tmp_path / 'preview',
                        production_budget=10, evaluation_budget=10)
    assert preview['complexity_gate']['decision'] == 'dag'
    approved = authorization(preview['live_authorization_preview'])
    with pytest.raises(ValueError, match='拆分判别输入已改变'):
        run_agent({**payload, 'task': '输入已经变化', 'authorization': approved},
                  provider_config=raw, runs_dir=tmp_path / 'changed', mode='live',
                  execute_paid_run=True, client=Client(), production_budget=10,
                  evaluation_budget=10)


def test_adaptive_review_only_skips_unforced_low_risk_direct():
    payload = {'task': '简单回答'}
    direct = complexity_gate(payload, '', policy='auto')
    assert review_decision(payload, direct, policy='adaptive') == {
        'policy': 'adaptive', 'required': False, 'reason': 'adaptive-low-risk-direct'}
    forced = complexity_gate(payload, '', policy='direct')
    assert review_decision(payload, forced, policy='adaptive')['required'] is True
    assert review_decision(payload, direct, policy='always')['required'] is True


def test_preview_digest_binds_request_configuration_and_expiry():
    payload = {'task': '简单回答', 'strategy': 'auto'}
    gate = complexity_gate(payload, '', policy='auto')
    review = review_decision(payload, gate, policy='adaptive')
    binding = authorization_binding(payload, provider_config={'schemaVersion': 'v4'},
        catalog_snapshot={'routes': []}, production_budget=1, evaluation_budget=2,
        max_output_tokens=2048, gate=gate, review=review, data_mode='synthetic',
        billing_unit='USD')
    now = datetime(2026, 9, 22, tzinfo=timezone.utc)
    preview = create_authorization_preview(binding, billing_unit='USD',
        production_estimate=.1, evaluation_estimate=0, now=now)
    approved = authorization(preview)
    assert validate_authorization(approved, binding, now=now + timedelta(minutes=1)) == approved
    with pytest.raises(ValueError, match='configuration changed'):
        validate_authorization(approved, {**binding, 'production_budget': 3}, now=now)
    with pytest.raises(ValueError, match='expired'):
        validate_authorization(approved, binding, now=now + timedelta(minutes=11))


def test_tool_preview_binds_host_catalog_and_enforced_call_limit(tmp_path):
    schemas = [{'name': 'web_search', 'description': '查询网页', 'parameters': {'type': 'object'}}]
    runtime = StdioToolRuntime(schemas, object(), max_calls=2)
    payload = {'task': '请搜索网页并回答', 'strategy': 'auto', 'maxDshToolCalls': 2}
    preview = run_agent(payload, provider_config=config(), runs_dir=tmp_path / 'runs',
                        tool_runtime=runtime, production_budget=10, evaluation_budget=10)
    authorization_preview = preview['live_authorization_preview']
    assert preview['complexity_gate']['decision'] == 'dag'
    assert authorization_preview['tools_allowed'] is True
    assert authorization_preview['tools']['maximum_calls'] == 2
    assert authorization_preview['calls']['maximum'] == 10
    assert authorization_preview['calls']['estimate'] is None
    assert authorization_preview['costs']['estimate_kind'] == 'base-route-only-tool-continuations-unestimated'
    assert preview['review']['required'] is True
    approved = authorization(authorization_preview)
    changed_catalog = StdioToolRuntime([{'name': 'file_write', 'description': '写文件',
        'parameters': {'type': 'object'}}], object(), max_calls=2)
    with pytest.raises(ValueError, match='PREVIEW_MISMATCH'):
        run_agent({**payload, 'authorization': approved}, provider_config=config(),
                  runs_dir=tmp_path / 'changed', mode='live', execute_paid_run=True,
                  client=Client(), tool_runtime=changed_catalog, production_budget=10,
                  evaluation_budget=10)


def test_unlimited_tool_preview_has_no_fabricated_call_ceiling(tmp_path):
    schemas = [{'name': 'web_search', 'description': '查询网页', 'parameters': {'type': 'object'}}]
    runtime = StdioToolRuntime(schemas, object(), max_calls='unlimited')
    payload = {'task': '请搜索网页并回答', 'strategy': 'auto', 'maxDshToolCalls': 'unlimited'}
    result = run_agent(payload, provider_config=config(), runs_dir=tmp_path / 'runs',
                       tool_runtime=runtime, production_budget=10, evaluation_budget=10)
    preview = result['live_authorization_preview']
    assert preview['tools']['maximum_calls'] == 'unlimited'
    assert preview['calls']['maximum'] is None


def test_simple_v4_preflight_then_live_uses_one_worker_and_skips_judge(tmp_path):
    raw = config()
    payload = {'task': '现在应该可以了吧', 'strategy': 'auto',
               'complexityPolicy': 'auto', 'reviewPolicy': 'adaptive'}
    preview = run_agent(payload, provider_config=raw, runs_dir=tmp_path / 'runs',
                        production_budget=1, evaluation_budget=1)
    assert preview['status'] == 'preview'
    assert preview['complexity_gate']['decision'] == 'direct'
    assert preview['live_authorization_preview']['calls']['maximum'] == 1
    assert preview['costs'] == {'production': 0, 'evaluation': 0, 'unconfirmed': 0}
    client = Client()
    result = run_agent({**payload, 'authorization': authorization(preview['live_authorization_preview'])},
        provider_config=raw, runs_dir=tmp_path / 'runs', mode='live', execute_paid_run=True,
        client=client, production_budget=1, evaluation_budget=1)
    assert result['status'] == 'completed' and len(client.calls) == 1
    assert result['plan_origin'] == 'direct-gate'
    assert result['review']['status'] == 'skipped' and result['quality'] is None
    assert result['costs']['evaluation'] == 0


def test_live_second_level_can_discard_a_costly_dag_without_repeating_planner(tmp_path):
    raw = config()
    payload = {'task': '分别核对第一项事实和第二项风险，然后汇总建议。', 'strategy': 'auto'}
    preview = run_agent(payload, provider_config=raw, runs_dir=tmp_path / 'preview',
                        production_budget=10, evaluation_budget=10)
    client = CompactClient()
    result = run_agent({**payload, 'authorization': authorization(preview['live_authorization_preview'])},
        provider_config=raw, runs_dir=tmp_path / 'live', mode='live', execute_paid_run=True,
        client=client, production_budget=10, evaluation_budget=10)
    assert result['status'] == 'completed'
    assert result['plan_origin'] == 'direct-after-probe'
    assert result['route_comparison']['route'] == 'direct'
    assert result['route_comparison']['selected_candidate'] == 'direct-template'
    assert result['route_comparison']['selected_node_count'] == 1
    assert result['route_comparison']['multi_node_selected'] is False
    assert result['route_comparison']['decision_factors']['qualified_execution_model_count'] == 1
    assert result['route_comparison']['decision_factors']['task_specific_dag_quality_gain_verified'] is False
    assert result['route_comparison']['decision_factors']['dag_extra_worker_cost'] >= 0
    assert (result['route_comparison']['direct']['total_estimated_cost']
            <= result['route_comparison']['dag']['total_estimated_cost'])
    assert len(result['plan']['nodes']) == 1
    assert len(client.calls) == 3  # 规划一次，直接执行一次，最终评审一次
    assert result['cost_breakdown']['planning'] == 0  # 夹具中的本地规划模型不计 API 费用
    assert any(call['label'] == 'planner' for call in json.loads(Path(result['result_path']).read_text())['calls'])


def test_live_second_level_uses_dag_when_qualified_profiles_save_cost(tmp_path):
    raw = config()
    for model in raw['models']:
        if model['id'] == 'local-router':
            model['routing'] = {'quality': 50, 'latencyMs': 10000,
                'profiles': [{'nodeType': kind, 'difficulty': 'medium', 'risk': 'medium',
                              'inputMinTokens': 256, 'inputMaxTokens': 131073, 'quality': 90,
                              'latencyMs': 1000, 'outputTokens': 1000}
                             for kind in ('extraction', 'verification', 'generation')]}
    payload = {'task': '分别核对第一项事实和第二项风险，然后汇总建议。', 'strategy': 'auto'}
    preview = run_agent(payload, provider_config=raw, runs_dir=tmp_path / 'preview',
                        production_budget=10, evaluation_budget=10)
    client = CompactClient()
    result = run_agent({**payload, 'authorization': authorization(preview['live_authorization_preview'])},
        provider_config=raw, runs_dir=tmp_path / 'live', mode='live', execute_paid_run=True,
        client=client, production_budget=10, evaluation_budget=10)
    assert result['status'] == 'completed'
    assert result['route_comparison']['route'] == 'dag'
    assert result['route_comparison']['multi_node_selected'] is True
    assert result['route_comparison']['selected_node_count'] == 3
    assert result['plan_origin'] == 'model'
    assert len(result['plan']['nodes']) == 3
    assert len(client.calls) == 5  # 规划、三个节点、评审


def test_single_node_planner_result_is_direct_even_when_generated_plan_wins(tmp_path):
    raw = config()
    for model in raw['models']:
        if model['id'] == 'local-router':
            model['routing'] = {'quality': 50, 'latencyMs': 10000,
                'profiles': [{'nodeType': 'generation', 'difficulty': 'medium', 'risk': 'medium',
                              'inputMinTokens': 256, 'inputMaxTokens': 131073,
                              'quality': 90, 'latencyMs': 1000, 'outputTokens': 1000}]}
    payload = {'task': '分别核对第一项事实和第二项风险，然后汇总建议。', 'strategy': 'auto'}
    preview = run_agent(payload, provider_config=raw, runs_dir=tmp_path / 'preview',
                        production_budget=10, evaluation_budget=10)
    client = SingleNodeClient()
    result = run_agent({**payload, 'authorization': authorization(preview['live_authorization_preview'])},
        provider_config=raw, runs_dir=tmp_path / 'live', mode='live', execute_paid_run=True,
        client=client, production_budget=10, evaluation_budget=10)
    comparison = result['route_comparison']
    assert result['status'] == 'completed' and result['plan_origin'] == 'model'
    assert comparison['route'] == 'direct' and comparison['reason'] == 'generated-single-node'
    assert comparison['comparison_reason'] == 'direct-infeasible'
    assert comparison['selected_candidate'] == 'generated-plan'
    assert comparison['generated_node_count'] == comparison['selected_node_count'] == 1
    assert comparison['multi_node_selected'] is False
    assert len(result['plan']['nodes']) == 1 and len(client.calls) == 3


def test_live_second_level_keeps_valid_dag_when_direct_input_is_too_large(tmp_path, monkeypatch):
    from refractrouter import task_runtime
    original = task_runtime.compile_generated_capacity

    def capacity(plan, *args, **kwargs):
        if len(plan.nodes) == 1:
            raise ValueError('automatic-plan-input-capacity-exceeded: answer (known_input=999999)')
        return original(plan, *args, **kwargs)

    monkeypatch.setattr(task_runtime, 'compile_generated_capacity', capacity)
    raw = config()
    payload = {'task': '分别核对第一项事实和第二项风险，然后汇总建议。', 'strategy': 'auto'}
    preview = run_agent(payload, provider_config=raw, runs_dir=tmp_path / 'preview',
                        production_budget=10, evaluation_budget=10)
    result = run_agent({**payload, 'authorization': authorization(preview['live_authorization_preview'])},
        provider_config=raw, runs_dir=tmp_path / 'live', mode='live', execute_paid_run=True,
        client=CompactClient(), production_budget=10, evaluation_budget=10)
    assert result['status'] == 'completed'
    assert result['route_comparison']['route'] == 'dag'
    assert result['route_comparison']['direct'] is None
    assert result['route_comparison']['excluded']['direct']['answer'] == 'input-capacity'


def test_live_second_level_stops_before_workers_when_review_budget_is_insufficient(tmp_path, monkeypatch):
    from refractrouter import task_runtime
    monkeypatch.setattr(task_runtime, '_shared_judge_forecast', lambda *args: 20.0)
    raw = config()
    payload = {'task': '分别核对第一项事实和第二项风险，然后汇总建议。', 'strategy': 'auto'}
    preview = run_agent(payload, provider_config=raw, runs_dir=tmp_path / 'preview',
                        production_budget=10, evaluation_budget=10)
    client = CompactClient()
    result = run_agent({**payload, 'authorization': authorization(preview['live_authorization_preview'])},
        provider_config=raw, runs_dir=tmp_path / 'live', mode='live', execute_paid_run=True,
        client=client, production_budget=10, evaluation_budget=10)
    assert result['status'] == 'no-feasible-route'
    assert result['route_comparison']['route'] == 'infeasible'
    assert set(result['route_comparison']['budget_shortfalls']) == {'direct', 'dag'}
    assert len(client.calls) == 1  # 只发生有用量记录的规划探测


def test_v4_objective_never_and_force_are_bound_to_preflight(tmp_path):
    raw = config()
    raw['objective']['dagMode'] = 'never'
    payload = {'task': '分别核对两项材料，然后汇总。', 'strategy': 'auto'}
    direct = run_agent(payload, provider_config=raw, runs_dir=tmp_path / 'never')
    assert direct['complexity_gate']['decision'] == 'direct'
    assert direct['complexity_gate']['reasons'] == ['objective-dag-never']
    raw['objective']['dagMode'] = 'force'
    forced = run_agent({'task': '简短回答', 'strategy': 'auto'},
                       provider_config=raw, runs_dir=tmp_path / 'force')
    assert forced['complexity_gate']['decision'] == 'dag'
    assert forced['complexity_gate']['reasons'] == ['objective-dag-force']


def test_unlimited_cost_choices_are_independent_and_bound_to_preview(tmp_path):
    raw = config()
    payload = {'task': '简单回答', 'strategy': 'auto', 'reviewPolicy': 'adaptive'}
    preview = run_agent(payload, provider_config=raw, runs_dir=tmp_path / 'runs',
                        production_budget='unlimited', evaluation_budget=1)
    costs = preview['live_authorization_preview']['costs']
    assert costs['production_unlimited'] is True and costs['production_hard_limit'] is None
    assert costs['evaluation_unlimited'] is False and costs['evaluation_hard_limit'] == 1
    approved = authorization(preview['live_authorization_preview'])
    with pytest.raises(ValueError, match='PREVIEW_MISMATCH'):
        run_agent({**payload, 'authorization': approved}, provider_config=raw,
                  runs_dir=tmp_path / 'mismatch', mode='live', execute_paid_run=True,
                  client=Client(), production_budget=1, evaluation_budget=1)
    client = Client()
    result = run_agent({**payload, 'authorization': approved}, provider_config=raw,
                       runs_dir=tmp_path / 'runs', mode='live', execute_paid_run=True,
                       client=client, production_budget='unlimited', evaluation_budget=1)
    assert result['status'] == 'completed' and len(client.calls) == 1
    review_preview = run_agent({**payload, 'reviewPolicy': 'always'}, provider_config=raw,
                               runs_dir=tmp_path / 'review', production_budget=1,
                               evaluation_budget='unlimited')
    review_costs = review_preview['live_authorization_preview']['costs']
    assert review_costs['production_unlimited'] is False
    assert review_costs['evaluation_unlimited'] is True
    assert review_costs['evaluation_hard_limit'] is None
    assert review_costs['evaluation_estimate'] is None


def test_dag_preview_and_forced_direct_have_bounded_call_envelopes(tmp_path):
    raw = config()
    dag = run_agent({'task': '分别比较两个方案，然后汇总', 'strategy': 'auto',
                     'complexityPolicy': 'auto', 'reviewPolicy': 'adaptive'},
                    provider_config=raw, runs_dir=tmp_path / 'dag')
    assert dag['complexity_gate']['decision'] == 'dag'
    assert dag['review']['required'] is True
    assert dag['live_authorization_preview']['calls']['maximum'] == 8
    assert dag['live_authorization_preview']['costs']['production_estimate_range']['maximum'] == 40
    direct = run_agent({'task': '简单回答', 'strategy': 'auto',
                        'complexityPolicy': 'direct', 'reviewPolicy': 'adaptive'},
                       provider_config=raw, runs_dir=tmp_path / 'direct')
    assert direct['complexity_gate']['decision'] == 'direct'
    assert direct['review']['required'] is True
    assert direct['live_authorization_preview']['calls']['maximum'] == 2


def test_live_rejects_missing_preview_invalid_data_mode_and_tools_before_dispatch(tmp_path):
    raw = config()
    client = Client()
    with pytest.raises(ValueError, match='PREVIEW_MISMATCH'):
        run_agent({'task': '简单回答', 'strategy': 'auto'}, provider_config=raw,
            runs_dir=tmp_path / 'missing', mode='live', execute_paid_run=True, client=client)
    raw['security']['dataMode'] = 'invalid'
    with pytest.raises(ValueError, match='security.dataMode'):
        run_agent({'task': '简单回答', 'strategy': 'auto'}, provider_config=raw,
            runs_dir=tmp_path / 'live-data', mode='live', execute_paid_run=True, client=client)
    with pytest.raises(ValueError, match='TOOLS_DISABLED'):
        run_agent({'task': '请搜索网页', 'strategy': 'auto', 'complexityPolicy': 'direct'},
            provider_config=config(), runs_dir=tmp_path / 'tools', mode='live',
            execute_paid_run=True, client=client)
    assert not client.calls


def test_live_data_only_dispatches_to_local_or_trusted_models(tmp_path):
    raw = config()
    raw['security']['dataMode'] = 'live'
    # 外部模型更便宜，但真实会话无论是否匹配敏感词，都只准入可信路线。
    raw['models'][0]['routing'] = {'quality': 100, 'latencyMs': 1000}
    payload = {'task': '完成项目决策说明', 'strategy': 'auto',
               'complexityPolicy': 'direct', 'reviewPolicy': 'adaptive'}
    preview = run_agent(payload, provider_config=raw, runs_dir=tmp_path/'preview',
                        production_budget=10, evaluation_budget=10)
    assert preview['live_authorization_preview']['ready']
    client = Client()
    result = run_agent({**payload, 'authorization':authorization(preview['live_authorization_preview'])},
                       provider_config=raw, runs_dir=tmp_path/'live', mode='live',
                       execute_paid_run=True, client=client,
                       production_budget=10, evaluation_budget=10)
    assert result['status'] == 'completed'
    assert {model.model_id for model, _ in client.calls} <= {'local-router','local-judge'}


def test_live_relax_budget_cannot_bypass_authorized_hard_limit(tmp_path):
    raw = config()
    local_router = next(model for model in raw['models'] if model['id'] == 'local-router')
    local_router['roles'] = ['planner', 'classifier']
    local_router.pop('routing')
    external = next(provider for provider in raw['providers'] if provider['id'] == 'external')
    external.update(deployment='trusted-cloud', trustPolicy='test-policy')
    raw['trustPolicies'] = [{'id': 'test-policy', 'residency': 'test',
                             'auditLogging': True, 'allowsSensitiveData': True}]
    payload = {'task': '简单回答', 'strategy': 'auto',
               'complexityPolicy': 'auto', 'reviewPolicy': 'adaptive',
               'limits': {'relaxBudget': True, 'relaxContext': False}}
    preview = run_agent(payload, provider_config=raw, runs_dir=tmp_path / 'preview',
                        production_budget=0.000001, evaluation_budget=1)
    assert preview['status'] == 'no-feasible-route'
    assert preview['live_authorization_preview']['costs']['production_hard_limit'] == 0.000001
    assert preview['live_authorization_preview']['ready'] is False
