import pytest

from experiments.analyze_quality_failures import _fixed_dag_evidence, analyze
from refractrouter.moa_review import MOA_POLICY, digest


def _review(run_id, task_id, output, verdict='pass'):
    return {'run_id': run_id, 'task_id': task_id, 'output_sha256': digest(output),
            'policy_sha256': digest(MOA_POLICY), 'consensus': {'overall': verdict}}


def _arm_result(run_counts, accepted=1):
    return {
        'run_counts': run_counts,
        'accepted_task_count': accepted,
        'accepted_task_metrics': {
            'total_afp_all_tasks': 1.0,
            'afp_per_accepted_task': 1.0 if accepted else 0.0,
        },
    }


def test_failure_layers_and_route_coverage_are_separate():
    task = {'task_id': 't1', 'category': 'rule-checking', 'structure_stratum': 'direct'}
    output = {'answer': 'x', 'findings': []}
    runs = []
    reviews = []
    calls = []
    for arm in ('direct-strong', 'task-selector', 'direct-or-dag'):
        for repeat in range(1, 4):
            run_id = f't1-r{repeat}-{arm}'
            row = {'run_id': run_id, 'task_id': 't1', 'arm': arm, 'repeat': repeat,
                   'status': 'delivered-unconfirmed', 'output': output,
                   'nodes': [{}, {}] if arm == 'direct-or-dag' and repeat == 1 else [{}],
                   'adjudication': {'deterministic': {'status': 'pass', 'checks': []}}}
            runs.append(row)
            reviews.append(_review(run_id, 't1', output))
            calls.append({'label': f'{run_id}:answer', 'stage': 'final',
                          'charged': 0.1, 'input_tokens': 10, 'output_tokens': 5})
            if arm == 'direct-or-dag' and repeat == 1:
                calls.append({'label': f'{run_id}:planner', 'stage': 'planner',
                              'charged': 0.02, 'input_tokens': 4, 'output_tokens': 2})
    final = {'arms': {arm: _arm_result({'pass': 3, 'fail': 0, 'pending': 0})
                      for arm in ('direct-strong', 'task-selector', 'direct-or-dag')}}
    report = analyze({'runs': runs, 'calls': calls}, [task], reviews, final)
    assert report['arms']['direct-strong']['failure_layer'] == {'pass': 3}
    assert report['arms']['direct-strong']['moa_consensus_all_runs'] == {'pass': 3}
    assert report['routing_behavior']['single_node_runs'] == 2
    assert report['routing_behavior']['multi_node_runs'] == 1
    assert report['cost_analysis']['identification_limit'].startswith('只有 1 次')
    dag = report['cost_analysis']['actual_multi_node_cases'][0]['comparisons'][2]
    assert dag['routing_execution_afp'] == pytest.approx(0.12)
    assert dag['routing_execution_tokens'] == 21


def test_deterministic_failure_overrides_moa_pass():
    tasks = [{'task_id': 't1', 'category': 'material-analysis',
              'structure_stratum': 'sequential'}]
    output = {'answer': 'x', 'findings': []}
    runs = []
    reviews = []
    for arm in ('direct-strong', 'task-selector', 'direct-or-dag'):
        for repeat in range(1, 4):
            run_id = f't1-r{repeat}-{arm}'
            fail = arm == 'task-selector' and repeat == 1
            checks = [{'check': 'value:sources', 'status': 'fail'}] if fail else []
            runs.append({'run_id': run_id, 'task_id': 't1', 'arm': arm, 'repeat': repeat,
                         'status': 'delivered-unconfirmed', 'output': output, 'nodes': [{}],
                         'adjudication': {'deterministic': {
                             'status': 'fail' if fail else 'pass', 'checks': checks}}})
            reviews.append(_review(run_id, 't1', output))
    final = {'arms': {
        'direct-strong': _arm_result({'pass': 3, 'fail': 0, 'pending': 0}),
        'task-selector': _arm_result({'pass': 2, 'fail': 1, 'pending': 0}, accepted=0),
        'direct-or-dag': _arm_result({'pass': 3, 'fail': 0, 'pending': 0}),
    }}
    report = analyze({'runs': runs}, tasks, reviews, final)
    selected = report['arms']['task-selector']
    assert selected['failure_layer']['deterministic-check'] == 1
    assert selected['deterministic_failed_check_instances'] == {'citation': 1}


def test_fixed_dag_evidence_is_not_counted_as_automatic_split_coverage():
    methods = ('direct-strong', 'dag-strong-serial', 'dag-strong-parallel',
               'dag-calibrated-single', 'dag-node-a', 'dag-node-b',
               'dag-single-a', 'dag-single-b')
    study = {
        'runs': [
            {
                'split': 'test', 'method': method, 'delivered': True, 'score': 95,
                'production_cost': 1.0 if method == 'direct-strong' else 2.0,
                'deployment_cost': 2.0 if method == 'direct-strong' else 3.0,
                'wall_time_ms': 1000 if method == 'direct-strong' else 1500,
            }
            for method in methods
        ],
        'comparison': {'comparisons': []},
    }
    evidence = _fixed_dag_evidence(study)
    assert evidence['fixed_dag_runs'] == 7
    assert evidence['direct_runs'] == 1
    assert evidence['methods']['dag-strong-serial'][
        'production_change_vs_direct_strong'] == pytest.approx(1.0)
    assert '不检验自动规划器' in evidence['scope']
