"""冻结人工审核的身份、证据、评分与判定回归。"""
from copy import deepcopy
import hashlib
import json

import pytest

from experiments.finalize_real_v0_1 import DIMENSIONS, finalize, prepare_audit


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


@pytest.fixture
def audit_case(tmp_path):
    output = tmp_path / 'final'
    preflight = {'human_audit_task_ids': ['report_011', 'report_020']}
    summary = {'phase': 'final', 'status': 'awaiting-human-audit', 'preflight': preflight,
               'oracle_gate': {'decision': 'Go'}}
    write(output / 'preflight.json', preflight)
    write(output / 'benchmark-summary.json', summary)
    for task in preflight['human_audit_task_ids']:
        for strategy in ('task-oracle', 'node-oracle'):
            write(output / f'runs/{task}/repeat-1/{strategy}.json', {
                'task_id': task, 'strategy': strategy, 'repeat': 1, 'judge_error': None,
                'result': {'task_score': 90, 'final_output': '<html>冻结证据</html>', 'failure_types': []},
                'judge': {'rubric_version': 'v0.1', 'final_score': 90,
                          'claim_support': [{'claim': '冻结主张', 'source_ids': ['source_001']}]}})
    reindex(output)
    audit = prepare_audit(output)
    for row in audit['records']:
        row.update(human_score=90, reviewer='人工审核者', reviewed_at='2026-09-09T08:00:00+08:00',
                   dimensions={**DIMENSIONS, 'analysis_depth': 10}, serious_factual_error=False,
                   evidence_quote='冻结证据', notes='按来源逐条核对，分析维度扣 10 分。')
        row['claim_checks'][0].update(supported=True, notes='已核对来源原文及引用哈希。')
    path = tmp_path / 'audit.json'
    write(path, audit)
    return output, path, audit


def reindex(output):
    write(output / 'evidence-index.json', {'artifacts': {
        str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in output.rglob('*') if p.is_file() and p.name != 'evidence-index.json'}})


def test_review_is_bound_and_preserves_original_files(audit_case):
    output, path, _ = audit_case
    before = {str(p): p.read_bytes() for p in output.rglob('*') if p.is_file()}
    result = finalize(output, path)
    assert result['audit_pass'] and result['final_decision'] == 'Go'
    assert all(c['delta'] == 0 for c in result['comparisons'])
    assert before == {str(p): p.read_bytes() for p in output.rglob('*') if p.is_file()}
    assert (output.with_name('final-human-audit') / 'submitted-audit.json').read_bytes() == path.read_bytes()
    with pytest.raises(ValueError):
        finalize(output, path)


@pytest.mark.parametrize('damage', ['threshold', 'nan', 'infinity', 'bool', 'rubric', 'time',
    'reviewer', 'quote', 'hash', 'missing', 'duplicate', 'dimensions', 'index', 'modified-output'])
def test_invalid_audit_is_rejected_before_writing(audit_case, damage):
    output, path, audit = audit_case
    row = audit['records'][0]
    if damage == 'threshold': audit['agreement_threshold_points'] = 100
    elif damage in {'nan', 'infinity', 'bool'}:
        row['human_score'] = {'nan': float('nan'), 'infinity': float('inf'), 'bool': True}[damage]
    elif damage == 'rubric': audit['rubric_version'] = 'changed'
    elif damage == 'time': row['reviewed_at'] = '2026-09-09'
    elif damage == 'reviewer': row['reviewer'] = ' '
    elif damage == 'quote': row['evidence_quote'] = '不在输出中'
    elif damage == 'hash': row['run_sha256'] = '0' * 64
    elif damage == 'missing': audit['records'].pop()
    elif damage == 'duplicate': audit['records'].append(deepcopy(row))
    elif damage == 'dimensions': row['dimensions']['analysis_depth'] = 20
    elif damage == 'index': audit['evidence_index_sha256'] = '0' * 64
    else:
        p = output / 'runs/report_011/repeat-1/task-oracle.json'
        p.write_text(p.read_text() + ' ')
    write(path, audit)
    with pytest.raises(ValueError): finalize(output, path)
    assert not output.with_name('final-human-audit').exists()


@pytest.mark.parametrize(('score', 'serious', 'decision'), [(80, False, 'Go'), (79, False, 'No-go'), (90, True, 'No-go')])
def test_fixed_threshold_and_serious_fact_errors(audit_case, score, serious, decision):
    output, path, audit = audit_case
    row = audit['records'][0]
    row.update(human_score=score, serious_factual_error=serious,
               dimensions={**DIMENSIONS, 'analysis_depth': max(0, score - 80),
                           'structure_readability': min(15, score - 65)})
    write(path, audit)
    assert finalize(output, path)['final_decision'] == decision


def test_insufficient_evidence_stays_incomplete(audit_case):
    output, path, audit = audit_case
    summary = json.loads((output / 'benchmark-summary.json').read_text())
    summary['oracle_gate']['decision'] = 'Insufficient-evidence'
    write(output / 'benchmark-summary.json', summary)
    reindex(output)
    audit['evidence_index_sha256'] = prepare_audit(output)['evidence_index_sha256']
    write(path, audit)
    assert finalize(output, path)['final_decision'] == 'incomplete'


def test_output_inside_frozen_directory_is_rejected(audit_case):
    output, path, _ = audit_case
    with pytest.raises(ValueError): finalize(output, path, output / 'audit')
