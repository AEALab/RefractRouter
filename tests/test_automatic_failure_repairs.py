"""复验实际失败结构、账本事实阻断与评审包络；无网络、无付费调用。"""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from refractrouter.agent import run_agent
from refractrouter.compact_planning import normalize_compact_types, compile_compact
from refractrouter.responses_api import output_token_limit
from experiments.run_automatic_applicability import task_check
from tests.test_live_execution import CompactClient, config, authorization


def test_recorded_illegal_plans_preserve_graph_and_compile_without_another_model_call():
    fixtures = json.loads((Path(__file__).parent/'fixtures/automatic-planner-analysis-alias.json').read_text())
    for case in fixtures:
        raw = case['plan']
        with pytest.raises(ValueError, match='node_type'):
            compile_compact(raw)
        canonical, changes = normalize_compact_types(raw)
        expected = deepcopy(raw)
        for row in expected['nodes']:
            if row['type'] == 'analysis':
                row['type'] = 'synthesis'
        assert canonical == expected and changes
        plan = compile_compact(canonical)
        assert len(plan.nodes) == len(raw['nodes'])
        assert plan.final_node_id == raw['nodes'][-1]['id']


def test_recorded_extra_closer_preserves_plan_and_uses_no_repair_call(tmp_path, monkeypatch):
    from dataclasses import replace
    from refractrouter.compact_planning import load_compact_reply
    import tests.test_automatic_failure_repairs as this
    content = json.loads(Path('tests/fixtures/automatic-planner-extra-closer.json').read_text())['response']
    fixed, changes = load_compact_reply(content, normalize=True)
    assert len(changes) == 1 and len(fixed['nodes']) == 1
    assert fixed['nodes'][0]['id'] == 'answer' and fixed['nodes'][0]['parents'] == []
    assert content[:changes[0]['position']] + content[changes[0]['position']+1:] == json.dumps(
        fixed, ensure_ascii=False, separators=(',', ':'))
    class RecordedPlan(CompactClient):
        def complete(self, model, messages, **kwargs):
            response = super().complete(model, messages, **kwargs)
            return replace(response, content=content) if 'DAG 规划器' in messages[0]['content'] else response
    monkeypatch.setattr(this, 'CompactClient', RecordedPlan)
    result, client = launch(tmp_path, complexityPolicy='dag')
    assert result['status'] == 'completed' and len(client.calls) == 3
    attempt = result['compact_planning']['attempts'][0]
    assert attempt['output'] == content
    assert attempt['json_normalization']['changes'] == changes
    assert all(c['status'] == 'billed' for c in result['calls'])


@pytest.mark.parametrize('content', ['{"nodes":[{"job":"文字 } 应保留"}]}',
    '{"nodes":[{"job":"转义 \\\" } 应保留"}]}'])
def test_valid_closers_in_strings_are_never_changed(content):
    from refractrouter.compact_planning import load_compact_reply
    result, changes = load_compact_reply(content, normalize=True)
    assert result == json.loads(content) and changes == []


@pytest.mark.parametrize('content', ['{"nodes":[{"id":"a"}',
    '{"nodes":[{"id":"a"}]]}', '{"nodes":[{"id":"a"}}}]}',
    '{"nodes":[{"id":"a"} {"id":"b"}]}'])
def test_other_json_syntax_errors_remain_rejected(content):
    from refractrouter.compact_planning import load_compact_reply
    with pytest.raises(json.JSONDecodeError):
        load_compact_reply(content, normalize=True)


def launch(tmp_path, *, final_validator=None, timeout_ms=300000, **parameters):
    payload = {'task': '仅依据给定材料核对费用，完整说明各组成项。',
        'strategy': 'auto', 'complexityPolicy': 'direct', 'reviewPolicy': 'always',
        'boundedCallOutput': True, 'unlimitedNodeOutput': True, **parameters}
    raw = config()
    for m in raw['models']:
        m.update(maxOutputTokens=32768, contextWindow=1000000)
    common = dict(provider_config=raw, production_budget=1000, evaluation_budget=1000,
                  timeout_ms=timeout_ms, max_output_tokens=8192)
    preview = run_agent(payload, mode='preflight', runs_dir=tmp_path/'preview', **common)
    client = CompactClient()
    result = run_agent({**payload, 'authorization': authorization(preview['live_authorization_preview'])},
        mode='live', execute_paid_run=True, client=client, runs_dir=tmp_path/'live',
        final_validator=final_validator, **common)
    return json.loads(Path(result['result_path']).read_text()), client


def test_known_wrong_fact_stops_before_paid_judge_even_if_judge_fixture_would_approve(tmp_path):
    raw, client = launch(tmp_path, final_validator=lambda answer: task_check(answer,
        {'expectedAnswers': {'knownReferenceCny': .11, 'cashProtectedCny': .23}}))
    assert raw['status'] == 'quality-failed'
    assert raw['review']['status'] == 'blocked-deterministic-check'
    assert raw['deterministic_validation']['passed'] is False
    assert len(client.calls) == 1
    assert raw['calls'][0]['status'] == 'billed'
    assert raw['evaluation'] is None


def test_reported_grounding_failure_blocks_real_candidate_with_95_score_and_settles_both_calls(tmp_path,monkeypatch):
    from dataclasses import replace
    import tests.test_automatic_failure_repairs as this
    fixture=json.loads(Path('data/research/automatic-grounding-native-counterexample-v1.json').read_text())
    class SourceChecked(CompactClient):
        def complete(self,model,messages,**kwargs):
            response=super().complete(model,messages,**kwargs)
            if model.role=='judge':
                verdict=json.loads(response.content)
                claims=verdict['grounding_checks'][2:]
                for row in claims:
                    if '回滚路径未经实测' in row['answer_quote']:
                        row.update(status='FAIL',claim_kind='FACT',source_quote=None,rationale='未提供测试状态')
                verdict.update(score=95,passed=False,rationale='记录来源信息缺失，拒绝事实否定断言',
                    grounding_checks=[{'check_id':'source-state','status':'FAIL',
                        'answer_quote':'回滚路径未经实测','source_quote':None,'rationale':'材料没有说明测试状态'},
                    {'check_id':'time-causality','status':'FAIL',
                        'answer_quote':'若审核实际耗时超过60秒则挤压执行时间','source_quote':None,
                        'rationale':'审核不挤压已经完成的执行'},*claims])
                return replace(response,content=json.dumps(verdict))
            return replace(response,content=fixture['answer'])
    monkeypatch.setattr(this,'CompactClient',SourceChecked)
    raw,client=launch(tmp_path)
    assert raw['status']=='quality-failed' and raw['evaluation']['score']==95
    assert raw['review']['passed'] is False and raw['final_output']==fixture['answer']
    assert len(client.calls)==2 and all(c['status']=='billed' for c in raw['calls'])
    assert len(raw['evaluation']['grounding_checks'])>2


def test_recorded_invalid_source_citation_stops_review_and_settles_usage(tmp_path, monkeypatch):
    from dataclasses import replace
    import tests.test_automatic_failure_repairs as this
    fixture = json.loads(Path('data/research/automatic-grounding-invalid-citation-v1.json').read_text())
    class RecordedCitation(CompactClient):
        def complete(self, model, messages, **kwargs):
            response = super().complete(model, messages, **kwargs)
            if model.role == 'judge':
                # 保留原非法引用，其余新增覆盖项只模拟接口，不作为语义质量证据。
                verdict={**fixture['rawVerdict'],'grounding_checks':[
                    *fixture['rawVerdict']['grounding_checks'],*json.loads(response.content)['grounding_checks'][2:]]}
                return replace(response, content=json.dumps(verdict))
            return replace(response, content=fixture['answer'])
    monkeypatch.setattr(this, 'CompactClient', RecordedCitation)
    raw, client = launch(tmp_path, task=fixture['task'])
    assert raw['status'] == 'failed' and raw['evaluation'] is None
    assert raw['review']['status'] == 'failed' and raw['review']['passed'] is False
    assert raw['review']['reason'] == 'grounding quote not in task evidence'
    assert len(client.calls) == 2 and all(c['status'] == 'billed' for c in raw['calls'])


def test_recorded_v5_missing_fields_stop_without_repair_or_delivery(tmp_path, monkeypatch):
    from dataclasses import replace
    import tests.test_automatic_failure_repairs as this
    fixture=json.loads(Path('data/research/automatic-grounding-v5-invalid-fields-v1.json').read_text())
    class RecordedFields(CompactClient):
        def complete(self, model, messages, **kwargs):
            response=super().complete(model, messages, **kwargs)
            content=json.dumps(fixture['rawVerdict']) if model.role=='judge' else fixture['answer']
            return replace(response, content=content)
    monkeypatch.setattr(this, 'CompactClient', RecordedFields)
    raw, client=launch(tmp_path, task=fixture['task'])
    assert raw['status']=='failed' and raw['evaluation'] is None
    assert raw['review']['status']=='failed' and raw['review']['passed'] is False
    assert raw['review']['reason']=='invalid final judge grounding fields'
    assert len(client.calls)==2 and all(c['status']=='billed' for c in raw['calls'])


def test_review_uses_separate_output_cap_and_keeps_worker_unlimited(tmp_path, monkeypatch):
    from refractrouter import task_runtime
    from refractrouter.task_execution import execute_nodes as real_execute
    from refractrouter.task_evaluation import evaluate_text as real_evaluate
    deadlines, caps = {}, {}
    def execute(*args, **kwargs):
        deadlines['worker'] = kwargs['deadline']
        caps['worker'] = max(output_token_limit(m) for m in args[3].values())
        return real_execute(*args, **kwargs)
    def evaluate(budget, judge, *args, **kwargs):
        deadlines['judge'] = kwargs['deadline']
        caps['judge'] = output_token_limit(judge)
        return real_evaluate(budget, judge, *args, **kwargs)
    monkeypatch.setattr(task_runtime, 'execute_nodes', execute)
    monkeypatch.setattr(task_runtime, 'evaluate_text', evaluate)
    raw, client = launch(tmp_path)
    assert raw['status'] == 'completed' and len(client.calls) == 2
    assert deadlines['judge'] - deadlines['worker'] == pytest.approx(60)
    assert caps == {'worker': 32768, 'judge': 8192}
    assert raw['review']['time_reserve_ms'] == 60000


@pytest.mark.parametrize('timeout,unlimited,expected', [(180000, False, 180000),
    (0, False, 300000), (180000, True, 180000), (0, True, None)])
def test_review_wait_is_independent_but_cannot_exceed_task_deadline(tmp_path, monkeypatch,
                                                                  timeout, unlimited, expected):
    from refractrouter import task_runtime
    from refractrouter.task_evaluation import evaluate_text as real_evaluate
    seen = []
    def evaluate(*args, **kwargs):
        now = task_runtime.time.monotonic()
        seen.append(None if kwargs['deadline'] == float('inf') else
                    (kwargs['deadline'] - now) * 1000)
        return real_evaluate(*args, **kwargs)
    monkeypatch.setattr(task_runtime, 'evaluate_text', evaluate)
    raw, _ = launch(tmp_path, reviewTimeoutMs=timeout,
                    limits={'unlimitedTime': unlimited})
    assert raw['status'] == 'completed'
    assert raw['review']['timeout_ms'] == (timeout or None)
    if expected is None:
        assert seen == [None] and raw['review']['effective_wait_ms'] is None
    else:
        assert expected - 2000 < seen[0] <= expected
    assert raw['review']['task_timeout_ms'] == (None if unlimited else 300000)


def test_shorter_task_caps_longer_review_wait(tmp_path):
    raw, _ = launch(tmp_path, timeout_ms=100000, reviewTimeoutMs=180000, reviewReserveMs=0)
    assert raw['status'] == 'completed'
    assert 98000 < raw['review']['effective_wait_ms'] <= 100000


def test_insufficient_total_time_does_not_dispatch_worker_or_judge(tmp_path):
    raw, client = launch(tmp_path, timeout_ms=20000)
    assert raw['status'] != 'completed'
    assert not client.calls and not raw['calls']


def test_planner_gets_remaining_time_and_review_reserve_without_answer_keys(tmp_path):
    raw, client = launch(tmp_path, complexityPolicy='dag', plannerTimeoutMs=90000)
    payload = json.loads(client.calls[0][1][-1]['content'])
    hint = payload['planning_budget']
    assert hint['version'] == 'automatic-planning-time-envelope-v1'
    assert hint['review_reserve_ms'] == 60000
    assert hint['planner_allowance_ms'] == 90000
    assert 140000 < hint['execution_after_planner_ms'] <= 150000
    assert hint['estimates_are_guarantees'] is False
    assert 'expectedAnswers' not in payload
    assert raw['planning_budget'] == hint


def test_short_dag_task_stops_before_even_paid_planning(tmp_path):
    raw, client = launch(tmp_path, timeout_ms=20000, complexityPolicy='dag')
    assert not client.calls and not raw['calls']
    assert raw['review']['reason'] == 'planning-would-consume-review-reserve'


def test_late_known_worker_result_does_not_launch_judge_with_tiny_deadline(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from refractrouter import task_runtime
    from refractrouter.task_execution import execute_nodes as real_execute
    monotonic = task_runtime.time.monotonic
    drift = [0]
    monkeypatch.setattr(task_runtime, 'time', SimpleNamespace(monotonic=lambda: monotonic() + drift[0]))
    def late_worker(*args, **kwargs):
        answer = real_execute(*args, **kwargs)
        drift[0] = 280  # 模拟确认用量的执行器迟到；不等待、不访问网络。
        return answer
    monkeypatch.setattr(task_runtime, 'execute_nodes', late_worker)
    raw, client = launch(tmp_path)
    assert raw['status'] == 'review-time-exhausted'
    assert raw['review']['status'] == 'not-dispatched-insufficient-time'
    assert len(client.calls) == 1 and raw['calls'][0]['status'] == 'billed'
    assert not any(c['status'] == 'unknown-usage' for c in raw['calls'])


@pytest.mark.parametrize('values', [{'reviewReserveMs': True}, {'reviewReserveMs': -1},
    {'reviewMaxOutputTokens': 0}, {'reviewMaxOutputTokens': 128001},
    {'reviewTimeoutMs': True}, {'reviewTimeoutMs': -1}, {'reviewTimeoutMs': 3600001}])
def test_bad_review_envelopes_are_rejected_before_calls(tmp_path, values):
    with pytest.raises(ValueError):
        launch(tmp_path, **values)


@pytest.mark.parametrize('policy,context', [('legacy','full'),('minimal-v1','full'),
    ('minimal-v2','full'),('minimal-v1','selective-v1'),('minimal-v2','selective-v1')])
def test_every_planner_policy_receives_time_contract(policy, context):
    from refractrouter.compact_planning import planner_system
    prompt = planner_system(policy, context)
    assert 'planning_budget' in prompt and 'max_nodes 包含最终交付节点' in prompt


@pytest.mark.parametrize('remaining,priors,parallel,expected', [
    (150000, {'a':60000,'b':60000}, 1, 2),
    (230000, {'a':60000}, 1, 3),
    (30000, {'a':60000}, 1, 0),
    (None, {'a':60000}, 1, 6),
    (150000, {'a':None}, 1, 6),
    (150000, {'a':60000,'b':0}, 1, 6),
    (150000, {'a':60000}, 2, 6),
])
def test_serial_node_limit_uses_complete_priors_only(remaining, priors, parallel, expected):
    from refractrouter.compact_planning import planning_node_limit
    assert planning_node_limit({'execution_after_planner_ms':remaining,
                                'latency_prior_ms':priors}, parallel) == expected


def test_realistic_slow_priors_constrain_actual_planner_and_stop_oversized_plan(tmp_path, monkeypatch):
    import tests.test_automatic_failure_repairs as this
    original = config
    def slow_config():
        raw = original()
        for model in raw['models']:
            if 'routing' in model:
                model['routing']['latencyMs'] = 60000
        return raw
    monkeypatch.setattr(this, 'config', slow_config)
    raw, client = launch(tmp_path, complexityPolicy='dag', plannerTimeoutMs=90000)
    payload = json.loads(client.calls[0][1][-1]['content'])
    assert payload['max_nodes'] == 2
    assert raw['planning_budget']['max_nodes'] == 2
    # 夹具故意给出三节点：保留失败且不派发工作节点，不偷偷删任务。
    assert len(client.calls) == 1 and raw['status'] != 'completed'
    assert raw['calls'][0]['status'] == 'billed'


def test_two_node_plan_finishes_under_same_serial_time_envelope(tmp_path, monkeypatch):
    from dataclasses import replace
    import tests.test_automatic_failure_repairs as this
    original = config
    def slow_config():
        raw = original()
        raw['objective']['dagMode'] = 'force'
        for model in raw['models']:
            if 'routing' in model:
                model['routing']['latencyMs'] = 60000
        return raw
    class TwoNodes(CompactClient):
        def complete(self, model, messages, **kwargs):
            response = super().complete(model, messages, **kwargs)
            if 'DAG 规划器' in messages[0]['content']:
                return replace(response, content=json.dumps({'reason':'两项职责在时间内交接', 'nodes':[
                    {'id':'facts','type':'synthesis','job':'核对全部金额和取消边界','parents':[],
                     'difficulty':'medium','risk':'medium'},
                    {'id':'answer','type':'generation','job':'复核原始材料并完整交付方案','parents':['facts'],
                     'difficulty':'medium','risk':'medium'}]}))
            return response
    monkeypatch.setattr(this, 'config', slow_config)
    monkeypatch.setattr(this, 'CompactClient', TwoNodes)
    raw, client = launch(tmp_path, complexityPolicy='dag', plannerTimeoutMs=90000)
    assert raw['status'] == 'completed'
    assert len(client.calls) == 4  # 一次规划、两次执行、一次评审。
    assert [n['node_id'] for n in raw['plan']['nodes']] == ['facts','answer']
    assert all(r['status'] == 'billed' for r in raw['calls'])
