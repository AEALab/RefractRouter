"""MoA 双初审聚合的确定性测试；全部使用合成证据，不发起模型调用。"""
import json
from pathlib import Path

import pytest

from experiments.aggregate_moa_consensus import (case_consensus, index_by_case, main,
    read_records, summarize)
from refractrouter.moa_review import digest, output_messages
from refractrouter.quality_study import load_study


STUDY = Path(__file__).resolve().parents[1] / 'data/quality-study-v1'


@pytest.fixture(scope='module')
def study():
    _, tasks, references, controls, *_ = load_study(STUDY)
    return {task['task_id']: task for task in tasks}, references, controls


def review_body(verdict, criteria):
    return {'verdict': verdict, 'rationale': '合成依据',
            'criteria': [{'criterion': criterion, 'verdict': verdict, 'rationale': '合成依据'}
                         for criterion in criteria]}


def evidence(case, task, reviewer_id, verdict):
    messages, criteria = output_messages(task, case['output'])
    return {'reviewer_id': reviewer_id, 'model': 'mock-model', 'thinking_effort': 'high',
            'status': 'reviewed', 'verdict': verdict, 'case_id': case['case_id'],
            'prompt_sha256': digest(messages), 'response_sha256': 'mock-sha256',
            'wall_time_ms': 1.0, 'review': review_body(verdict, criteria)}


def write_evidence(path, records):
    path.write_text(''.join(json.dumps(record, ensure_ascii=False) + '\n' for record in records),
                    encoding='utf-8')
    return path


def test_two_primaries_agree_adopts_verdict(study):
    by_id, references, controls = study
    case = controls[0]
    task = by_id[case['task_id']]
    result = case_consensus(case, task, references[task['task_id']],
                            [evidence(case, task, 'reviewer-a', 'pass'),
                             evidence(case, task, 'reviewer-b', 'pass')])
    assert result['consensus']['overall'] == 'pass'
    assert result['consensus']['escalated_criteria'] == 0
    assert result['disputed_criteria'] == []
    assert result['deterministic_status'] == case['expected_check_status']


def test_disagreement_without_escalation_is_pending(study):
    by_id, references, controls = study
    case = controls[0]
    task = by_id[case['task_id']]
    result = case_consensus(case, task, references[task['task_id']],
                            [evidence(case, task, 'reviewer-a', 'fail'),
                             evidence(case, task, 'reviewer-b', 'pass')])
    assert result['consensus']['overall'] == 'pending'
    rows = result['consensus']['criteria']
    assert all(row['escalated'] and row['verdict'] == 'pending' for row in rows)
    assert result['escalation'] == {}
    assert len(result['disputed_criteria']) == len(rows)
    assert result['final_status'] == 'pending'


def test_escalation_agreement_resolves_dispute(study):
    by_id, references, controls = study
    case = controls[0]
    task = by_id[case['task_id']]
    result = case_consensus(
        case, task, references[task['task_id']],
        [evidence(case, task, 'reviewer-a', 'fail'), evidence(case, task, 'reviewer-b', 'pass')],
        [evidence(case, task, 'escalation-a', 'fail'), evidence(case, task, 'escalation-b', 'fail')])
    assert result['consensus']['overall'] == 'fail'
    assert result['consensus']['escalated_criteria'] == len(result['consensus']['criteria'])
    assert all(row['verdict'] == 'fail' for row in result['consensus']['criteria'])
    assert set(result['escalation']) == {'escalation-a', 'escalation-b'}


def test_prompt_hash_mismatch_is_rejected(study):
    by_id, references, controls = study
    case = controls[0]
    task = by_id[case['task_id']]
    tampered = evidence(case, task, 'reviewer-a', 'pass')
    tampered['prompt_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='prompt hash mismatch'):
        case_consensus(case, task, references[task['task_id']], [tampered])


def test_duplicate_case_evidence_is_rejected(study):
    by_id, references, controls = study
    case = controls[0]
    task = by_id[case['task_id']]
    record = evidence(case, task, 'reviewer-a', 'pass')
    with pytest.raises(ValueError, match='duplicate case evidence'):
        index_by_case([record, dict(record)], 'synthetic')


def test_summary_counts_false_accepts_and_pending(study):
    cases = [
        {'case_id': 'a', 'author_semantic_label': 'unacceptable', 'disputed_criteria': [],
         'consensus': {'overall': 'pass', 'escalated_criteria': 0, 'failed_records': 0},
         'final_status': 'pass', 'primary': {'x': {}}, 'escalation': {},
         'deterministic_status_matches_expectation': True},
        {'case_id': 'b', 'author_semantic_label': 'acceptable', 'disputed_criteria': [],
         'consensus': {'overall': 'fail', 'escalated_criteria': 1, 'failed_records': 1},
         'final_status': 'fail', 'primary': {'x': {}}, 'escalation': {},
         'deterministic_status_matches_expectation': True},
        {'case_id': 'c', 'author_semantic_label': 'unacceptable', 'disputed_criteria': ['甲'],
         'consensus': {'overall': 'pending', 'escalated_criteria': 1, 'failed_records': 0},
         'final_status': 'pending', 'primary': {'x': {'verdict': 'pass'}}, 'escalation': {},
         'deterministic_status_matches_expectation': False},
    ]
    summary = summarize(cases, escalation_state='not-executed', sources=[])
    assert summary['false_accepts'] == 1
    assert summary['false_rejects'] == 1
    assert summary['false_accept_rate'] == 0.5
    assert summary['false_reject_rate'] == 1.0
    assert summary['pending_on_unacceptable'] == 1
    assert summary['deterministic_expectation_mismatches'] == ['c']
    assert summary['disputed'] == [{'case_id': 'c', 'author_semantic_label': 'unacceptable',
                                    'primary': {'x': 'pass'}, 'criteria': ['甲'],
                                    'consensus': 'pending', 'escalation': {}}]


def test_cli_aggregates_full_study_and_indexes_artifacts(study, tmp_path):
    by_id, _references, controls = study
    first = write_evidence(tmp_path / 'first.jsonl',
                           [evidence(case, by_id[case['task_id']], 'reviewer-a', 'pass')
                            for case in controls])
    second = write_evidence(tmp_path / 'second.jsonl',
                            [evidence(case, by_id[case['task_id']], 'reviewer-b', 'pass')
                             for case in controls])
    output = tmp_path / 'consensus-out'
    main(['--study-dir', str(STUDY), '--primary-evidence', str(first),
          '--primary-evidence', str(second), '--output-dir', str(output),
          '--note', '测试用附加说明'])
    summary = json.loads((output / 'summary.json').read_text(encoding='utf-8'))
    assert summary['cases'] == len(controls)
    assert summary['consensus_counts'] == {'pass': len(controls), 'fail': 0, 'pending': 0}
    assert summary['escalation_state'] == 'not-executed'
    assert summary['notes'] == ['测试用附加说明']
    assert summary['policy_sha256']
    readme = (output / 'README.md').read_text(encoding='utf-8')
    assert 'not-executed' in readme and '测试用附加说明' in readme
    assert '无。' in readme
    records = read_records(first)
    assert len(index_by_case(records, 'first')) == len(controls)
    index = json.loads((output / 'artifact-index.json').read_text(encoding='utf-8'))
    assert {'consensus.json', 'summary.json', 'README.md'} <= set(index)


def test_refresh_refuses_unexpected_files(study, tmp_path):
    by_id, _references, controls = study
    evidence_path = write_evidence(tmp_path / 'first.jsonl',
                                   [evidence(case, by_id[case['task_id']], 'reviewer-a', 'pass')
                                    for case in controls])
    output = tmp_path / 'out'
    output.mkdir()
    (output / 'unexpected.txt').write_text('x', encoding='utf-8')
    with pytest.raises(SystemExit):
        main(['--study-dir', str(STUDY), '--primary-evidence', str(evidence_path),
              '--output-dir', str(output), '--refresh'])


def test_cli_rejects_evidence_with_incomplete_case_set(study, tmp_path):
    by_id, _references, controls = study
    partial = write_evidence(tmp_path / 'partial.jsonl',
                             [evidence(controls[0], by_id[controls[0]['task_id']], 'reviewer-a', 'pass')])
    with pytest.raises(SystemExit):
        main(['--study-dir', str(STUDY), '--primary-evidence', str(partial),
              '--output-dir', str(tmp_path / 'out')])
