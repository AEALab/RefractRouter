"""编码的反例与同图、费用、时序完整性；所有模型响应均为本地模拟。"""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest

from experiments.run_bound_quality_study import RehearsalClient
from refractrouter.pareto_analysis import audit_and_analyze, _break_even
from refractrouter.quality_runtime import prepare, execute
from refractrouter.quality_study import check_output, load_study, digest

STUDY = Path(__file__).resolve().parents[1] / 'data/quality-study-v2'


@pytest.fixture(autouse=True)
def offline():
    with patch('socket.socket', side_effect=AssertionError('测试禁止付费调用')): yield


@pytest.mark.parametrize('edge,encoding,facts', [
    (['签名', '发布'], 'canonical', 'pass'),
    ([['签名', '发布']], 'normalized', 'pass'),
    (['签名通过', '发布'], 'normalized', 'pass'),
    ([['签名通过', '发布']], 'normalized', 'pass'),
    (['发布', '签名'], 'canonical', 'fail'),
    (['发布', '签名通过'], 'normalized', 'fail'),
    (['签名未通过', '发布'], 'invalid', 'unverified'),
    (['签名通过但可跳过', '发布'], 'invalid', 'unverified'),
    ([['签名', '发布'], ['发布', '打包']], 'invalid', 'unverified'),
])
def test_public_encoding_does_not_turn_reverse_edge_into_pass(edge, encoding, facts):
    _, tasks, refs, *_ = load_study(STUDY)
    task = next(t for t in tasks if t['task_id'] == 'rules-02')
    output = deepcopy(refs['rules-02']['author_reference'])
    next(r for r in output['findings'] if r['id'] == 'required_edge')['value'] = edge
    raw = deepcopy(output)
    result = check_output(task, refs['rules-02'], output)
    assert result['encoding']['status'] == encoding
    assert result['fact_status'] == facts
    assert raw == output


def test_boolean_and_node_state_not_coerced_and_old_results_keep_old_contract():
    _, tasks, refs, *_ = load_study(STUDY)
    task = next(t for t in tasks if t['task_id'] == 'analysis-01')
    output = deepcopy(refs[task['task_id']]['author_reference'])
    next(r for r in output['findings'] if r['id'] == 'theft_proven')['value'] = 0
    assert check_output(task, refs[task['task_id']], output)['fact_status'] == 'unverified'
    task = next(t for t in tasks if t['task_id'] == 'rules-02')
    output = deepcopy(refs['rules-02']['author_reference'])
    next(r for r in output['findings'] if r['id'] == 'allowed_now')['value'] = ['签名通过']
    assert check_output(task, refs['rules-02'], output)['encoding']['status'] == 'invalid'
    old_tasks, old_refs = load_study(STUDY.parent/'quality-study-v1')[1:3]
    old = next(t for t in old_tasks if t['task_id'] == 'rules-02')
    output = deepcopy(old_refs['rules-02']['author_reference'])
    next(r for r in output['findings'] if r['id'] == 'required_edge')['value'] = ['签名通过','发布']
    assert check_output(old, old_refs['rules-02'], output)['status'] == 'fail'


def test_audit_reconciles_stages_cold_start_progress_and_rejects_tampering(tmp_path):
    frozen = prepare(STUDY, task_ids=['analysis-02'], arms=['direct-strong', 'shared-single-1', 'shared-single-2',
        'shared-heterogeneous-1', 'shared-heterogeneous-2'], repeats=2)
    messages = []
    result = execute(STUDY, frozen, tmp_path/'run', simulated=True, client=RehearsalClient(STUDY), on_progress=messages.append)
    _, tasks, refs, _, _, manifest = load_study(STUDY)
    report = audit_and_analyze(frozen, result, tasks, refs, manifest)
    assert report['ledger_audit'] == 'verified' and report['actual_model_calls'] == report['actual_afp'] == 0
    assert len(messages) == 10 and len(report['rows']) == 10
    assert sum(r.get('cold_plan_and_execution_ms') is not None for r in report['rows']) == 1
    for r in report['rows']:
        assert r['planning_ms'] + r['execution_ms'] + r['delivery_ms'] == pytest.approx(r['online_ms'])
        assert r['first_progress_emitted_ms'] is not None
    assert not report['confirmed_pareto_frontier'] and not report['human_quality_confirmed']
    mutations = [lambda r: r['calls'][0].update(charged=999),
                 lambda r: r['runs'][0].update(online_finished_ms=0),
                 lambda r: r['calls'][0]['request_messages'][-1].update(content='{"task":{"gold":42}}'),
                 lambda r: next(x for x in r['calls'] if x['stage']=='delivery-judge').update(category='evaluation'),
                 lambda r: r['runs'].append(r['runs'][0])]
    for mutate in mutations:
        altered = deepcopy(result); mutate(altered)
        with pytest.raises(ValueError): audit_and_analyze(frozen, altered, tasks, refs, manifest)
    missing = deepcopy(result); missing['runs'].pop()
    report = audit_and_analyze(frozen, missing, tasks, refs, manifest)
    assert len(report['missing_runs']) == 1
    arm = result['runs'][-1]['arm']
    assert not report['summaries'][arm]['complete']
    assert all(c['performance'] is None for c in report['comparisons'] if arm in (c['candidate'],c['reference']))


def test_break_even_never_promises_reuse_can_fix_negative_online_saving():
    assert _break_even(3, 2, 1) == 3
    assert _break_even(3, 1, 2) is None
    assert _break_even(0, 1, 1) is None
