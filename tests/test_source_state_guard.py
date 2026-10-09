"""以原生误放行措辞及反例检查归属，不把未匹配当成事实已证伪。"""
from dataclasses import replace

import pytest

from refractrouter.source_state_guard import check_source_state
from tests.test_automatic_failure_repairs import launch
from tests.test_live_execution import CompactClient

TASK = '仅依据下面材料检查风险，不要调用工具。回滚应保留会话、provider、凭证和证据。'
BAD = '材料未说明回滚资产是否已捕获并校验，未验证回滚预案的可执行性。'
GOOD = '材料未说明历史验证情况，尚待确认。若未验证回滚预案，应在发布前核对。本次未执行测试。'


@pytest.mark.parametrize('answer', [BAD, '保留完整性未经验证，回滚有风险。',
    '未核对提供方账单（材料未提供）。', '未与实际扣费核对，可能低估费用。',
    '若发生异常，回滚资产未经验证。'])
def test_negative_state_with_no_actor_or_matching_source_is_conservatively_blocked(answer):
    result = check_source_state(TASK, answer)
    assert result['applicable'] and result['passed'] is False
    assert result['findings'][0]['check_id'] == 'negative-verification-attribution'
    assert '需澄清' in result['findings'][0]['reason']  # 没有将来源缺失当作已证实的反面事实。


@pytest.mark.parametrize('answer', [GOOD, '材料未说明是否已经验证，尚待确认。',
    '材料未说明是否未经验证。', '本次未核对提供方账单。', '我未验证回滚预案。',
    '如果回滚预案未经验证，则应核对。', '不要把材料未说明当成回滚未经验证。',
    '不能声称回滚未经验证。'])
def test_material_gaps_explicit_self_reports_conditions_and_warnings_are_allowed(answer):
    assert check_source_state(TASK, answer)['passed']


def test_literal_source_can_support_attribution_but_a_warning_in_source_cannot():
    assert check_source_state(TASK + '回滚预案未验证。', '回滚预案未验证。')['passed']
    assert not check_source_state(TASK + '不能声称回滚预案未验证。', '回滚预案未验证。')['passed']
    assert check_source_state(TASK, '回滚预案未验证。',
        tool_evidence={'records': [{'result': '回滚预案未验证。'}]})['passed']


def test_general_tasks_do_not_gain_an_implicit_material_only_policy():
    result = check_source_state('为项目开发测试。', '系统未经测试。')
    assert result['applicable'] is False and result['passed']


@pytest.mark.parametrize('answer', ['仅依据题面材料审查，本次未调用工具、未修改文件；未核对提供方账单，也未测试。',
    '本次未执行测试，未核对账单。', '我未测试；也未核对账单。'])
def test_explicit_self_report_is_preserved_across_clauses_in_the_same_sentence(answer):
    assert check_source_state(TASK, answer)['passed']


@pytest.mark.parametrize('answer', [
    '本次也未调用工具、未修改文件、未核对账单、未执行测试。',
    '材料未提供账单记录，本次也未核对账单。',
    '我仍未核对账单，也未测试。',
    '本轮实际未执行测试；未核对账单。',
    '本回答暂时未核对账单。',
])
def test_explicit_self_adverbs_and_parallel_verbs_keep_the_same_subject(answer):
    assert check_source_state(TASK, answer)['passed']


@pytest.mark.parametrize('answer', [
    '本次也未核对账单、系统未经验证。',
    '本次未执行测试、回滚预案未验证。',
    '本次也未测试。未核对提供方账单。',
    '系统也未核对账单。',
    '本次未测试，系统已上线，未验证。',
])
def test_parallel_self_reports_do_not_license_a_system_fact_or_new_sentence(answer):
    assert not check_source_state(TASK, answer)['passed']


@pytest.mark.parametrize('answer', ['我未测试。回滚未经验证。',
    '本次未核对账单\n| 回滚 | 未经验证 |',
    '本次未测试，系统未经验证。', '本次未测试，系统未经校验，未验证。'])
def test_self_report_cannot_excuse_other_subjects_sentences_or_table_cells(answer):
    assert not check_source_state(TASK, answer)['passed']


def test_recorded_ambiguous_candidate_is_rejected_before_permissive_judge_and_corrected_once(tmp_path, monkeypatch):
    import tests.test_automatic_failure_repairs as fixtures
    class Client(CompactClient):
        def complete(self, model, messages, **kwargs):
            response = super().complete(model, messages, **kwargs)
            if model.role != 'judge':
                return replace(response, content=GOOD if '纠正尚未交付' in messages[0]['content'] else BAD)
            return response
    client = Client()
    monkeypatch.setattr(fixtures, 'CompactClient', lambda: client)
    result, _ = launch(tmp_path, task=TASK, maxFinalRevisions=1)
    assert result['status'] == 'completed' and result['final_output'] == GOOD
    assert [c['label'] for c in result['calls']] == ['answer', 'final-correction', 'final-judge-correction']
    assert result['final_correction']['initial_source_state_validation']['passed'] is False
    assert result['source_state_validation']['passed'] and result['final_correction']['attempt'] == 1
    assert result['final_correction']['previous_output'] == BAD


def test_bad_repair_stops_without_rereview_or_second_correction(tmp_path, monkeypatch):
    import tests.test_automatic_failure_repairs as fixtures
    class Client(CompactClient):
        def complete(self, model, messages, **kwargs):
            response = super().complete(model, messages, **kwargs)
            return replace(response, content=BAD) if model.role != 'judge' else response
    client = Client()
    monkeypatch.setattr(fixtures, 'CompactClient', lambda: client)
    result, _ = launch(tmp_path, task=TASK, maxFinalRevisions=1)
    assert result['status'] == 'quality-failed' and len(client.calls) == 2
    assert not result['source_state_validation']['passed']
    assert not result['final_correction']['accepted'] and result['final_correction']['attempt'] == 1
    assert result['calls'][-1]['status'] == 'cancelled-before-dispatch'
