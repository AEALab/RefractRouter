"""不同产物的输出预测及公平 Direct 对照；全程无网络。"""
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from refractrouter.compact_planning import compile_compact
from tests.test_fast_dynamic_dag import compact
from tests.test_live_execution import CompactClient, authorization, config
from refractrouter.agent import run_agent


def test_planner_output_forecasts_preserve_distinct_deliverables_and_old_contract():
    raw = compact(('facts', []), ('answer', ['facts']))
    raw['nodes'][0]['expected_output_tokens'] = 250
    raw['nodes'][1]['expected_output_tokens'] = 1800
    plan = compile_compact(raw, output_cap=2048)
    assert [plan.contracts[n]['capability']['expected_output_tokens'] for n in ('facts', 'answer')] == [250, 1800]
    assert compile_compact(compact(('answer', []))).contracts['answer']['capability']['expected_output_tokens'] == 1000
    for invalid in [0, -1, True, 1.5, '300', 2049]:
        bad = deepcopy(raw)
        bad['nodes'][0]['expected_output_tokens'] = invalid
        with pytest.raises(ValueError, match='expected_output_tokens'):
            compile_compact(bad, output_cap=2048)


@pytest.mark.parametrize('final_tokens', [300, 1600])
def test_direct_final_forecast_matches_final_delivery_without_sum_of_intermediates(tmp_path, final_tokens):
    class ForecastClient(CompactClient):
        def complete(self, model, messages, **kwargs):
            response = super().complete(model, messages, **kwargs)
            if 'DAG 规划器' in messages[0]['content']:
                raw = json.loads(response.content)
                for item in raw['nodes']:
                    item['expected_output_tokens'] = final_tokens if item['id'] == 'answer' else 800
                return replace(response, content=json.dumps(raw))
            return response
    payload = {'task': '分别核对第一项事实和第二项风险，然后汇总建议。', 'strategy': 'auto'}
    preview = run_agent(payload, provider_config=config(), runs_dir=tmp_path/'preview',
        production_budget=10, evaluation_budget=10)
    client = ForecastClient()
    result = run_agent({**payload, 'authorization': authorization(preview['live_authorization_preview'])},
        provider_config=config(), runs_dir=tmp_path/'live', mode='live', execute_paid_run=True,
        client=client, production_budget=10, evaluation_budget=10)
    assert result['status'] == 'completed', result['issues']
    comparison = result['route_comparison']
    assert comparison['output_forecast']['direct_final_tokens'] == final_tokens
    assert comparison['output_forecast']['generated_final_tokens'] == final_tokens
    assert comparison['decision_factors']['quality_basis'] == comparison['quality_evidence_basis'][comparison['route']]
    assert len(client.calls) == 3  # 不新增预测 Judge，不实际派发未选中的 DAG。
