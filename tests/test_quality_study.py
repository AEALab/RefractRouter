"""防止答案泄漏、虚假验收及未支持的检查被当作质量通过。"""
from copy import deepcopy
import json
from pathlib import Path
import re
from unittest.mock import patch

import pytest

from experiments.preflight_quality_study import main
from refractrouter.quality_study import (adjudicate, calibrate, check_output, digest,
    execution_payload, load_study, make_blind_packet, material_review_packet,
    preflight, strategy_counts,
    validate_materials)

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / 'data/quality-study-v1'


@pytest.fixture
def bundle():
    return load_study(STUDY)


def test_zero_network_preflight_and_conservative_envelopes():
    with patch('socket.socket', side_effect=AssertionError('禁止网络')):
        result = preflight(STUDY)
    assert result['real_model_calls'] == 0
    assert result['formal_run_ready'] is False
    assert result['independent_review_records'] == 0
    assert result['material_independence_verified'] is False
    assert result['source_kinds'] == {'constructed': 18}
    assert len(result['envelopes']) == 12
    assert len(result['schedule']) == 18 * 3 * 12
    assert len({r['output_relative_path'] for r in result['schedule']}) == 18 * 3 * 12
    arms = {r['arm_id']: r for r in result['envelopes']}
    direct = arms['direct-cheap']
    # One final, one online delivery judge, one offline research judge.
    assert direct['maximum_online_calls'] == 2
    assert direct['maximum_research_calls'] == 1
    assert direct['online_afp_ceiling'] == pytest.approx(2.048 + 34.816)
    assert direct['research_afp_ceiling'] == pytest.approx(34.816)
    assert direct['online_timeout_sum_ms'] == 140000
    dynamic = arms['direct-or-dag']
    assert dynamic['maximum_online_calls'] == 9
    assert dynamic['maximum_research_calls'] == 1
    assert result['totals']['holdout-candidate']['runs'] == 432
    assert result['calibration']['expectation_mismatches'] == []
    assert result['calibration']['detected_negative_cases'] == 5
    assert result['calibration']['unresolved_negative_cases'] == 2
    assert result['calibration']['false_rejections_on_author_positives'] == 0
    assert result['calibration']['human_disagreement'] is None


def test_correct_fields_do_not_override_wrong_final_prose(bundle):
    _, tasks, refs, controls, *_ = bundle
    t = next(t for t in tasks if t['task_id'] == 'rules-02')
    bad = next(c['output'] for c in controls if c['case_id'] == 'prose-contradiction')
    result = adjudicate(t, refs[t['task_id']], bad)
    assert result['deterministic']['status'] == 'pass'
    assert result['status'] == 'pending'


def test_candidate_holdout_cannot_be_used_to_tune_evaluator(bundle):
    _, tasks, refs, controls, *_ = bundle
    holdout = next(t for t in tasks if t['split'] == 'holdout-candidate')
    controls = deepcopy(controls)
    controls[0]['task_id'] = holdout['task_id']
    controls[0]['output'] = refs[holdout['task_id']]['author_reference']
    with pytest.raises(ValueError, match='cannot calibrate'):
        calibrate(tasks, refs, controls)


def test_planner_projection_excludes_reference_and_stratum(bundle):
    _, tasks, refs, *_ = bundle
    t = deepcopy(tasks[0]); t['reference_answer'] = 'SECRET_REFERENCE'
    t['review'] = {'verdict': 'SECRET_REVIEW'}
    payload = execution_payload(t)
    encoded = json.dumps(payload)
    assert 'SECRET' not in encoded
    assert not {'task_id', 'split', 'structure_stratum', 'provenance', 'reference_answer', 'review'} & payload.keys()
    payload['materials'][0]['text'] = 'changed'
    assert t['materials'][0]['text'] != 'changed'
    assert refs[t['task_id']]['author_reference'] not in payload.values()


def test_unsupported_checker_stays_unverified(bundle):
    _, tasks, refs, *_ = bundle
    t = tasks[0]; ref = deepcopy(refs[t['task_id']]); ref['checks'][0]['op'] = 'llm-says-good'
    result = adjudicate(t, ref, ref['author_reference'])
    assert result['deterministic']['status'] == 'unverified'
    assert result['status'] == 'pending'


def human(t, output, name='reviewer-A', verdict='pass', stage='initial'):
    return {'origin': 'human', 'reviewer': name, 'verdict': verdict, 'stage': stage,
            'criteria': t['semantic_criteria'], 'evidence': 'fixture://review-record',
            'task_sha256': t['task_sha256'], 'output_sha256': digest(output)}


def test_human_records_bound_to_output_and_independent_identities(bundle):
    _, tasks, refs, *_ = bundle
    t = tasks[0]; ref = refs[t['task_id']]; output = ref['author_reference']
    a = human(t, output); b = human(t, output, 'reviewer-B')
    assert adjudicate(t, ref, output, [a, b])['status'] == 'pass'
    assert adjudicate(t, ref, output, [a, a])['status'] == 'pending'
    for mutation in [{'origin': 'model'}, {'reviewer': 'Codex'}, {'evidence': ''},
                     {'output_sha256': 'wrong'}, {'criteria': []}]:
        invalid = {**b, **mutation}
        assert adjudicate(t, ref, output, [a, invalid])['status'] == 'pending'
    b['verdict'] = 'fail'
    assert adjudicate(t, ref, output, [a, b])['status'] == 'pending'
    c = human(t, output, 'reviewer-C', 'fail', 'adjudication')
    assert adjudicate(t, ref, output, [a, b, c])['status'] == 'fail'
    assert not adjudicate(t, ref, output, [a, b, c])['reviewer_identity_verified']


def test_critical_failure_cannot_be_outvoted(bundle):
    _, tasks, refs, *_ = bundle
    t = tasks[0]; ref = refs[t['task_id']]; output = deepcopy(ref['author_reference'])
    output['findings'][0]['value'] = 999
    reviews = [human(t, output, n) for n in ['A', 'B']]
    assert adjudicate(t, ref, output, reviews)['status'] == 'fail'


@pytest.mark.parametrize('value,expected', [(60.0, 'pass'), (True, 'fail'), (float('nan'), 'fail')])
def test_numeric_representation_and_boolean_not_interchangeable(bundle, value, expected):
    _, tasks, refs, *_ = bundle
    t = tasks[0]; ref = refs[t['task_id']]; output = deepcopy(ref['author_reference'])
    output['findings'][0]['value'] = value
    assert check_output(t, ref, output)['status'] == expected


def test_false_and_zero_not_interchangeable(bundle):
    _, tasks, refs, *_ = bundle
    t = tasks[0]; ref = refs[t['task_id']]; output = deepcopy(ref['author_reference'])
    output['findings'][-1]['value'] = 0
    assert check_output(t, ref, output)['status'] == 'fail'


def test_wrong_edge_direction_and_duplicate_fields_fail(bundle):
    _, tasks, refs, *_ = bundle
    t = next(t for t in tasks if t['task_id'] == 'rules-02'); ref = refs[t['task_id']]
    output = deepcopy(ref['author_reference']); output['findings'][-1]['value'].reverse()
    assert check_output(t, ref, output)['status'] == 'fail'
    output = deepcopy(ref['author_reference']); output['findings'].append(output['findings'][0])
    assert check_output(t, ref, output)['status'] == 'fail'


def test_failures_and_pending_remain_in_denominator():
    result = strategy_counts(['pass', 'pending', 'fail'])
    assert result['total'] == 3 and result['confirmed_pass_rate'] == 1 / 3
    assert result['noninferiority'] == 'not-assessed'
    with pytest.raises(ValueError):
        strategy_counts([])


def test_split_family_overlap_detected_after_legitimate_rehash(bundle):
    protocol, tasks, refs, *_ = deepcopy(bundle)
    holdout = next(t for t in tasks if t['split'] == 'holdout-candidate')
    holdout['template_family'] = tasks[0]['template_family']
    holdout['task_sha256'] = digest({k: v for k, v in holdout.items() if k != 'task_sha256'})
    refs[holdout['task_id']]['task_sha256'] = holdout['task_sha256']
    with pytest.raises(ValueError, match='crosses splits'):
        validate_materials(tasks, refs, protocol)


def test_blind_metadata_and_private_mapping(bundle):
    _, tasks, refs, *_ = bundle
    records = [{'task_id': tasks[0]['task_id'], 'arm_id': 'SECRET_ARM', 'model_id': 'SECRET_MODEL',
                'output': refs[tasks[0]['task_id']]['author_reference']}]
    packet, mapping = make_blind_packet(records, tasks, refs)
    assert 'SECRET' not in json.dumps(packet)
    assert mapping['case-0001']['arm_id'] == 'SECRET_ARM'
    assert packet[0]['review']['verdict'] is None
    assert packet[0]['review']['review_time_ms'] is None
    assert all(row['review']['review_time_ms'] is None for row in material_review_packet(tasks, refs))


def test_cli_is_zero_call_and_cannot_overwrite(tmp_path):
    args = ['--output-dir', str(tmp_path / 'run')]
    with patch('socket.socket', side_effect=AssertionError('禁止网络')):
        assert main(args) == 0
        with pytest.raises(FileExistsError):
            main(args)
        with pytest.raises(SystemExit):
            main(args + ['--live'])
    assert (tmp_path / 'run/private-blind-mapping.json').exists()


def test_file_mutation_rejected(tmp_path):
    import shutil
    # Preserve relative manifest layout for the independent copy.
    copy = tmp_path / 'data/quality-study-v1'
    shutil.copytree(STUDY, copy)
    shutil.copytree(ROOT / 'data/model-manifests', tmp_path / 'data/model-manifests')
    (copy / 'review/references.json').write_text('{}')
    with pytest.raises(ValueError, match='artifact hash mismatch'):
        load_study(copy)


def test_order_fields_use_ordered_comparison():
    """有序字段必须使用有序比较：无序集合比较会放过顺序错误的候选。"""
    _, tasks, refs, *_ = load_study(STUDY)
    ordered = [(t['task_id'], c['field'], c['op']) for t in tasks
               for c in refs[t['task_id']]['checks']
               if 'order' in c['field'] or 'sequence' in c['field']]
    assert ordered, '全库应至少存在一个有序检查，避免断言真空'
    assert [row for row in ordered if row[2] != 'equal'] == []


def test_permuted_order_candidate_fails_decision_06():
    """decision-06 回归：打乱顺序的候选必须判 fail，且只报 order 一项。"""
    _, tasks, refs, *_ = load_study(STUDY)
    task = next(t for t in tasks if t['task_id'] == 'decision-06')
    reference = refs['decision-06']
    assert check_output(task, reference, reference['author_reference'])['status'] == 'pass'
    permuted = deepcopy(reference['author_reference'])
    next(f for f in permuted['findings'] if f['id'] == 'order')['value'] = [
        '部署', '备份', '回归检查', '校验备份']
    result = check_output(task, reference, permuted)
    assert result['status'] == 'fail'
    assert [row['check'] for row in result['checks'] if row['status'] == 'fail'] == ['order']


def test_task_and_reference_semantic_criteria_stay_in_sync():
    """材料评审读 task 的 semantic_criteria；两侧不同步会放过语义缺陷。"""
    _, tasks, refs, *_ = load_study(STUDY)
    assert [t['task_id'] for t in tasks
            if t['semantic_criteria'] != refs[t['task_id']]['semantic_criteria']] == []


def test_decision_03_quote_qualifies_every_room_accessibility():
    """decision-03 回归：硬条件是无障碍通道，报价不得用「有通道」这类未声明简写。"""
    _, tasks, refs, *_ = load_study(STUDY)
    task = next(t for t in tasks if t['task_id'] == 'decision-03')
    quote = next(m for m in task['materials'] if m['source_id'] == 's2')['text']
    rooms = re.findall(r'[A-D]可容\d+人、([^、]+)、\d+元', quote)
    assert len(rooms) == 4
    assert [room for room in rooms if '无障碍通道' not in room] == []


def test_decision_03_rejects_only_hard_condition_failures():
    """把合格但更贵的 D 计入 rejected_ids 必须判 fail；参考答案本身必须通过。"""
    _, tasks, refs, *_ = load_study(STUDY)
    task = next(t for t in tasks if t['task_id'] == 'decision-03')
    reference = refs['decision-03']
    assert check_output(task, reference, reference['author_reference'])['status'] == 'pass'
    wrong = deepcopy(reference['author_reference'])
    next(f for f in wrong['findings'] if f['id'] == 'rejected_ids')['value'] = ['B', 'C', 'D']
    result = check_output(task, reference, wrong)
    assert result['status'] == 'fail'
    assert [row['check'] for row in result['checks'] if row['status'] == 'fail'] == ['rejected_ids']
