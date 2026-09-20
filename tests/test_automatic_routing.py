"""v4 两级自动选路：全部使用声明预测，零网络、零模型调用。"""
import json
from pathlib import Path

import pytest

from refractrouter.application_config import compile_configuration
from refractrouter.automatic_routing import CallEnvelope, RouteFeatures, choose_route, first_level_gate

ROOT = Path(__file__).resolve().parents[1]


def configuration(*, quality_min=80, simulated=False):
    raw = json.loads((ROOT / 'data/schema/refractagent-providers-v4-example.json').read_text())
    raw['objective']['qualityMin'] = quality_min
    local = raw['providers'][1]
    local['deployment'] = 'simulated-local' if simulated else 'trusted-cloud'
    local['trustPolicy'] = 'team-cn'
    raw['trustPolicies'] = [{'id': 'team-cn', 'residency': 'CN', 'auditLogging': True,
                             'allowsSensitiveData': True,
                             **({'acknowledgeExternalTransmission': True} if simulated else {})}]
    for model in raw['models']:
        if model['provider'] == 'local':
            model['pricing'] = {'unit': 'USD', 'inputPer1k': .01, 'outputPer1k': .02}
    return compile_configuration(raw)


def parallel_plan():
    return {'nodes': [
        {'node_id': 'facts', 'node_type': 'extraction', 'prompt_template': '提取事实', 'parents': []},
        {'node_id': 'risks', 'node_type': 'verification', 'prompt_template': '核对风险', 'parents': []},
        {'node_id': 'answer', 'node_type': 'synthesis', 'prompt_template': '汇总回答',
         'parents': ['facts', 'risks']},
    ], 'final_node_id': 'answer', 'acceptance_criteria': ['完整回答']}


def node_envelopes(*, grade='S3', fallback=0, continuation=0):
    return {
        'facts': CallEnvelope(1200, 300, grade, fallback_calls=fallback,
                              tool_continuations=continuation),
        'risks': CallEnvelope(1200, 300, grade),
        'answer': CallEnvelope(2200, 700, grade),
    }


def judge(grade='S3', latency=800):
    return CallEnvelope(4000, 500, grade, latency_ms=latency)


def test_first_level_gate_skips_simple_tasks_and_admits_real_signals():
    simple = RouteFeatures(.1, .1, False, 1.1, True, .8, .2)
    assert first_level_gate(simple)['reason'] == 'no-potential-net-benefit'
    parallel = RouteFeatures(.8, .6, False, 1.1, True, .2, .2)
    admitted = first_level_gate(parallel)
    assert admitted['call_planner'] is True and admitted['signals'] == ['parallel-work']
    assert first_level_gate(parallel, dag_mode='never')['call_planner'] is False
    assert first_level_gate(simple, dag_mode='force')['reason'] == 'research-force'


def test_first_level_gate_blocks_risky_split_except_security_placement():
    risky = RouteFeatures(.8, .8, False, 2, False, .8, .8)
    assert first_level_gate(risky)['reason'] == 'structural-risk-blocked'
    security = RouteFeatures(.8, .8, True, 2, False, .9, .9)
    assert first_level_gate(security)['call_planner'] is True


def test_sensitive_direct_route_excludes_external_worker_before_cost_ranking():
    result = choose_route(configuration(), direct=CallEnvelope(5000, 1000, 'S1'),
                          direct_judge=judge('S1'), dag_mode='never')
    assert result['route'] == 'direct'
    assert result['direct']['model_id'] == 'local-router'
    assert result['excluded_candidates']['direct_worker']['security-placement'] == 1
    assert result['direct']['calls']['worker']['deployment'] == 'trusted-cloud'


def test_quality_gate_can_make_every_route_infeasible_without_dispatch():
    result = choose_route(configuration(quality_min=99), direct=CallEnvelope(5000, 1000),
                          direct_judge=judge(), dag_mode='never')
    assert result['status'] == 'infeasible' and result['route'] == 'infeasible'
    assert result['direct'] is None and result['dag'] is None


def test_direct_wins_when_planning_and_repeated_context_remove_dag_savings():
    result = choose_route(configuration(), direct=CallEnvelope(5000, 1200), plan=parallel_plan(),
        nodes={nid: CallEnvelope(5000, envelope.output_tokens) for nid, envelope in node_envelopes().items()},
        planner=CallEnvelope(5000, 800), direct_judge=judge(), dag_judge=judge(), max_concurrency=2)
    assert result['route'] == 'direct' and result['reason'] == 'direct-cost-not-worse'
    assert result['dag']['marginal_cost'] > result['direct']['marginal_cost']


def test_planner_probe_is_charged_to_both_routes_after_plan_evaluation():
    direct_only = choose_route(configuration(), direct=CallEnvelope(5000, 1200),
                               direct_judge=judge(), dag_mode='never')
    compared = choose_route(configuration(), direct=CallEnvelope(5000, 1200), plan=parallel_plan(),
        nodes=node_envelopes(), planner=CallEnvelope(500, 300),
        direct_judge=judge(), dag_judge=judge())
    probe = compared['direct']['calls']['planner_probe']
    assert compared['direct']['marginal_cost'] == pytest.approx(
        direct_only['direct']['marginal_cost'] + probe['marginal_cost'])
    assert compared['direct']['latency_ms'] == pytest.approx(
        direct_only['direct']['latency_ms'] + probe['latency_ms'])
    assert compared['dag']['calls']['planner'] == probe


def test_dag_wins_only_after_full_cost_and_critical_path_accounting():
    result = choose_route(configuration(), direct=CallEnvelope(100000, 4000), plan=parallel_plan(),
        nodes=node_envelopes(fallback=1, continuation=1), planner=CallEnvelope(500, 300),
        direct_judge=judge(), dag_judge=judge(), max_concurrency=2, cost_risk_margin=.001)
    assert result['route'] == 'dag' and result['reason'] == 'lower-total-cost-after-risk'
    dag = result['dag']
    assert dag['calls']['nodes']['facts']['calls'] == 3
    assert dag['cost_with_risk_margin'] == pytest.approx(dag['marginal_cost'] + .001)
    node_latency_sum = sum(row['latency_ms'] for row in dag['calls']['nodes'].values())
    assert dag['critical_path']['makespan_ms'] < node_latency_sum
    assert set(dag['assignments']) == {'facts', 'risks', 'answer'}


def test_cost_risk_margin_can_keep_direct_as_the_default():
    base = choose_route(configuration(), direct=CallEnvelope(100000, 4000), plan=parallel_plan(),
        nodes=node_envelopes(), planner=CallEnvelope(500, 300),
        direct_judge=judge(), dag_judge=judge(), max_concurrency=2)
    saving = base['direct']['marginal_cost'] - base['dag']['marginal_cost']
    guarded = choose_route(configuration(), direct=CallEnvelope(100000, 4000), plan=parallel_plan(),
        nodes=node_envelopes(), planner=CallEnvelope(500, 300),
        direct_judge=judge(), dag_judge=judge(), max_concurrency=2,
        cost_risk_margin=saving + .001)
    assert base['route'] == 'dag'
    assert guarded['route'] == 'direct'


def test_quality_risk_margin_above_scale_makes_dag_infeasible():
    result = choose_route(configuration(quality_min=90), direct=CallEnvelope(5000, 1000),
        plan=parallel_plan(), nodes=node_envelopes(), planner=CallEnvelope(500, 300),
        direct_judge=judge(), dag_judge=judge(), quality_risk_margin=11)
    assert result['route'] == 'direct'
    assert result['dag'] is None
    assert result['excluded_candidates']['dag_workers']['facts']['quality'] == 2


@pytest.mark.parametrize('field', ['planner', 'direct_judge', 'dag_judge'])
def test_auxiliary_envelopes_cannot_downgrade_sensitive_material(field):
    values = {'direct': CallEnvelope(5000, 1000, 'S1'), 'plan': parallel_plan(),
              'nodes': node_envelopes(grade='S1'), 'planner': CallEnvelope(500, 300, 'S1'),
              'direct_judge': judge('S1'), 'dag_judge': judge('S1')}
    values[field] = CallEnvelope(500, 300, 'S3', latency_ms=800)
    with pytest.raises(ValueError, match='cannot downgrade'):
        choose_route(configuration(), **values)


def test_simulated_local_records_zero_marginal_and_nonzero_cloud_bill_separately():
    result = choose_route(configuration(simulated=True), direct=CallEnvelope(5000, 1000, 'S1'),
                          direct_judge=judge('S1'), dag_mode='never')
    worker = result['direct']['calls']['worker']
    assert worker['model_id'] == 'local-router'
    assert worker['marginal_cost'] == 0
    assert worker['actual_cloud_cost'] > 0


def test_direct_and_dag_judge_envelopes_are_accounted_separately():
    result = choose_route(configuration(), direct=CallEnvelope(100000, 4000), plan=parallel_plan(),
        nodes=node_envelopes(), planner=CallEnvelope(500, 300),
        direct_judge=CallEnvelope(4000, 500, latency_ms=800),
        dag_judge=CallEnvelope(9000, 500, latency_ms=800))
    assert result['direct']['calls']['judge']['input_tokens_per_call'] == 4000
    assert result['dag']['calls']['judge']['input_tokens_per_call'] == 9000


def test_force_mode_fails_closed_when_no_dag_is_available():
    result = choose_route(configuration(), direct=CallEnvelope(5000, 1000),
                          direct_judge=judge(), dag_mode='force')
    assert result['status'] == 'infeasible'
    assert result['reason'] == 'forced-dag-unavailable-or-infeasible'


@pytest.mark.parametrize('mutate', [
    lambda row: row.update(input_tokens=-1),
    lambda row: row.update(cached_input_tokens=101),
    lambda row: row.update(grade='secret'),
    lambda row: row.update(latency_ms=0),
])
def test_invalid_call_envelopes_fail_closed(mutate):
    row = {'input_tokens': 100, 'output_tokens': 10}
    mutate(row)
    with pytest.raises(ValueError):
        CallEnvelope(**row)
