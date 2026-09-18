"""replay_cheap_judge 的确定性测试；不发起任何模型调用。"""
import json

import pytest

from experiments.replay_cheap_judge import _arm_of, _estimate_afp, summarize


def _case(case_id, recorded_verdicts, recorded_criteria, tokens=(800, 300)):
    case = {
        'case_id': case_id,
        'task_id': 't',
        'repeat': 1,
        'recorded': {
            ref: {'verdict': recorded_verdicts[ref], 'criteria': recorded_criteria[ref],
                  'input_tokens': tokens[0], 'output_tokens': tokens[1]}
            for ref in ('delivery-judge', 'research-judge')
        },
    }
    return case


def _record(case, verdict, criteria):
    refs = ('delivery-judge', 'research-judge')
    return {
        'case_id': case['case_id'],
        'ark': {
            'verdicts': {ref: case['recorded'][ref]['verdict'] for ref in refs},
            'criteria': {ref: case['recorded'][ref]['criteria'] for ref in refs},
        },
        'verdict': verdict,
        'criteria': criteria,
        'estimated_afp': _estimate_afp(case),
        'wall_time_ms': 10.0,
    }


THRESHOLDS = {
    'verdict_agreement_min': 0.9,
    'criterion_agreement_min': 0.9,
    'risk_direction_max': 0.05,
}


def test_arm_of():
    assert _arm_of('rules-02-r1-shared-single-2') == 'shared-single-2'
    assert _arm_of('analysis-01-r2-direct-strong') == 'direct-strong'


def test_estimate_afp():
    case = {'recorded': {'delivery-judge': {'input_tokens': 1000, 'output_tokens': 500}}}
    assert _estimate_afp(case) == pytest.approx(0.075)


def test_summarize_excludes_reference_disagreements():
    # 9 例两个 Ark judge 互相矛盾 → 单列不計；剩下的样例低于门槛 → keep
    cases = []
    records = []
    for i in range(10):
        disagree = i < 9
        delivery = 'pass'
        research = 'fail' if disagree else 'pass'
        ark = {'delivery-judge': delivery, 'research-judge': research}
        case = _case('c%d' % i, ark, {ref: {'c': 'pass'} for ref in ark})
        verdict = 'fail' if i == 9 else 'pass'
        records.append(_record(case, verdict, {'c': verdict}))
    summary = summarize(records, THRESHOLDS)
    assert summary['excluding_reference_disagreements'] == 9
    assert summary['reference_disagreement_cases'] == ['c%d' % i for i in range(9)]
    assert summary['decision'] == 'keep'


def test_summarize_pending_stays_in_denominator():
    # 10 例一致；其中 1 例候选输出 pending，仍需在分母里计为不一致
    cases = []
    records = []
    for i in range(10):
        ark = {'delivery-judge': 'pass', 'research-judge': 'pass'}
        case = _case('c%d' % i, ark, {ref: {'c': 'pass'} for ref in ark})
        verdict = 'pending' if i == 0 else 'pass'
        records.append(_record(case, verdict, {'c': verdict}))
    summary = summarize(records, THRESHOLDS)
    stats = summary['by_reference']['delivery-judge']
    assert stats['verdict_agreement'] == 9 / 10
    assert stats['verdict_agreement_ok'] is True
    assert summary['decision'] == 'replace'


def test_summarize_risk_direction_blocks_replace():
    # 一致性够，但 Ark fail 候选 pass 比例超过上限 → keep
    cases = []
    records = []
    for i in range(10):
        delivery = 'fail' if i < 2 else 'pass'
        ark = {'delivery-judge': delivery, 'research-judge': delivery}
        case = _case('c%d' % i, ark, {ref: {'c': delivery} for ref in ark})
        # 候选对 Ark 判 fail 的两例仍判 pass，制造危险方向风险
        records.append(_record(case, 'pass', {'c': 'pass'}))
    summary = summarize(records, THRESHOLDS)
    assert summary['by_reference']['delivery-judge']['risk_direction'] == 2 / 10
    assert summary['by_reference']['delivery-judge']['risk_direction_ok'] is False
    assert summary['decision'] == 'keep'

