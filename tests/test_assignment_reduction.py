"""支配消除保留精确路由结果，不通过削减节点或放宽预算解决组合爆炸。"""
import pytest
from refractrouter.node_routing import NodeProfile, route_nodes
from refractrouter.task_plan import validate_plan
from refractrouter.model_selection import Weights


def chain(n):
    return validate_plan({'nodes': [{'node_id': f'n{i}', 'node_type': 'synthesis',
        'parents': [] if i == 0 else [f'n{i-1}'], 'prompt_template': 'Analyze'} for i in range(n)],
        'final_node_id': f'n{n-1}', 'acceptance_criteria': ['Answer']})


def test_eleven_models_six_nodes_do_not_exhaust_search():
    profiles = tuple(NodeProfile(f'm{i:02}', 'synthesis', 80, i + 1, 10, 0) for i in range(11))
    result = route_nodes(chain(6), profiles, method='A', quality_min=80,
        cost_max=10, latency_max_ms=100, reduce_dominated=True)
    assert result['status'] == 'selected'
    assert result['original_combinations'] == 11**6
    assert result['combinations'] == 1
    assert set(result['assignments'].values()) == {'m00'}


@pytest.mark.parametrize('method', ['A', 'B'])
def test_reduction_matches_exhaustive_result_and_normalization(method):
    profiles = tuple(NodeProfile(mid, 'synthesis', quality, cost, latency, 0)
        for mid, quality, cost, latency in [('a',80,1,10),('b',80,2,10),
            ('c',90,3,10),('d',80,1,5),('e',80,1,10)])
    kwargs = dict(method=method, quality_min=80, cost_max=20, latency_max_ms=100,
        weights=Weights(quality=1,cost=1,latency=1) if method=='B' else None)
    exact = route_nodes(chain(3), profiles, **kwargs)
    reduced = route_nodes(chain(3), profiles, reduce_dominated=True, **kwargs)
    for key in ['assignments', 'prediction', 'normalization_bounds', 'scheduled_latency_bounds_ms']:
        assert reduced[key] == exact[key]


def test_distinct_providers_and_latency_are_not_collapsed():
    profiles = (NodeProfile('a','synthesis',80,1,10,0),
                NodeProfile('b','synthesis',80,2,10,0),
                NodeProfile('c','synthesis',80,2,5,0))
    result = route_nodes(chain(2), profiles, method='A', quality_min=80,
        cost_max=10, latency_max_ms=100, reduce_dominated=True,
        model_providers={'a':'first','b':'second','c':'first'})
    assert result['combinations'] == 9


def test_ark_automatic_six_node_plan_completes(tmp_path):
    import json
    from pathlib import Path
    from refractrouter.agent import run_agent
    from refractrouter.ark_plan import application_configuration
    from tests.test_fast_dynamic_dag import Client, compact
    jobs = [(f'n{i}', [] if i == 0 else [f'n{i-1}']) for i in range(6)]
    result = run_agent({'task':'完成六个依赖步骤','template':'auto'},
        provider_config=application_configuration(), client=Client(plan=compact(*jobs)),
        mode='live', execute_paid_run=True, runs_dir=tmp_path)
    assert result['status'] == 'completed', result['issues']
    raw = json.loads((Path(result['run_dir'])/'result.json').read_text())
    assert raw['routing']['original_combinations'] > 100000
    assert raw['routing']['combinations'] <= 100000
    assert len(raw['routing']['assignments']) == 6
