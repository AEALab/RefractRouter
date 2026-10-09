"""复现真实审核误放行的时间混淆，并区分正确条件、否定与任务合同。"""
from dataclasses import replace

import pytest

from refractrouter.review_time_guard import check_review_time
from tests.test_automatic_failure_repairs import launch
from tests.test_live_execution import CompactClient

TASK = ('仅依据下面材料检查风险。审核最多等待180秒，同时受任务剩余期限约束；'
        '执行阶段给审核预留60秒。')
WRONG = '若任务剩余期限或60秒预留先到期，审核可能被提前截断，实际等不满180秒。'
RIGHT = ('60秒是执行阶段给审核留下的余量；审核最多等待180秒，实际等待还受任务剩余期限约束。'
         '材料未说明历史验证情况，尚待确认。')


@pytest.mark.parametrize('answer', [WRONG, WRONG.replace('60秒', '**60秒**'),
    '审核最多等待60秒。', '由于预留60秒用完，审核将停止。',
    '预留60000毫秒到期后审核中止。'])
def test_source_anchored_reserve_is_not_an_expiring_review_timer(answer):
    result = check_review_time(TASK, answer)
    assert result['applicable'] and result['passed'] is False
    assert result['review_wait_ms'] == 180000 and result['execution_reserve_ms'] == 60000
    assert result['findings'][0]['answer_quote'] in answer


@pytest.mark.parametrize('answer', [RIGHT,
    '若任务剩余期限先到期，审核可能被提前截断。',
    '不能说60秒预留先到期就会使审核截断。',
    '60秒预留不会先到期并使审核截断。',
    '如果实现错误地将预留当作上限，让审核最多等待60秒，应修正实现。',
    '审核最多等待180秒不保证实际等待满180秒。',
    '预留60秒与审核等待180秒用途不同，并不矛盾。'])
def test_correct_time_constraints_negations_and_explicit_misuse_are_allowed(answer):
    assert check_review_time(TASK, answer)['passed']


@pytest.mark.parametrize('task', ['只需核对费用。', '审核最多等待60秒；执行阶段给审核预留60秒。',
    TASK + '另一条合同审核最多等待90秒。'])
def test_missing_equal_or_ambiguous_contract_never_invents_a_constraint(task):
    assert check_review_time(task, '审核最多等待60秒。')['passed']


def test_guard_uses_task_values_instead_of_hard_coding_60_and_180():
    task = TASK.replace('180秒', '90秒').replace('60秒', '30秒')
    assert not check_review_time(task, '审核最多等待30秒。')['passed']
    assert check_review_time(task, '审核最多等待60秒。')['passed']  # 此检查不覆盖其他任意数值错误。


def test_violation_cannot_reach_permissive_judge_before_one_bounded_correction(tmp_path, monkeypatch):
    import tests.test_automatic_failure_repairs as fixtures
    class Client(CompactClient):
        def complete(self, model, messages, **kwargs):
            response = super().complete(model, messages, **kwargs)
            if model.role != 'judge':
                return replace(response, content=RIGHT if '纠正尚未交付' in messages[0]['content'] else WRONG)
            return response  # 模拟总是批准的 Judge 仍不能放行原错误候选。
    client = Client()
    monkeypatch.setattr(fixtures, 'CompactClient', lambda: client)
    result, _ = launch(tmp_path, task=TASK, maxFinalRevisions=1)
    assert result['status'] == 'completed' and result['final_output'] == RIGHT
    assert [row['label'] for row in result['calls']] == ['answer', 'final-correction', 'final-judge-correction']
    record = result['final_correction']
    assert record['initial_time_contract_validation']['passed'] is False
    assert result['time_contract_validation']['passed'] and record['accepted']
    assert record['previous_output'] == WRONG and record['attempt'] == 1
    assert 'review-time-contract-failed' not in result['issues']


def test_unchanged_bad_correction_stops_without_paid_rereview(tmp_path, monkeypatch):
    import tests.test_automatic_failure_repairs as fixtures
    class Client(CompactClient):
        def complete(self, model, messages, **kwargs):
            response = super().complete(model, messages, **kwargs)
            return replace(response, content=WRONG) if model.role != 'judge' else response
    client = Client()
    monkeypatch.setattr(fixtures, 'CompactClient', lambda: client)
    result, _ = launch(tmp_path, task=TASK, maxFinalRevisions=1)
    assert result['status'] == 'quality-failed' and not result['final_correction']['accepted']
    assert len(client.calls) == 2 and result['time_contract_validation']['passed'] is False
    assert result['calls'][-1]['status'] == 'cancelled-before-dispatch'


def test_legacy_contract_is_not_rewritten(tmp_path, monkeypatch):
    import tests.test_automatic_failure_repairs as fixtures
    class Client(CompactClient):
        def complete(self, model, messages, **kwargs):
            response = super().complete(model, messages, **kwargs)
            return replace(response, content=WRONG) if model.role != 'judge' else response
    monkeypatch.setattr(fixtures, 'CompactClient', Client)
    result, _ = launch(tmp_path, task=TASK)
    assert 'time_contract_validation' not in result and 'final_correction' not in result
