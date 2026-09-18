"""judge 判例匯出器的确定性回归；只读写本地合成存档，不发起模型调用。"""
import hashlib
import json
from unittest.mock import patch

import pytest

from experiments.export_judge_replay import export


def _messages(payload):
    return [
        {'role': 'system', 'content': '你是评审。'},
        {'role': 'user', 'content': payload},
    ]


def _call(run_id, stage, payload, *, model_id='judge-kimi', category='production',
          charged=1.5, status='ok', with_messages=True):
    call = {
        'label': run_id + ':' + stage,
        'model_id': model_id,
        'category': category,
        'status': status,
        'charged': charged,
        'input_tokens': 100,
        'output_tokens': 20,
        'reasoning_tokens': 0,
        'input_sha256': 'in-' + stage,
        'output_sha256': 'out-' + stage,
        'request_id': 'req-' + stage,
        'response_output': '{"verdict": "pass"}',
    }
    if with_messages:
        call['request_messages'] = _messages(payload)
    return call


def _review(verdict, criteria):
    return {
        'verdict': verdict,
        'criteria': [{'criterion': name, 'verdict': value} for name, value in criteria],
    }


def _row(run_id, *, delivery, research, task_id='task-1', arm='direct-strong', repeat=1):
    return {
        'run_id': run_id,
        'task_id': task_id,
        'arm': arm,
        'repeat': repeat,
        'task_sha256': 'sha-' + run_id,
        'delivery_review': delivery,
        'research_review': research,
    }


def _session(rows, calls, schema='bound-quality-results-v1'):
    return {'schema_version': schema, 'runs': rows, 'calls': calls}


def _write(tmp_path, session):
    source = tmp_path / 'batch'
    source.mkdir(parents=True, exist_ok=True)
    (source / 'session.json').write_text(
        json.dumps(session, ensure_ascii=False, indent=2) + '\n')
    return source


def _cases(out):
    return json.loads((out / 'cases.json').read_text())['cases']


@pytest.fixture(autouse=True)
def offline():
    with patch('socket.socket', side_effect=AssertionError('本测试不得发起付费调用')):
        yield


def _paired(run_id, payload='same-payload', *, delivery_verdict='pass',
            research_verdict='pass', delivery_criteria=(('依赖顺序', 'pass'),),
            research_criteria=(('依赖顺序', 'pass'),), charged=1.5):
    return (
        _row(run_id,
             delivery=_review(delivery_verdict, delivery_criteria),
             research=_review(research_verdict, research_criteria)),
        [_call(run_id, 'delivery-judge', payload, charged=charged),
         _call(run_id, 'research-judge', payload, charged=charged)],
    )


def test_identical_payload_is_digested_and_flagged(tmp_path):
    payload = '{"task": "t", "candidate_output": "o", "criteria": []}'
    row, calls = _paired('run-1', payload)
    out = tmp_path / 'out'
    summary = export(_write(tmp_path, _session([row], calls)), out)

    assert summary['case_count'] == 1
    assert summary['identical_request_between_judges'] == 1
    case = _cases(out)[0]
    assert case['request']['identical_between_judges'] is True
    assert case['request']['payload_sha256'] == hashlib.sha256(payload.encode()).hexdigest()
    assert case['request']['messages'] == calls[0]['request_messages']


def test_different_payload_is_reported_as_not_identical(tmp_path):
    row, calls = _paired('run-1')
    calls[1] = _call('run-1', 'research-judge', 'other-payload')
    summary = export(_write(tmp_path, _session([row], calls)), tmp_path / 'out')

    assert summary['identical_request_between_judges'] == 0
    assert _cases(tmp_path / 'out')[0]['request']['identical_between_judges'] is False


def test_missing_judge_call_is_skipped_and_reason_counted(tmp_path):
    good_row, good_calls = _paired('run-1')
    bad_row, bad_calls = _paired('run-2')
    session = _session([good_row, bad_row], good_calls + bad_calls[:1])
    out = tmp_path / 'out'
    summary = export(_write(tmp_path, session), out)

    assert summary['case_count'] == 1
    assert summary['skipped'] == {'missing-research-judge': 1}
    assert [case['case_id'] for case in _cases(out)] == ['run-1']


def test_rows_without_request_messages_or_run_id_are_skipped(tmp_path):
    good_row, good_calls = _paired('run-1')
    no_messages, calls_a = _paired('run-2')
    calls_a[0] = _call('run-2', 'delivery-judge', 'p', with_messages=False)
    nameless_row, calls_b = _paired('run-3')
    nameless_row.pop('run_id')
    summary = export(_write(tmp_path, _session(
        [good_row, no_messages, nameless_row], good_calls + calls_a + calls_b)),
        tmp_path / 'out')

    assert summary['case_count'] == 1
    assert summary['skipped'] == {'missing-request-messages': 1, 'missing-run-id': 1}


def test_agreement_statistics_use_recorded_reviews(tmp_path):
    rows, calls = [], []
    for run_id, verdicts, criteria in [
        ('run-1', ('pass', 'pass'), (('依赖顺序', 'pass'), ('回归完整', 'pass'))),
        ('run-2', ('fail', 'pass'), (('依赖顺序', 'fail'), ('回归完整', 'pass'))),
        ('run-3', ('pass', 'pass'), (('依赖顺序', 'pass'), ('回归完整', 'pass'))),
    ]:
        row, pair = _paired(run_id, delivery_verdict=verdicts[0], research_verdict=verdicts[1],
                            delivery_criteria=criteria, research_criteria=criteria)
        rows.append(row)
        calls.extend(pair)

    summary = export(_write(tmp_path, _session(rows, calls)), tmp_path / 'out')

    assert summary['verdict_pairs'] == {'fail -> pass': 1, 'pass -> pass': 2}
    assert summary['verdict_agreement'] == 0.666667
    assert summary['criterion_pairs'] == {
        'fail -> fail': 1, 'pass -> pass': 5}
    assert summary['criterion_agreement'] == 1.0


def test_criterion_only_on_one_side_counts_as_disagreement(tmp_path):
    row, calls = _paired('run-1', delivery_criteria=(('依赖顺序', 'pass'),),
                         research_criteria=(('回归完整', 'pass'),))
    summary = export(_write(tmp_path, _session([row], calls)), tmp_path / 'out')

    assert summary['criterion_pairs'] == {'None -> pass': 1, 'pass -> None': 1}
    assert summary['criterion_agreement'] == 0.0


def test_cost_is_aggregated_by_stage_and_model(tmp_path):
    row, calls = _paired('run-1', charged=2.0)
    calls[1]['model_id'] = 'judge-kimi'
    calls[1]['charged'] = 3.0
    summary = export(_write(tmp_path, _session([row], calls)), tmp_path / 'out')

    assert summary['replayed_afp_by_stage'] == {'delivery-judge': 2.0, 'research-judge': 3.0}
    assert summary['replayed_afp_by_model'] == {'judge-kimi': 5.0}


def test_cases_are_sorted_and_keep_row_metadata(tmp_path):
    rows, calls = [], []
    for run_id in ['run-b', 'run-a']:
        row, pair = _paired(run_id)
        row['arm'] = 'direct-or-dag'
        row['repeat'] = 2
        rows.append(row)
        calls.extend(pair)
    out = tmp_path / 'out'
    export(_write(tmp_path, _session(rows, calls)), out)

    cases = _cases(out)
    assert [case['case_id'] for case in cases] == ['run-a', 'run-b']
    assert cases[0]['arm'] == 'direct-or-dag'
    assert cases[0]['repeat'] == 2
    assert cases[0]['task_sha256'] == 'sha-run-a'
    assert cases[0]['recorded']['delivery-judge']['category'] == 'production'


def test_unknown_schema_and_missing_lists_are_rejected(tmp_path):
    row, calls = _paired('run-1')
    with pytest.raises(ValueError, match='schema'):
        export(_write(tmp_path, _session([row], calls, schema='something-else')), tmp_path / 'out')

    source = tmp_path / 'broken'
    source.mkdir()
    (source / 'session.json').write_text(json.dumps({'schema_version': 'pareto-development-report-v1'}))
    with pytest.raises(ValueError, match='runs'):
        export(source, tmp_path / 'out')


def test_missing_session_file_is_rejected(tmp_path):
    empty = tmp_path / 'empty'
    empty.mkdir()
    with pytest.raises(ValueError, match='session.json'):
        export(empty, tmp_path / 'out')
