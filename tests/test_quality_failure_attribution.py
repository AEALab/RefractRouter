from experiments.analyze_quality_failures import analyze
from refractrouter.moa_review import MOA_POLICY, digest


def _review(run_id, task_id, output, verdict='pass'):
    return {'run_id': run_id, 'task_id': task_id, 'output_sha256': digest(output),
            'policy_sha256': digest(MOA_POLICY), 'consensus': {'overall': verdict}}


def test_failure_layers_and_route_coverage_are_separate():
    task = {'task_id': 't1', 'category': 'rule-checking', 'structure_stratum': 'direct'}
    output = {'answer': 'x', 'findings': []}
    runs = []
    reviews = []
    for arm in ('direct-strong', 'task-selector', 'direct-or-dag'):
        for repeat in range(1, 4):
            run_id = f't1-r{repeat}-{arm}'
            row = {'run_id': run_id, 'task_id': 't1', 'arm': arm, 'repeat': repeat,
                   'status': 'delivered-unconfirmed', 'output': output,
                   'nodes': [{}, {}] if arm == 'direct-or-dag' and repeat == 1 else [{}],
                   'adjudication': {'deterministic': {'status': 'pass', 'checks': []}}}
            runs.append(row)
            reviews.append(_review(run_id, 't1', output))
    final = {'arms': {arm: {'run_counts': {'pass': 3, 'fail': 0, 'pending': 0}}
                      for arm in ('direct-strong', 'task-selector', 'direct-or-dag')}}
    report = analyze({'runs': runs}, [task], reviews, final)
    assert report['arms']['direct-strong']['failure_layer'] == {'pass': 3}
    assert report['arms']['direct-strong']['moa_consensus_all_runs'] == {'pass': 3}
    assert report['routing_behavior']['single_node_runs'] == 2
    assert report['routing_behavior']['multi_node_runs'] == 1


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
        'direct-strong': {'run_counts': {'pass': 3, 'fail': 0, 'pending': 0}},
        'task-selector': {'run_counts': {'pass': 2, 'fail': 1, 'pending': 0}},
        'direct-or-dag': {'run_counts': {'pass': 3, 'fail': 0, 'pending': 0}},
    }}
    report = analyze({'runs': runs}, tasks, reviews, final)
    selected = report['arms']['task-selector']
    assert selected['failure_layer']['deterministic-check'] == 1
    assert selected['deterministic_failed_check_instances'] == {'citation': 1}
