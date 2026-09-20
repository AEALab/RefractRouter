"""MoA 评审接入质量执行与统计管线的确定性测试；模拟 CLI，不发起真实模型调用。"""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from experiments.run_bound_quality_study import RehearsalClient
from experiments.review_moa_failed_calls import failed_calls, retry_records
from refractrouter.moa_review import MOA_POLICY, material_review, output_review, purpose_review
from refractrouter.quality_runtime import execute, moa_gate, prepare
from refractrouter.quality_statistics import analyze
from refractrouter.quality_study import digest, load_study

STUDY = Path(__file__).resolve().parents[1] / 'data/quality-study-v1'


@pytest.fixture(autouse=True)
def offline():
    with patch('socket.socket', side_effect=AssertionError('禁止测试发起网络调用')):
        yield


def review_json(verdict, criteria):
    return json.dumps({'verdict': verdict, 'rationale': '模拟依据',
                       'criteria': [{'criterion': c, 'verdict': verdict,
                                     'rationale': '模拟依据'} for c in criteria]},
                      ensure_ascii=False)


def all_pass_invoke(reviewer, messages, schema=None):
    payload = json.loads(messages[-1]['content'])
    return 0, review_json('pass', payload['criteria']), '', 120.0, 'test-version'


def test_moa_gate_requires_full_consensus_and_bindings():
    _, tasks, refs, *_ = load_study(STUDY)
    selected = [t for t in tasks if t['task_id'] == 'analysis-03']
    frozen = prepare(STUDY, task_ids=['analysis-03'], arms=['direct-cheap'], repeats=1)
    materials = material_review(selected, refs, all_pass_invoke)
    purpose = purpose_review(digest(frozen['statistics_policy']), frozen['task_bindings'],
                             frozen['statistics_policy'], invoke=all_pass_invoke)
    assert moa_gate(frozen, tasks, refs, materials, purpose)
    for bad in ({'task_sha256': 'old'}, {'reference_sha256': 'old'}, {'policy_sha256': 'old'}):
        assert not moa_gate(frozen, tasks, refs, [{**materials[0], **bad}], purpose)
    tampered = deepcopy(materials[0])
    tampered['consensus']['criteria'][0]['verdict'] = 'pending'
    assert not moa_gate(frozen, tasks, refs, [tampered], purpose)
    assert not moa_gate(frozen, tasks, refs, materials, {**purpose, 'statistics_policy_sha256': 'old'})
    assert not moa_gate(frozen, tasks, refs, materials, {**purpose, 'consensus': {'overall': 'pending'}})


def _pending_materials_and_tiebreak(selected, tasks, refs, frozen):
    materials = material_review(selected, refs, all_pass_invoke)
    tampered = deepcopy(materials[0])
    pending_criterion = next(c for c in tampered['consensus']['criteria'])
    pending_criterion['verdict'] = 'pending'
    tid = selected[0]['task_id']
    tiebreak = {'task_id': tid, 'criterion': pending_criterion['criterion'],
                'verdict': 'pass', 'adjudicator': '研究负责人',
                'evidence': '裁决依据：材料本身已能推出该结论，不构成泄漏。',
                'task_sha256': frozen['task_bindings'][tid],
                'reference_sha256': digest(refs[tid])}
    return tampered, tiebreak, tid


def test_moa_gate_accepts_documented_human_tiebreak_for_pending_criterion():
    _, tasks, refs, *_ = load_study(STUDY)
    selected = [t for t in tasks if t['task_id'] == 'analysis-03']
    frozen = prepare(STUDY, task_ids=['analysis-03'], arms=['direct-cheap'], repeats=1)
    purpose = purpose_review(digest(frozen['statistics_policy']), frozen['task_bindings'],
                             frozen['statistics_policy'], invoke=all_pass_invoke)
    tampered, tiebreak, _ = _pending_materials_and_tiebreak(selected, tasks, refs, frozen)
    assert not moa_gate(frozen, tasks, refs, [tampered], purpose)
    assert moa_gate(frozen, tasks, refs, [tampered], purpose,
                    human_tiebreaks=[tiebreak])


@pytest.mark.parametrize('mutate', [
    lambda row: row.update(verdict='pending'),
    lambda row: row.update(adjudicator='Codex'),
    lambda row: row.update(evidence=''),
    lambda row: row.update(task_sha256='old'),
    lambda row: row.update(reference_sha256='old'),
    lambda row: row.update(criterion='不在评审标准内'),
])
def test_moa_gate_rejects_invalid_human_tiebreaks(mutate):
    _, tasks, refs, *_ = load_study(STUDY)
    selected = [t for t in tasks if t['task_id'] == 'analysis-03']
    frozen = prepare(STUDY, task_ids=['analysis-03'], arms=['direct-cheap'], repeats=1)
    purpose = purpose_review(digest(frozen['statistics_policy']), frozen['task_bindings'],
                             frozen['statistics_policy'], invoke=all_pass_invoke)
    tampered, tiebreak, _ = _pending_materials_and_tiebreak(selected, tasks, refs, frozen)
    mutate(tiebreak)
    assert not moa_gate(frozen, tasks, refs, [tampered], purpose,
                        human_tiebreaks=[tiebreak])


def test_execute_accepts_moa_gate_for_heldout_run(tmp_path):
    plan = prepare(STUDY, task_ids=['analysis-03'], arms=['direct-cheap'], repeats=1)
    client = RehearsalClient(STUDY)
    _, tasks, refs, *_ = load_study(STUDY)
    selected = [t for t in tasks if t['task_id'] == 'analysis-03']
    materials = material_review(selected, refs, all_pass_invoke)
    purpose = purpose_review(digest(plan['statistics_policy']), plan['task_bindings'],
                             plan['statistics_policy'], invoke=all_pass_invoke)
    result = execute(STUDY, plan, tmp_path / 'held', client=client,
                     moa_material_reviews=materials, moa_purpose_review=purpose)
    assert result['moa_gate_evidence']['reviewer_identity_verified'] is False
    assert result['runs'] and result['status'] == 'completed'


def _development_fixture():
    _, tasks, refs, *_ = load_study(STUDY)
    selected = [t for t in tasks if t['split'] == 'development'][:2]
    frozen = prepare(STUDY, task_ids=[t['task_id'] for t in selected], arms=['direct-cheap'], repeats=1)
    rows = []
    for spec in frozen['schedule']:
        rows.append({**spec, 'status': 'delivered-unconfirmed', 'quality_status': 'pass',
                     'output': refs[spec['task_id']]['author_reference'], 'cost_known': True,
                     'online_afp': .5, 'offline_afp': .1, 'online_finished_ms': 500})
    result = {'frozen_sha256': digest(frozen), 'simulated': False, 'runs': rows}
    return tasks, refs, selected, frozen, result


def test_analyze_uses_moa_gate_and_output_consensus():
    tasks, refs, selected, frozen, result = _development_fixture()
    materials = material_review(selected, refs, all_pass_invoke)
    purpose = purpose_review(digest(frozen['statistics_policy']), frozen['task_bindings'],
                             frozen['statistics_policy'], invoke=all_pass_invoke)
    moa_outputs = output_review(selected, refs, result['runs'], all_pass_invoke)
    report = analyze(frozen, result, tasks, references=refs,
                     moa_material_reviews=materials, moa_output_reviews=moa_outputs,
                     moa_purpose_review=purpose)
    arm = 'direct-cheap'
    assert report['arms'][arm]['run_counts']['pass'] == len(result['runs'])
    assert report['arms'][arm]['quality_pass_rate'] == 1
    metrics = report['arms'][arm]['accepted_task_metrics']
    assert metrics['quality_gate_status'] == 'active'
    assert metrics['afp_per_accepted_task'] == pytest.approx(.6)
    assert report['moa_review']['gate_status'] == 'active'
    assert report['moa_review']['output_review_bound_runs'] == len(result['runs'])
    assert report['moa_review']['reviewer_identity_verified'] is False
    cost = report['moa_review']['cost']
    assert cost['real_model_calls'] == 2 * len(materials) + 2 * len(moa_outputs) + 2
    assert cost['included_in_ark_afp'] is False and cost['external_usage'] == 'unknown'
    assert not report['quality_gate_pending']
    # 缺少输出评审时不能自动放行：仍为 pending，不把门槛通过当作交付通过。
    report = analyze(frozen, result, tasks, references=refs,
                     moa_material_reviews=materials, moa_purpose_review=purpose)
    assert report['arms'][arm]['run_counts']['pending'] == len(result['runs'])
    assert report['quality_gate_pending']


def test_deterministic_fail_vetoes_moa_pass_consensus():
    tasks, refs, selected, frozen, result = _development_fixture()
    corrupted = deepcopy(result['runs'][0]['output'])
    corrupted['findings'][0]['value'] = '__被篡改的错误答案__'
    result['runs'][0]['output'] = corrupted
    moa_outputs = output_review(selected, refs, result['runs'], all_pass_invoke)
    report = analyze(frozen, result, tasks, references=refs, moa_output_reviews=moa_outputs)
    assert report['arms']['direct-cheap']['run_counts']['fail'] == 1
    assert report['arms']['direct-cheap']['run_counts']['pass'] == len(result['runs']) - 1


def _write_shard(path, records, *, kind='material', policy=None):
    path.write_text(json.dumps({'kind': kind,
                                'policy_sha256': policy or digest(MOA_POLICY),
                                'records': records}, ensure_ascii=False), encoding='utf-8')
    return path


def test_merge_rejects_duplicate_kind_and_policy_mismatch(tmp_path):
    """合流必须拒绝跨分片重复任务与口径不一致的分片，避免门禁读到混合证据。"""
    from experiments.merge_moa_records import merge_records
    policy = digest(MOA_POLICY)
    shard = tmp_path / 'shard.json'
    first = _write_shard(shard, [{'task_id': 'analysis-03'}])
    duplicate = (shard, 'material', policy, [{'task_id': 'analysis-03'}])
    with pytest.raises(SystemExit, match='重复'):
        merge_records([(first, 'material', policy, [{'task_id': 'analysis-03'}]), duplicate],
                      expected_kind='material', expected_policy=policy)
    with pytest.raises(SystemExit, match='策略哈希不符'):
        merge_records([(first, 'material', 'deadbeef', [{'task_id': 'analysis-03'}])],
                      expected_kind='material', expected_policy=policy)
    with pytest.raises(SystemExit, match='分片种类不符'):
        merge_records([(first, 'output', policy, [{'task_id': 'analysis-03'}])],
                      expected_kind='material', expected_policy=policy)


def test_merged_records_are_the_single_gate_input(tmp_path):
    """定向重跑合流后的单一文件必须能直接放行门禁，且缺一题即不放行。"""
    from experiments.merge_moa_records import main as merge_main
    _, tasks, refs, *_ = load_study(STUDY)
    holdout = [t for t in tasks if t['split'] == 'holdout-candidate']
    task_ids = [t['task_id'] for t in holdout]
    frozen = prepare(STUDY, task_ids=task_ids, arms=['direct-cheap'], repeats=1)
    half = len(holdout) // 2
    left = _write_shard(tmp_path / 'material-a.json',
                        material_review(holdout[:half], refs, all_pass_invoke))
    right = _write_shard(tmp_path / 'material-b.json',
                         material_review(holdout[half:], refs, all_pass_invoke))
    output = tmp_path / 'gate'
    merge_main(['--study-dir', str(STUDY), '--source', str(left), '--source', str(right),
                '--task-ids', *task_ids, '--output-dir', str(output)])
    merged = json.loads((output / 'moa-results.json').read_text())
    assert [row['task_id'] for row in merged['records']] == task_ids
    assert merged['summary']['gate_ready'] == len(task_ids)
    assert merged['summary']['not_gate_ready'] == 0
    assert merged['dropped_task_ids'] == []
    assert merged['superseded'] == []
    assert (output / 'README.md').exists() and (output / 'artifact-index.json').exists()
    purpose = purpose_review(digest(frozen['statistics_policy']), frozen['task_bindings'],
                             frozen['statistics_policy'], invoke=all_pass_invoke)
    assert moa_gate(frozen, tasks, refs, merged['records'], purpose) is True
    assert moa_gate(frozen, tasks, refs, merged['records'][:-1], purpose) is False
    tampered = deepcopy(merged['records'])
    tampered[0]['consensus']['criteria'][0]['verdict'] = 'pending'
    assert moa_gate(frozen, tasks, refs, tampered, purpose) is False


def test_merge_supersede_is_explicit_and_audited(tmp_path):
    """单向重审取代旧结论必须显式开启，并在合流件与 README 留痕，不静默覆盖。"""
    from experiments.merge_moa_records import main as merge_main, merge_records
    _, tasks, refs, *_ = load_study(STUDY)
    selected = [t for t in tasks if t['task_id'] == 'analysis-03']
    stale = material_review(selected, refs, all_pass_invoke)[0]
    stale['consensus']['criteria'][0]['verdict'] = 'pending'
    stale['consensus']['overall'] = 'pending'
    fresh = material_review(selected, refs, all_pass_invoke)[0]
    policy = digest(MOA_POLICY)
    old_path = _write_shard(tmp_path / 'material-old.json', [stale])
    new_path = _write_shard(tmp_path / 'material-new.json', [fresh])
    with pytest.raises(SystemExit, match='重复'):
        merge_records([(old_path, 'material', policy, [stale]),
                       (new_path, 'material', policy, [fresh])],
                      expected_kind='material', expected_policy=policy)
    records, superseded = merge_records(
        [(old_path, 'material', policy, [stale]), (new_path, 'material', policy, [fresh])],
        expected_kind='material', expected_policy=policy, allow_supersede=True)
    assert [row['task_id'] for row in records] == ['analysis-03']
    assert records[0]['consensus']['overall'] == 'pass'
    assert superseded == [{'task_id': 'analysis-03', 'previous_source': str(old_path),
                           'previous_overall': 'pending', 'source': str(new_path),
                           'overall': 'pass'}]
    output = tmp_path / 'gate'
    merge_main(['--study-dir', str(STUDY), '--source', str(old_path), '--source', str(new_path),
                '--task-ids', 'analysis-03', '--output-dir', str(output), '--allow-supersede'])
    merged = json.loads((output / 'moa-results.json').read_text())
    assert merged['summary']['gate_ready'] == 1
    assert merged['superseded'][0]['previous_overall'] == 'pending'
    assert '被覆盖的旧记录' in (output / 'README.md').read_text()


def _run_rows_and_records_with_failed_deepseek():
    from refractrouter.moa_review import aggregate, output_messages
    _, tasks, refs, *_ = load_study(STUDY)
    selected = [t for t in tasks if t['task_id'] == 'analysis-03']
    frozen = prepare(STUDY, task_ids=['analysis-03'], arms=['direct-cheap'], repeats=1)
    run_rows = [{'run_id': spec['run_id'], 'task_id': spec['task_id'],
                 'output': refs[spec['task_id']]['author_reference']}
                for spec in frozen['schedule']]
    records = output_review(tasks, refs, run_rows, all_pass_invoke)
    record = records[0]
    deepseek = next(r for r in record['primary'] if r['reviewer_id'] == 'ds-deepseek-v4-pro')
    deepseek.update(status='failed', verdict='pending', review=None,
                    error='review criteria coverage mismatch', wall_time_ms=1000.0)
    _, criteria = output_messages(selected[0], refs['analysis-03']['author_reference'])
    record['consensus'] = aggregate(record['primary'], record['escalation'], criteria)
    return tasks, refs, run_rows, records


def test_retry_records_replaces_failed_calls_and_recomputes_consensus():
    tasks, refs, run_rows, records = _run_rows_and_records_with_failed_deepseek()
    assert len(failed_calls(records)) == 1
    updated, audit = retry_records(tasks, refs, run_rows, records, all_pass_invoke)
    assert audit[0]['new_status'] == ['reviewed'] and audit[0]['overall'] == 'pass'
    record = updated[0]
    assert all(row['status'] == 'reviewed' for row in record['primary'])
    assert record['targeted_review']['replaced_failed_calls'][0]['original']['status'] == 'failed'
    assert record['consensus']['overall'] == 'pass'


def test_retry_records_keeps_record_when_retry_fails_again():
    tasks, refs, run_rows, records = _run_rows_and_records_with_failed_deepseek()

    def failing_invoke(reviewer, messages, schema=None):
        return 1, '', 'simulated failure', 10.0, None
    updated, audit = retry_records(tasks, refs, run_rows, records, failing_invoke)
    assert audit[0]['new_status'] == ['failed']
    assert updated[0]['primary'] == records[0]['primary']
