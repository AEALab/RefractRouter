"""同一 DAG 单模型与节点路由共用目标标尺，只改变允许的分配空间。"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from refractrouter.dag_study import load_study, study_preflight
from refractrouter.dag_study_execution import run_study
from refractrouter.model_selection import Weights
from refractrouter.node_routing import NodeProfile, route_nodes
from refractrouter.task_plan import validate_plan
from refractrouter.task_scheduling import ExecutionPolicy
from tests.test_text_tasks import branched_plan

from tests.study_fixtures import current_study

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('method', ['A', 'B'])
def test_uniform_baseline_preserves_normalization_and_constraints(method):
    profiles = tuple(NodeProfile(mid, kind, q, c, t, 3) for mid, kind, q, c, t in [
        ('cheap', 'synthesis', 90, 1, 3), ('strong', 'synthesis', 95, 4, 2),
        ('cheap', 'generation', 85, 6, 8), ('strong', 'generation', 95, 2, 1)])
    args = dict(method=method, quality_min=80, cost_max=100, latency_max_ms=100,
                execution_policy=ExecutionPolicy(2), weights=Weights(0, 1, 0) if method == 'B' else None)
    plan = validate_plan(branched_plan())
    node = route_nodes(plan, profiles, **args)
    single = route_nodes(plan, profiles, assignment_mode='single-model', **args)
    assert node['assignments'] == {'cost': 'cheap', 'risk': 'cheap', 'answer': 'strong'}
    assert set(single['assignments'].values()) == {'cheap'}
    assert node['prediction']['cost'] == 4 and single['prediction']['cost'] == 8
    assert single['normalization_bounds'] == node['normalization_bounds']
    assert single['scheduled_latency_bounds_ms'] == node['scheduled_latency_bounds_ms']
    assert single['execution_policy'] == node['execution_policy']
    assert single['feasible_combinations'] == 2 and node['feasible_combinations'] == 8
    args['cost_max'] = 5
    assert route_nodes(plan, profiles, **args)['status'] == 'selected'
    assert route_nodes(plan, profiles, assignment_mode='single-model', **args)['status'] == 'no-feasible-route'


def test_eight_group_demo_keeps_new_holdouts_separate_and_reports_symmetric_pairs(tmp_path):
    protocol, manifest = current_study(ROOT/'data/benchmarks/dag-routing-v6.json')
    # 当前实现的八组模拟仍检查旧整批首错停止模式；新隔离策略另测。
    protocol.pop('calibration_source')
    protocol['schema_version'] = 'dag-routing-study-v2'
    protocol['failure_policy'] = 'stop-on-first-unavailable-or-invalid-result'
    old = json.loads((ROOT/'data/benchmarks/dag-routing-v3.json').read_text())
    assert not {t['task'] for t in protocol['tasks'] if t['split']=='test'} & {t['task'] for t in old['tasks']}
    assert study_preflight(protocol, manifest)['maximum_calls'] == 516
    protocol['execution_policy']['providerMinIntervalMs']['ark-plan'] = 0
    with patch('socket.socket', side_effect=AssertionError('禁止网络')):
        result = run_study(protocol, manifest, tmp_path/'demo')
    assert result['status'] == 'simulated', result['issues']
    assert len(result['runs']) == 108 and len(result['calls']) == 516
    comparisons = result['comparison']['comparisons']
    assert len(comparisons) == 8
    assert {(c['candidate'], c['baseline']) for c in comparisons} >= {
        ('dag-node-a', 'dag-single-a'), ('dag-node-b', 'dag-single-b')}
    assert all(c['exploratory_signal'] is None for c in comparisons)
    for row in result['runs']:
        if row['method'].startswith('dag-single-'):
            run = json.loads((tmp_path/'demo'/row['result_path']).read_text())
            assert len(set(run['assignments'].values())) == 1
            assert run['routing']['assignment_mode'] == 'single-model'
