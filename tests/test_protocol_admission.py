"""显式网关v2只接受所有可能执行候选已配置验收的请求特性。"""
from copy import deepcopy
import json

import pytest

from refractrouter.model_gateway import GATEWAY_CONFIG_V2, ModelGateway, load_gateway_config
from refractrouter.planning_config import compile_config
from refractrouter.protocol_admission import REQUEST_FEATURES, execution_models
from tests.test_model_gateway import Caller, reply, request
from tests.test_planning_routing import configuration


def declared(strategy='static'):
    cfg = configuration(strategy)
    for model in cfg['models']:
        model['capabilities'] = {'toolCalling': 'verified', 'source': '确定性协议夹具', 'checkedAt': '2026-10-30',
            'requestFeatures': {key: 'verified' for key in REQUEST_FEATURES}}
    return cfg


def strict(tmp_path, cfg=None, caller=None):
    return ModelGateway({'schemaVersion': GATEWAY_CONFIG_V2, 'planningRouting': cfg or declared()},
                        tmp_path, caller or Caller(reply()))


@pytest.mark.parametrize('strategy', ['stage', 'task', 'composite', 'escalation'])
def test_unverified_possible_executor_rejects_before_classifier_or_execute(tmp_path, strategy):
    cfg = declared(strategy)
    cfg['models'][1]['capabilities']['requestFeatures']['strictTools'] = 'unknown'
    caller = Caller()
    gw = strict(tmp_path, cfg, caller)
    with pytest.raises(ValueError, match='large.*strictTools'):
        gw.complete(request(strategy))
    assert not caller.actions and not gw.runtime.runs
    gw.close()


def test_advisor_executor_features_are_separate_from_judge(tmp_path):
    cfg = declared('advisor')
    cfg['models'][1]['capabilities'] = cfg['models'][2]['capabilities'] = {}
    caller = Caller(reply('通过候选'), reply(json.dumps({'verdict': 'APPROVE', 'feedback': '通过'})))
    gw = strict(tmp_path, cfg, caller)
    result = gw.complete(request('advisor'))
    assert result['choices'][0]['message']['content'] == '通过候选'
    assert [a['purpose'] for a in caller.actions] == ['execute', 'advisor']
    gw.close()


@pytest.mark.parametrize('options,feature', [
    ({'response_format': {'type': 'json_object'}}, 'jsonObject'),
    ({'response_format': {'type': 'json_schema', 'json_schema': {'name': 'result', 'schema': {'type': 'object'}, 'strict': True}}}, 'jsonSchema'),
    ({'tool_choice': {'type': 'function', 'function': {'name': 'read'}}}, 'toolChoice'),
    ({'parallel_tool_calls': False}, 'parallelToolCalls'),
    ({'prompt_cache_key': 'unchanged'}, 'promptCacheKey'),
])
def test_requested_features_need_independent_candidate_evidence(tmp_path, options, feature):
    cfg = declared()
    cfg['models'][0]['capabilities']['requestFeatures'][feature] = 'declared'
    caller = Caller()
    gw = strict(tmp_path, cfg, caller)
    with pytest.raises(ValueError, match=feature):
        gw.complete({**request(), **options})
    assert not caller.actions and not gw.runtime.runs
    gw.close()


@pytest.mark.parametrize('options', [
    {'temperature': True}, {'top_p': 1.1}, {'parallel_tool_calls': 'false'},
    {'tool_choice': {'type': 'function', 'function': {'name': 'not-declared'}}},
    {'response_format': {'type': 'json_schema', 'json_schema': {'name': 'r', 'schema': []}}},
])
def test_invalid_options_reject_before_any_spend_in_legacy_too(tmp_path, options):
    caller = Caller()
    gw = ModelGateway({'planningRouting': configuration('static')}, tmp_path, caller)
    with pytest.raises(ValueError):
        gw.complete({**request(), **options})
    assert not caller.actions and not gw.runtime.runs
    gw.close()


def test_all_candidate_capacity_is_checked_before_paid_classification(tmp_path):
    cfg = declared('task')
    cfg['models'][1]['contextWindow'] = 2048
    caller = Caller()
    gw = strict(tmp_path, cfg, caller)
    with pytest.raises(ValueError, match='large.*容量'):
        gw.complete(request('task', [{'role': 'user', 'content': 'x' * 1200}]))
    assert not caller.actions and not gw.runtime.runs
    gw.close()


def test_static_random_includes_both_executors_and_legacy_is_explicitly_unverified(tmp_path):
    cfg = declared()
    cfg['parameters'] = {'staticMode': 'random'}
    assert [m.model_id for m in execution_models(compile_config(cfg), 'static')] == ['small', 'large']
    cfg['models'][1]['capabilities']['toolCalling'] = 'unknown'
    gw = strict(tmp_path, cfg)
    assert gw.capabilities('static')['toolTypes'] == []
    with pytest.raises(ValueError, match='large.*function'):
        gw.complete(request())
    gw.close()
    old = ModelGateway({'planningRouting': configuration('static')}, tmp_path / 'old', Caller())
    assert old.capabilities('static')['capabilityAdmission'] == 'legacy-unverified'
    old.close()


def test_v2_loader_and_plain_request_preserve_caller_parameters(tmp_path):
    source = tmp_path / 'gateway.json'
    value = {'schemaVersion': GATEWAY_CONFIG_V2, 'providers': {}, 'planningRouting': declared()}
    source.write_text(json.dumps(value))
    assert load_gateway_config(source) == value
    original = request()
    saved = deepcopy(original)
    caller = Caller(reply())
    gw = strict(tmp_path / 'runs', caller=caller)
    gw.complete(original)
    assert original == saved and len(caller.actions) == 1
    assert gw.capabilities('static')['capabilityAdmission'] == 'all-executor-protocol-admission-v1'
    gw.close()


def test_inflight_gateway_uses_frozen_capabilities_and_effort_after_config_change(tmp_path):
    from tests.test_model_gateway import call, follow
    caller = Caller(reply('', calls=[call()]), reply())
    gw = strict(tmp_path, caller=caller)
    initial = {**request(), 'reasoning_effort': 'low'}
    result = gw.complete(initial)
    gw.planning['models'][0]['capabilities'] = {}
    gw.planning['models'][0]['reasoningEffort'] = 'high'
    gw.complete(follow(initial, result))
    assert len(gw.runtime.runs) == 1 and len(caller.actions) == 2
    assert caller.actions[-1]['model']['reasoning_effort'] == 'low'
    gw.close()


def test_optional_host_neutral_core_guard_uses_all_candidates(tmp_path):
    from refractrouter.planning_runtime import PlanningRuntime
    from tests.test_planning_routing import begin, step
    cfg = declared('stage')
    cfg.update(schemaVersion='refractagent-planning-v8', billingUnit='CNY',
               protocolAdmission='all-executor-protocol-admission-v1')
    for model in cfg['models']:
        model['billingUnit'] = 'CNY'
    cfg['models'][1]['capabilities']['toolCalling'] = 'unknown'
    runtime = PlanningRuntime(tmp_path)
    run_id = begin(runtime, config=cfg)
    with pytest.raises(ValueError, match='large.*function'):
        step(runtime, run_id)
    assert runtime.runs[run_id]['budget'].records == []
    runtime.local_service.close()
