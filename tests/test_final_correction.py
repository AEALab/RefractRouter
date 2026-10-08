"""最终答复纠正的有界闭环、原子保护和故障停机；全部使用无网络回执。"""
from concurrent.futures import CancelledError, ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import json
from threading import Event
import time

import pytest

from refractrouter.final_correction import correct_final
from refractrouter.task_budget import TaskCallBudget, request_input_bound
from tests.test_automatic_failure_repairs import launch
from tests.test_live_execution import CompactClient
from tests.test_native_tool_runtime import Client, real_model, reply, call
from tests.review_fixtures import mock_grounding_checks


class RepairClient(CompactClient):
    def __init__(self, *, second_pass=True, invalid=False, unknown=False):
        super().__init__()
        self.reviews = 0
        self.second_pass, self.invalid, self.unknown = second_pass, invalid, unknown

    def complete(self, model, messages, **kwargs):
        response = super().complete(model, messages, **kwargs)
        if '纠正尚未交付' in messages[0]['content']:
            return replace(response, content='修正版', usage_available=not self.unknown)
        if model.role == 'judge':
            self.reviews += 1
            if self.invalid:
                return replace(response, content='非 JSON 审核')
            verdict = json.loads(response.content)
            passed = self.reviews > 1 and self.second_pass
            verdict.update(passed=passed, score=95 if passed else 55, rationale='已修正' if passed else '原答案未满足要求')
            return replace(response, content=json.dumps(verdict, ensure_ascii=False))
        return replace(response, content='错误答复')


def run_repair(tmp_path, monkeypatch, client=None, **kwargs):
    import tests.test_automatic_failure_repairs as fixtures
    client = client or RepairClient()
    monkeypatch.setattr(fixtures, 'CompactClient', lambda: client)
    result, _ = launch(tmp_path, maxFinalRevisions=1, **kwargs)
    return result, client


def test_reject_correct_review_approve_without_replanning_or_tools(tmp_path, monkeypatch):
    result, client = run_repair(tmp_path, monkeypatch)
    assert result['status'] == 'completed' and result['final_output'] == '修正版'
    assert [r['label'] for r in result['calls']] == ['answer', 'final-judge', 'final-correction', 'final-judge-correction']
    assert all(r['status'] == 'billed' for r in result['calls'])
    repair = result['final_correction']
    assert repair['attempt'] == 1 and repair['accepted'] and repair['status'] == 'accepted'
    assert repair['previous_output'] == '错误答复' and repair['initial_evaluation']['passed'] is False
    assert repair['evaluation']['passed'] is True
    data = json.loads(client.calls[2][1][-1]['content'])
    assert data['review_feedback']['passed'] is False and data['rejected_candidate'] == '错误答复'
    assert len(result['nodes']) == 1 and len(client.calls) == 4
    assert result['calls'][-1]['input_bound_confirmed'] is True


def test_second_rejection_stops_and_retains_all_attempts(tmp_path, monkeypatch):
    result, client = run_repair(tmp_path, monkeypatch, RepairClient(second_pass=False))
    assert result['status'] == 'quality-failed' and len(client.calls) == 4
    assert result['final_correction']['status'] == 'rejected'
    assert result['final_correction']['accepted'] is False
    assert all(r['status'] == 'billed' for r in result['calls'])


def test_approved_first_candidate_does_not_reserve_or_call_correction(tmp_path):
    result, client = launch(tmp_path, maxFinalRevisions=1)
    assert result['status'] == 'completed' and len(client.calls) == 2
    assert 'final_correction' not in result


def test_invalid_first_review_does_not_attempt_repair(tmp_path, monkeypatch):
    result, client = run_repair(tmp_path, monkeypatch, RepairClient(invalid=True))
    assert result['status'] == 'failed' and len(client.calls) == 2
    assert 'final_correction' not in result


def test_unknown_correction_usage_stops_without_review_and_keeps_reserve(tmp_path, monkeypatch):
    result, client = run_repair(tmp_path, monkeypatch, RepairClient(unknown=True))
    assert result['status'] == 'failed' and len(client.calls) == 3
    rows = {r['label']: r for r in result['calls']}
    assert rows['final-correction']['status'] == 'unknown-usage'
    assert rows['final-correction']['charged'] == rows['final-correction']['reserved']
    assert rows['final-judge-correction']['status'] == 'cancelled-before-dispatch'
    assert rows['final-judge-correction']['charged'] == 0


def test_hidden_validator_values_never_sent_to_corrector(tmp_path, monkeypatch):
    hidden = 'hidden-expected-not-in-the-task'
    client = RepairClient()
    client.reviews = 1  # 初次确定性检查拒绝，不派发首次 Judge。
    def validate(answer):
        return {'passed': answer == '修正版', 'expected': hidden, 'actual': answer}
    result, client = run_repair(tmp_path, monkeypatch, client, final_validator=validate)
    assert result['status'] == 'completed' and len(client.calls) == 3
    assert result['deterministic_validation']['passed'] is True
    assert result['final_correction']['initial_deterministic_validation']['passed'] is False
    assert hidden not in json.dumps(client.calls, ensure_ascii=False)
    assert 'deterministic-final-check-failed' not in result['issues']


def test_deterministic_rejection_of_correction_skips_paid_review(tmp_path, monkeypatch):
    result, client = run_repair(tmp_path, monkeypatch, final_validator=lambda a: {'passed': False})
    assert result['status'] == 'quality-failed' and len(client.calls) == 2
    assert result['final_correction']['attempt'] == 1
    assert result['calls'][-1]['status'] == 'cancelled-before-dispatch'


def model():
    return replace(real_model(), context_window=100000, max_output_tokens=2048,
                   input_cost_per_1k=.001, output_cost_per_1k=.001, billing_unit='CNY')


def judge_reply(answer='修正版'):
    from refractrouter.task_evaluation import evaluation_messages
    payload = json.loads(evaluation_messages('仅依据原材料回答。', answer, ['忠实原材料'], evidence_refs=True)[-1]['content'])
    return reply(json.dumps({'score': 95, 'passed': True, 'rationale': '合成正确回执',
        'criteria': [{'criterion_id': key, 'passed': True, 'rationale': '合成检查'} for key in payload['criterion_ids']],
        'grounding_checks': mock_grounding_checks(payload)}, ensure_ascii=False))


def correct(budget, record, **kwargs):
    return correct_final(budget, model(), model(), '仅依据原材料回答。', '原答案',
        {'passed': False, 'score': 50, 'rationale': '需修正'}, ['忠实原材料'], record=record,
        persist=kwargs.pop('persist', lambda: None), execution_deadline=time.monotonic()+60,
        task_deadline=time.monotonic()+90, **kwargs)


def test_path_insufficient_review_budget_prevents_paid_correction():
    client = Client([reply('修正版')])
    budget = TaskCallBudget(client, 1, .001)
    with pytest.raises(ValueError, match='evaluation-budget-exhausted'):
        correct(budget, {})
    assert not client.requests and budget.charged == {'production': 0, 'evaluation': 0}
    assert all(row['status'] == 'cancelled-before-dispatch' for row in budget.records)


def test_path_call_slots_are_protected_before_correction():
    client = Client([reply('修正版')])
    budget = TaskCallBudget(client, 1, 1, max_calls=1)
    with pytest.raises(ValueError, match='study-call-limit-exhausted'):
        correct(budget, {})
    assert not client.requests
    # 未派发的保护释放后，仍可给其他明确请求使用原名额。
    budget.reserve(model(), [], label='other')


def test_cancellation_after_corrector_receipt_bills_call_but_releases_review():
    cancel = Event()
    class CancellingClient(Client):
        def complete(self, *a, **kw):
            result = super().complete(*a, **kw)
            cancel.set()
            return result
    budget = TaskCallBudget(CancellingClient([reply('修正版')]), 1, 1)
    record = {}
    with pytest.raises(CancelledError):
        correct(budget, record, cancel_event=cancel)
    assert record['status'] == 'cancelled' and record['attempt'] == 1
    assert [r['status'] for r in budget.records] == ['billed', 'cancelled-before-dispatch']


def test_correction_tools_are_billed_but_not_executed_or_reviewed():
    client = Client([reply(calls=[call()])])
    budget = TaskCallBudget(client, 1, 1)
    with pytest.raises(ValueError, match='invalid or truncated'):
        correct(budget, {})
    assert len(client.requests) == 1
    assert [r['status'] for r in budget.records] == ['billed', 'cancelled-before-dispatch']


def test_ledger_is_written_with_dispatch_state_before_network_call():
    events = []
    class ObservedClient(Client):
        def complete(self, *a, **kw):
            events.append('model')
            return super().complete(*a, **kw)
    budget = TaskCallBudget(ObservedClient([reply('修正版'), judge_reply()]), 1, 1)
    record = {}
    def persist():
        events.append([(r['status'], record.get('attempt')) for r in budget.records])
    answer, verdict = correct(budget, record, persist=persist)
    assert answer == '修正版' and verdict['passed']
    first_call = events.index('model')
    assert events[first_call-1] == [('unknown-usage', 1), ('reserved', 1)]


def test_evidence_failure_stops_before_call_and_keeps_unconfirmed_dispatch():
    client = Client([reply('修正版')])
    budget = TaskCallBudget(client, 1, 1)
    budget.on_dispatch = lambda _: (_ for _ in ()).throw(OSError('evidence-write-failed'))
    record = {}
    with pytest.raises(OSError):
        correct(budget, record)
    assert not client.requests and budget.stopped
    assert [r['status'] for r in budget.records] == ['unknown-usage', 'cancelled-before-dispatch']


def test_future_envelope_cannot_dispatch_unbound_or_rebind():
    budget = TaskCallBudget(Client([reply('ok')]), 1, 1)
    r = budget.reserve(model(), [], label='future', future_input_bound=5000)
    with pytest.raises(ValueError, match='bound before dispatch'):
        budget.invoke(r)
    budget.bind_future_input(r, [{'role': 'user', 'content': 'actual'}])
    assert r.row['actual_input_bound'] == request_input_bound(r.messages)
    with pytest.raises(ValueError, match='rebound'):
        budget.bind_future_input(r, [])
    budget.invoke(r)
    with pytest.raises(ValueError, match='dispatched'):
        budget.release(r)


def test_unknown_paid_correction_reserve_is_not_released():
    client = Client([replace(reply('修正版'), usage_available=False)])
    budget = TaskCallBudget(client, 1, 1)
    with pytest.raises(ValueError, match='unconfirmed model usage'):
        correct(budget, {})
    assert budget.records[0]['status'] == 'unknown-usage'
    assert budget.records[0]['charged'] == budget.records[0]['reserved'] > 0
    assert budget.records[1]['charged'] == 0


def test_future_input_overflow_has_no_call_and_can_release_protection():
    client = Client([])
    budget = TaskCallBudget(client, 1, 1)
    r = budget.reserve(model(), [], label='future', future_input_bound=1000)
    with pytest.raises(ValueError, match='protected input envelope'):
        budget.bind_future_input(r, [{'role': 'user', 'content': 'x'*2000}])
    budget.release(r)
    assert not client.requests and budget.charged['production'] == 0


def test_parallel_required_paths_never_partially_overspend():
    budget = TaskCallBudget(Client([]), .008, .008)
    def reserve(i):
        try:
            return budget.reserve_many([dict(model=model(), messages=[], label=f'{i}-execute'),
                dict(model=model(), messages=[], label=f'{i}-review', category='evaluation')])
        except ValueError:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        paths = list(pool.map(reserve, range(8)))
    accepted = [p for p in paths if p]
    assert len(accepted) == 3
    assert all(budget.charged[key] <= .008 for key in ('production', 'evaluation'))
    assert sum(r['status'] == 'reserved' for r in budget.records) == len(accepted)*2
