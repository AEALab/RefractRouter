"""辅助评审的冻结、标签隔离、错误结算与三态统计；只使用模拟客户端。"""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from experiments.run_quality_calibration import main
from refractrouter.openai_compatible import ChatResponse
from refractrouter.quality_calibration import build_plan, parse_review, run_calibration


STUDY = Path(__file__).resolve().parents[1] / 'data/quality-study-v1'


class FakeJudge:
    def __init__(self, failure=None):
        self.calls = 0
        self.failure = failure

    def complete(self, model, messages, *, json_mode):
        self.calls += 1
        assert model.max_output_tokens == 2048 and json_mode
        if self.failure == 'network':
            raise ConnectionError('模拟网络错误')
        payload = json.loads(messages[1]['content'])
        result = review(payload['criteria'])
        response = ChatResponse(content=json.dumps(result), input_tokens=100, output_tokens=100,
            cached_input_tokens=0, reasoning_tokens=0, latency_ms=10, attempts=1,
            finish_reason='stop', request_id=f'fake-{self.calls}')
        if self.failure == 'missing-usage':
            return replace(response, usage_available=False)
        if self.failure == 'invalid-json':
            return replace(response, content='not JSON')
        if self.failure == 'truncated':
            return replace(response, finish_reason='length')
        return response


def review(criteria, verdict='pass'):
    return {'verdict': verdict, 'rationale': '模拟测试依据',
            'criteria': [{'criterion': c, 'verdict': verdict, 'rationale': '模拟逐项依据'} for c in criteria]}


def test_preparation_is_offline_and_live_requires_existing_freeze(tmp_path):
    with patch('socket.socket', side_effect=AssertionError('禁止网络')):
        assert main(['--study-dir', str(STUDY), '--output-dir', str(tmp_path / 'prepared')]) == 0
    plan = json.loads((tmp_path / 'prepared/frozen-plan.json').read_text())
    assert plan['max_calls'] == 36
    assert plan['real_model_calls'] == plan['http_retries'] == 0
    assert plan['afp_ceiling'] == pytest.approx(sum(r['afp_ceiling'] for r in plan['requests']))
    assert plan['model']['base_url'].endswith('/api/plan/v3')
    assert plan['call_timeout_sum_seconds'] == 36 * 45
    with pytest.raises(SystemExit):
        main(['--live', '--output-dir', str(tmp_path / 'live')])
    assert not (tmp_path / 'live').exists()


def test_judge_never_receives_author_labels_gold_answers_or_holdout_control():
    plan = build_plan(STUDY)
    tasks = json.loads((STUDY / 'public/tasks.json').read_text())['tasks']
    dev = {t['task_id'] for t in tasks if t['split'] == 'development'}
    for request in plan['requests']:
        payload = json.loads(request['messages'][1]['content'])
        assert not {'case_id', 'author_label', 'author_semantic_label', 'expected_check_status',
                    'author_reference', 'task_id', 'split', 'structure_stratum'} & payload.keys()
        assert not {'task_id', 'split', 'structure_stratum', 'provenance'} & payload['task'].keys()
        if request['kind'] == 'calibration':
            assert request['task_id'] in dev
            assert 'reference_checks' not in payload
        else:
            assert 'candidate_output' not in payload


def test_freeze_mismatch_and_existing_output_prevent_calls(tmp_path):
    plan = build_plan(STUDY)
    changed = deepcopy(plan); changed['requests'][0]['messages'][1]['content'] += 'changed'
    client = FakeJudge()
    with pytest.raises(ValueError, match='frozen calibration plan changed'):
        run_calibration(STUDY, changed, tmp_path / 'changed', client=client)
    assert not (tmp_path / 'changed').exists()
    with pytest.raises(FileExistsError):
        run_calibration(STUDY, plan, tmp_path, client=client)
    assert client.calls == 0


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'overall-pass', 'empty-evidence', 'extra'])
def test_judge_cannot_omit_critical_check_or_override_failure(mutation):
    data = review(['正文正确', '字段正确'])
    if mutation == 'missing':
        data['criteria'].pop()
    elif mutation == 'duplicate':
        data['criteria'][1] = data['criteria'][0]
    elif mutation == 'overall-pass':
        data['criteria'][0]['verdict'] = 'fail'
    elif mutation == 'empty-evidence':
        data['criteria'][0]['rationale'] = '  '
    else:
        data['criteria'].append(data['criteria'][0])
    with pytest.raises(ValueError):
        parse_review(json.dumps(data), ['正文正确', '字段正确'])


def test_duplicate_json_keys_rejected_and_pending_preserved():
    with pytest.raises(ValueError, match='duplicate JSON key'):
        parse_review('{"verdict":"fail","verdict":"pass"}', ['正文正确'])
    data = review(['正文正确'], 'pending')
    assert parse_review(json.dumps(data), ['正文正确'])['verdict'] == 'pending'


def test_real_accounting_and_false_accepts_are_separate_from_human_quality(tmp_path):
    plan = build_plan(STUDY); client = FakeJudge()
    summary = run_calibration(STUDY, plan, tmp_path / 'run', client=client)
    assert client.calls == summary['real_model_calls'] == 36
    assert summary['actual_total_afp'] == pytest.approx(7.2)
    # 总说通过的评审必须暴露全部 6 个误放，不能用字段检查替它掩盖错误。
    assert summary['false_accepts'] == 6
    assert summary['false_rejects'] == 0
    assert summary['independent_human_reviews'] == 0
    assert summary['human_disagreement'] is None
    assert summary['formal_run_ready'] is False
    assert (tmp_path / 'run/review-001.json').is_file()
    assert (tmp_path / 'run/artifact-index.json').is_file()


@pytest.mark.parametrize('failure', ['missing-usage', 'network'])
def test_unknown_usage_stops_batch_and_is_never_zero_cost(tmp_path, failure):
    plan = build_plan(STUDY); client = FakeJudge(failure)
    with pytest.raises((ValueError, ConnectionError)):
        run_calibration(STUDY, plan, tmp_path / 'run', client=client)
    summary = json.loads((tmp_path / 'run/summary.json').read_text())
    assert client.calls == summary['unknown_usage_calls'] == 1
    assert summary['state'] == 'stopped'
    assert summary['actual_total_afp'] is None
    assert summary['unknown_usage_reserved_afp'] > 0
    assert summary['unattempted_requests'] == 35
    assert summary['calibration_against_author_labels']['unacceptable:pending'] == 6


@pytest.mark.parametrize('failure', ['invalid-json', 'truncated'])
def test_billed_invalid_outputs_remain_pending_and_preserve_cost(tmp_path, failure):
    summary = run_calibration(STUDY, build_plan(STUDY), tmp_path / 'run', client=FakeJudge(failure))
    assert summary['real_model_calls'] == summary['invalid_outputs'] == 36
    assert summary['actual_total_afp'] == pytest.approx(7.2)
    assert summary['false_accepts'] == summary['false_rejects'] == 0
    assert summary['calibration_against_author_labels'] == {'acceptable:pending': 12, 'unacceptable:pending': 6}
