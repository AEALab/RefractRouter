"""Stage 协作策略的无网络合同验收。真实状态机，模拟本地推论与模型回执。"""
from copy import deepcopy
import math

import pytest

from refractrouter.planning_config import compile_config, preview
from refractrouter.planning_runtime import PlanningRuntime
from refractrouter.stage_hybrid import QUESTIONS, initial_state, observe, parse_answers, transition, decision_request
from tests.test_planning_routing import configuration, write_laya_fixture, FakeLocalService, begin, step, receipt


def config(tmp_path):
    path = tmp_path / 'weights'
    if not path.exists():
        write_laya_fixture(path)
    cfg = configuration()
    cfg.update(schemaVersion='refractagent-planning-v5')
    cfg['stage'] = {'mode': 'hybrid', 'allowExperimental': True, 'judge': {
        'type': 'local-decision', 'adapter': 'laya-mlx', 'modelPath': str(path),
        'sourceModel': 'aac6fef/laya-multilingual-mlx', 'revision': 'test'}}
    for model in cfg['models']:
        model['capabilityCard'] = '适合读取及简单编辑' if model['id'] == 'small' else '适合复杂推理及编辑'
    return cfg


def answers(route='EFFICIENT', confidence=.96, progress='PROGRESS'):
    result = {}
    for key, choice in (('progress', progress), ('route', route)):
        options = QUESTIONS[key]['criteria']
        result[key] = {'choice': choice, 'probabilities': {
            option: confidence if option == choice else (1-confidence)/(len(options)-1)
            for option in options}}
    return result


def local_result(route='EFFICIENT', **kw):
    return {'payload': {'answers': answers(route, **kw)}, 'model': 'local-laya',
            'coldStartMs': None, 'latencyMs': 20, 'usage': {'questions': 2, 'forwards': 1}}


def event(id, status='completed', fingerprint='failure-a'):
    return {'id': id, 'callId': id, 'tool': 'read', 'status': status,
            'kind': 'observe', 'category': 'read', 'fingerprint': fingerprint}


def messages(n=0):
    history = [{'role': 'user', 'content': '检查项目并修改错误'}]
    for i in range(n):
        history.extend([{'role': 'assistant', 'content': [{'type': 'tool-call',
            'id': f't{i}', 'name': 'read', 'arguments': {'path': 'test.txt'}}]},
            {'role': 'user', 'content': [{'type': 'tool-result', 'toolCallId': f't{i}',
                'content': [{'type': 'text', 'text': '需要继续检查'}]}]}])
    return history


def setup(tmp_path, result=None, error=None, modify=None):
    cfg = config(tmp_path)
    if modify:
        modify(cfg)
    runtime = PlanningRuntime(tmp_path / 'runs')
    runtime.local_service.close()
    runtime.local_service = FakeLocalService(result or local_result(), error)
    run = begin(runtime, config=cfg)
    return runtime, run


def poll(runtime, run, action):
    return runtime.handle({'op': 'local-judge-poll', 'runId': run, 'jobId': action['jobId']})


def test_migration_and_experimental_gate(tmp_path):
    assert compile_config(configuration())['stage'] == {'mode': 'rules'}
    cfg = config(tmp_path)
    assert next(r for r in preview(cfg)['strategies'] if r['id']=='stage')['available']
    cfg['stage']['allowExperimental'] = False
    assert not next(r for r in preview(cfg)['strategies'] if r['id']=='stage')['available']
    cfg['stage']['judge']['type'] = 'llm'
    with pytest.raises(ValueError, match='本地'):
        compile_config(cfg)


def test_strict_answers_and_thresholds(tmp_path):
    c = compile_config(config(tmp_path))['stage']
    assert parse_answers(answers(), c)['verdict'] == 'EFFICIENT_OK'
    assert parse_answers(answers('CAPABLE'), c)['verdict'] == 'NEED_STRONG'
    assert parse_answers(answers('UNKNOWN', progress='STALLED'), c)['verdict'] == 'NEED_STRONG'
    assert parse_answers(answers('EFFICIENT', progress='STALLED'), c)['verdict'] == 'UNCERTAIN'
    for value in (answers(confidence=.6), answers(route='UNKNOWN'), answers(progress='UNKNOWN')):
        assert parse_answers(value, c)['verdict'] == 'UNCERTAIN'
    for value in ({}, {**answers(), 'injected': {}},
                  {**answers(), 'route': {'choice': 'EFFICIENT', 'probabilities': {'EFFICIENT': math.nan}}}):
        with pytest.raises(ValueError):
            parse_answers(value, c)


def test_upgrade_hold_downgrade_and_only_selected_reservation(tmp_path):
    runtime, run = setup(tmp_path, local_result('CAPABLE'))
    first = step(runtime, run, messages(0))
    assert first['model']['id'] == 'small'
    assert not runtime.local_service.requests
    receipt(runtime, run, first)
    wait = step(runtime, run, messages(1))
    assert wait['action'] == 'wait'
    assert len(runtime.runs[run]['budget'].records) == 1
    strong = poll(runtime, run, wait)
    assert strong['model']['id'] == 'large'
    assert runtime.runs[run]['state']['stageHybrid']['hold'] == 1
    receipt(runtime, run, strong)
    held = step(runtime, run, messages(2))
    assert held['model']['id'] == 'large'
    assert len(runtime.local_service.requests) == 1
    receipt(runtime, run, held)
    runtime.local_service.result = local_result()
    for n, expected in ((3, 'large'), (4, 'small')):
        action = poll(runtime, run, step(runtime, run, messages(n)))
        assert action['model']['id'] == expected
        receipt(runtime, run, action)
    assert [r['model_id'] for r in runtime.runs[run]['budget'].records] == ['small', 'large', 'large', 'large', 'small']
    state = runtime.runs[run]['state']['stageHybrid']
    assert state['batches'] == 3
    assert all(r['apiCost'] == 0 for r in state['localRecords'])


@pytest.mark.parametrize('result,error,reason,model', [(local_result(confidence=.6), None, 'judge-uncertain', 'large'),
    (None, {'errorCode': 'capacity', 'error': 'too long'}, 'judge-upgrade', 'large')])
def test_uncertainty_and_capacity_follow_distinct_policy(tmp_path, result, error, reason, model):
    runtime, run = setup(tmp_path, result, error)
    receipt(runtime, run, step(runtime, run, messages()))
    action = poll(runtime, run, step(runtime, run, messages(1)))
    assert action['model']['id'] == model
    assert runtime.runs[run]['decisions'][-1]['reason'] == reason


@pytest.mark.parametrize('error', [None, {'errorCode': 'inference', 'error': 'worker crashed'}])
def test_invalid_or_failed_inference_stops_without_model_call(tmp_path, error):
    runtime, run = setup(tmp_path, {'payload': {}, 'usage': {}}, error)
    receipt(runtime, run, step(runtime, run, messages()))
    wait = step(runtime, run, messages(1))
    with pytest.raises(ValueError):
        poll(runtime, run, wait)
    assert runtime.runs[run]['status'] != 'running'
    assert len(runtime.runs[run]['budget'].records) == 1


def test_cancel_late_result_and_wrong_job_do_not_advance(tmp_path):
    runtime, run = setup(tmp_path)
    receipt(runtime, run, step(runtime, run, messages()))
    wait = step(runtime, run, messages(1))
    with pytest.raises(ValueError):
        poll(runtime, run, {'jobId': 'wrong'})
    assert runtime.runs[run]['status'] == 'running'
    runtime.handle({'op': 'cancel', 'runId': run})
    with pytest.raises(ValueError):
        poll(runtime, run, wait)
    assert len(runtime.runs[run]['budget'].records) == 1


def test_observe_provenance_dedup_failure_and_limit(tmp_path):
    c = compile_config(config(tmp_path))['stage']
    s = initial_state()
    s, trigger, _ = observe(s, messages(), [], [], 0, c)
    assert trigger is None
    s, trigger, _ = observe(s, messages(1), [], [event('a', 'failed')], 1, c)
    assert trigger == 'first-tool-result'
    s.update(lastJudgeStep=1, batches=1)
    next_state, trigger, _ = observe(s, messages(2), [], [event('a', 'failed'), event('b', 'failed')], 2, c)
    assert trigger is None and next_state['role'] == 'capable'
    assert s['seen'].keys() == {'a'}  # 预览不修改原状态。
    with pytest.raises(ValueError, match='矛盾'):
        observe(s, messages(2), [], [event('a', 'completed')], 2, c)
    s.update(batches=4, frozen=True)
    n, trigger, _ = observe(s, messages(3), [], [event('c', 'failed')], 3, c)
    assert n['role'] == 'capable' and trigger is None
    for status in ('unconfirmed', 'infrastructure'):
        with pytest.raises(ValueError):
            observe(s, messages(3), [], [event('c', status)], 3, c)
    n, trigger, reason = observe(s, messages(3), [], [event('c', 'denied')], 3, c)
    assert trigger is None and reason == 'permission-boundary'


def test_repeated_failure_uses_rule_without_local_judge(tmp_path):
    runtime, run = setup(tmp_path)
    receipt(runtime, run, step(runtime, run, messages()))
    runtime.runs[run]['state']['stageHybrid']['lastJudgeStep'] = 0
    first = step(runtime, run, messages(1), toolEvidence=[event('a', 'failed')])
    assert first['model']['id'] == 'small'
    receipt(runtime, run, first)
    second = step(runtime, run, messages(2), toolEvidence=[event('a', 'failed'), event('b', 'failed')])
    assert second['model']['id'] == 'large'
    assert not runtime.local_service.requests
    assert runtime.runs[run]['decisions'][-1]['reason'] == 'repeated-failure'


def test_unknown_local_answer_uses_strong_tier(tmp_path):
    runtime, run = setup(tmp_path, local_result('UNKNOWN'))
    receipt(runtime, run, step(runtime, run, messages()))
    action = poll(runtime, run, step(runtime, run, messages(1)))
    assert action['model']['id'] == 'large'
    assert runtime.runs[run]['decisions'][-1]['reason'] == 'judge-uncertain'


def test_media_and_missing_cards_never_silently_truncated(tmp_path):
    cfg = compile_config(config(tmp_path))
    history = messages(1)
    history[-1]['content'][0]['content'].append({'type': 'image', 'data': 'x'})
    args = ([], cfg['models']['small'], cfg['models']['large'], 65536)
    assert not decision_request(history, *args)['complete']
    assert not decision_request(messages(1), [], cfg['models']['small'], cfg['models']['large'], 10)['complete']
    assert not decision_request([{'role': 'system', 'content': '规则'}], *args)['complete']


def test_unknown_usage_and_compaction(tmp_path):
    runtime, run = setup(tmp_path)
    receipt(runtime, run, step(runtime, run, messages()))
    before = deepcopy(runtime.runs[run]['state']['stageHybrid'])
    action = step(runtime, run, [{'role': 'user', 'content': '压缩历史'}], purpose='compaction')
    receipt(runtime, run, action)
    assert runtime.runs[run]['state']['stageHybrid'] == before
    action = poll(runtime, run, step(runtime, run, messages(1)))
    with pytest.raises(ValueError):
        receipt(runtime, run, action, usageAvailable=False)
    assert runtime.runs[run]['status'] != 'running'
    assert runtime.runs[run]['budget'].records[-1]['status'] == 'unknown-usage'


def test_selected_strong_unaffordable_does_not_fallback_to_efficient(tmp_path):
    def modify(cfg):
        cfg['models'][1].update(inputPer1k=100, outputPer1k=100)
    runtime, run = setup(tmp_path, local_result('CAPABLE'), modify=modify)
    receipt(runtime, run, step(runtime, run, messages()))
    wait = step(runtime, run, messages(1))
    with pytest.raises(ValueError, match='预算'):
        poll(runtime, run, wait)
    assert len(runtime.runs[run]['budget'].records) == 1
    assert runtime.runs[run]['status'] != 'running'
    decision = runtime.runs[run]['decisions'][-1]
    assert decision['decision']['verdict'] == 'NEED_STRONG'
    assert decision['disposition'] == 'selected-not-dispatched'


def test_task_isolation_and_first_call_ignores_prior_tools(tmp_path):
    runtime, run = setup(tmp_path)
    action = step(runtime, run, messages(2))
    assert action['model']['id'] == 'small' and not runtime.local_service.requests
    other = begin(runtime, turn=2, config=config(tmp_path))
    assert 'stageHybrid' not in runtime.runs[other]['state']
    receipt(runtime, run, action)
    state = runtime.runs[run]['state']['stageHybrid']
    with pytest.raises(ValueError, match='重复'):
        observe(state, messages(2), runtime.runs[run]['budget'].records[0]['request_tools'], [], 1,
                compile_config(config(tmp_path))['stage'])


def test_plain_gateway_runs_local_judge_and_preserves_native_tools(tmp_path, monkeypatch):
    from tests.test_model_gateway import Caller, reply, call, request, follow, gateway, wire_messages
    import refractrouter.tool_runtime as tools
    monkeypatch.setattr(tools, 'run_tool_node', lambda *a, **k: pytest.fail('核心不能执行工具'))
    caller = Caller(reply(calls=[call()]), reply('由强模型完成'))
    gw = gateway(tmp_path / 'api', caller, config(tmp_path))
    gw.runtime.local_service.close()
    gw.runtime.local_service = FakeLocalService(local_result('CAPABLE'))
    req = request('stage')
    first = gw.complete(req)
    final = gw.complete(follow(req, first))
    assert final['choices'][0]['message']['content'] == '由强模型完成'
    assert [a['model']['id'] for a in caller.actions] == ['small', 'large']
    assert wire_messages(caller.actions[-1]['messages'])[-1]['role'] == 'tool'
    assert len(gw.runtime.local_service.requests) == 1
    gw.close()


def test_timeout_stops_without_reissuing_and_receipt_is_idempotent(tmp_path):
    runtime, run = setup(tmp_path)
    first = step(runtime, run, messages())
    receipt(runtime, run, first)
    before = deepcopy(runtime.runs[run]['state'])
    with pytest.raises(ValueError):
        receipt(runtime, run, first)
    assert runtime.runs[run]['state'] == before
    wait = step(runtime, run, messages(1))
    runtime.runs[run]['flow']['localJudge']['deadline'] = 0
    with pytest.raises(ValueError, match='超时'):
        poll(runtime, run, wait)
    assert len(runtime.runs[run]['budget'].records) == 1
    assert len(runtime.local_service.requests) == 1


def test_input_capacity_fallback_does_not_invoke_local_service(tmp_path):
    runtime, run = setup(tmp_path, modify=lambda c: c['stage'].update(maxJudgeInputBytes=512))
    receipt(runtime, run, step(runtime, run, messages()))
    action = step(runtime, run, messages(1))
    assert action['model']['id'] == 'large'
    assert not runtime.local_service.requests
    assert runtime.runs[run]['decisions'][-1]['decision']['usage']['forwards'] == 0


def test_begin_readiness_failure_cannot_be_bypassed_by_same_identity(tmp_path):
    runtime = PlanningRuntime(tmp_path / 'runs')
    runtime.local_service.close()
    class BrokenService(FakeLocalService):
        def call(self, *args, **kwargs):
            raise ValueError('worker crashed')
    runtime.local_service = BrokenService()
    with pytest.raises(ValueError, match='worker crashed'):
        begin(runtime, config=config(tmp_path))
    run = begin(runtime, config=config(tmp_path))
    with pytest.raises(ValueError, match='停止'):
        step(runtime, run, messages())
    assert not runtime.runs[run]['budget'].records
