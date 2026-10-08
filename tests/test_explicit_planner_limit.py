"""显式规划容量与实际派发一致，保留旧有界模式的默认上限。"""
import json
import pytest

from refractrouter.agent import run_agent
from tests.test_live_execution import CompactClient, authorization, config


@pytest.mark.parametrize('explicit,expected', [(None, 2048), (8192, 8192), (16000, 8192)])
def test_bounded_planning_preserves_explicit_limit_in_preview_and_dispatch(tmp_path, explicit, expected):
    raw = config()
    raw['objective']['dagMode'] = 'force'
    for model in raw['models']:
        model['maxOutputTokens'] = max(model['maxOutputTokens'], 16000)
    payload = {'task': '分别核对第一项事实和第二项风险，然后汇总建议。',
               'boundedCallOutput': True}
    if explicit is not None:
        payload['plannerMaxOutputTokens'] = explicit
    common = dict(provider_config=raw, max_output_tokens=8192,
                  production_budget=100, evaluation_budget=100)
    preview = run_agent(payload, runs_dir=tmp_path/'preview', **common)
    record = json.loads((tmp_path/'preview'/preview['run_id']/'request.json').read_text())
    assert record['runtime_request']['plannerMaxOutputTokens'] == expected
    assert record['runtime_request']['unrestrictedPlanning'] is False
    caps = []
    class Client(CompactClient):
        def complete(self, model, messages, **kwargs):
            if 'DAG 规划器' in messages[0]['content']:
                caps.append(model.max_output_tokens)
            return super().complete(model, messages, **kwargs)
    result = run_agent({**payload, 'authorization': authorization(preview['live_authorization_preview'])},
        runs_dir=tmp_path/'live', mode='live', execute_paid_run=True, client=Client(), **common)
    assert caps == [expected]
    assert result['costs']['unconfirmed'] == 0


def test_bounded_mode_preserves_explicit_timeout_and_task_deadline(tmp_path):
    raw = config()
    raw['objective']['dagMode'] = 'force'
    payload = {'task': '独立核对三个模块并汇总发布建议。', 'boundedCallOutput': True,
               'plannerTimeoutMs': 90000, 'plannerMaxOutputTokens': 8192}
    preview = run_agent(payload, runs_dir=tmp_path, provider_config=raw,
                        max_output_tokens=8192, timeout_ms=300000,
                        production_budget=100, evaluation_budget=100)
    record = json.loads((tmp_path/preview['run_id']/'request.json').read_text())
    assert record['runtime_request']['plannerTimeoutMs'] == 90000
    assert record['runtime_request']['latencyMaxMs'] == 300000
    observed = []
    class Client(CompactClient):
        def for_task_call(self, seconds):
            observed.append(seconds)
            return self
    result = run_agent({**payload, 'authorization': authorization(preview['live_authorization_preview'])},
        runs_dir=tmp_path/'live', provider_config=raw, max_output_tokens=8192,
        production_budget=100, evaluation_budget=100, timeout_ms=300000,
        mode='live', execute_paid_run=True, client=Client())
    assert 80 < observed[0] <= 90
    assert result['costs']['unconfirmed'] == 0


@pytest.mark.parametrize('cap', [True, 0, 255, 128001, 8192.5])
def test_invalid_explicit_limit_stops_before_model_call(tmp_path, cap):
    with pytest.raises(ValueError, match='explicit planner output cap'):
        run_agent({'task': '审查材料', 'boundedCallOutput': True, 'plannerMaxOutputTokens': cap},
                  provider_config=config(), runs_dir=tmp_path)
