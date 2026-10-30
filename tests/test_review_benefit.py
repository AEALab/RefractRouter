"""以真实核心状态机和模拟回执核对审核成本；不宣称模拟标签是模型资格。"""
from copy import deepcopy
from decimal import Decimal
import json

import pytest

from refractrouter.planning_runtime import PlanningRuntime
from refractrouter.review_benefit import audit, compare
from refractrouter.task_outcomes import digest
from refractrouter.task_results import event
from tests.test_planning_routing import advisor_gate_configuration, escalation_configuration, begin, step, receipt

CRITERIA = digest('模拟全文交付与下一步动作的分用途验收要求')


def trace(directory, strategy, script):
    runtime = PlanningRuntime(directory)
    cfg = escalation_configuration() if strategy == 'escalation' else advisor_gate_configuration()
    run = begin(runtime, strategy, config=cfg)
    expected = {}
    try:
        action = step(runtime, run)
        for purpose, text, gold in script:
            assert action['action'] == 'call' and action['purpose'] == purpose
            if gold is not None:
                expected[action['callId']] = gold
            try:
                action = receipt(runtime, run, action, text)
            except ValueError as exc:
                assert '审核未通过' in str(exc)
                action = {'action': 'stop'}
        assert action['action'] in {'release', 'stop'}
        if runtime.runs[run]['status'] == 'running':
            runtime.handle({'op': 'end', 'runId': run})
        identity = runtime.runs[run]['identity']
        value = runtime.handle({'op': 'outcome', 'runId': run, 'identity': identity})
        annotations = []
        for c in value['candidates']:
            gold = expected[c['candidateId']]
            label = {'candidateId': c['candidateId'], 'candidateSha256': c['candidateSha256'],
                'criteriaSha256': CRITERIA, 'scope': 'complete-delivery-and-requirements',
                'independent': True, 'verdict': gold,
                'method': 'pending' if gold == 'UNKNOWN' else 'explicit-acceptance',
                'recordSha256': digest({'fixture': directory.name, 'candidate': c['candidateSha256'], 'gold': gold})}
            annotations.append(label)
            runtime.task_results.journal.append(digest({k: identity[k] for k in ('session', 'agent')}), run,
                event('independent-' + c['candidateId'], 'feedback',
                    candidate=(c['candidateId'], c['candidateSha256']), source='hidden-evaluation', actor='fixture-oracle',
                    status={'PASS': 'accepted', 'FAIL': 'rejected', 'UNKNOWN': 'unknown'}[gold],
                    artifacts=[digest(label)], criteria=CRITERIA))
        return runtime.handle({'op': 'outcome', 'runId': run, 'identity': identity}), annotations
    finally:
        runtime.local_service.close()


def advisor_repair(directory):
    return trace(directory, 'advisor', [('execute', '错误交付', 'FAIL'),
        ('advisor', json.dumps({'verdict': 'REDO', 'feedback': '修正确定错误'}), None),
        ('redo', '完整交付', 'PASS'), ('advisor', '{"verdict":"APPROVE"}', None)])


def test_repair_counts_all_generation_and_both_reviews_without_double_discard_cost(tmp_path):
    base, base_labels = trace(tmp_path / 'baseline', 'static', [('execute', '错误交付', 'FAIL')])
    result, labels = advisor_repair(tmp_path / 'reviewed')
    report = compare(base, result, baseline_annotations=base_labels, reviewed_annotations=labels, criteria_sha256=CRITERIA)
    row = report['reviewed']
    assert row['quality'] == 'PASS' and row['repairedKnownFailure'] is True
    assert row['reviewedCandidates'] == 2 and row['knownDefectiveReviewed'] == 1
    assert row['falseAllowed'] == 0 and row['discardedFeesAddedAgain'] is False
    parts = {v['group']: Decimal(v['ledgerOccupied']) for v in row['costPartitions']}
    assert parts == {'execution': Decimal('.00028'), 'review': Decimal('.00028')}
    assert Decimal(row['discardedExecutionSubset'][0]['ledgerOccupied']) == Decimal('.00014')
    assert sum(parts.values()) == Decimal(row['costObservation']['costs'][0]['knownCalculated'])
    assert Decimal(report['costs'][0]['savingsFraction']) == -3
    assert report['qualityImproved'] is True and report['netBenefitProven'] is False
    assert row['observations']['p95'] is None


def test_model_approval_and_user_feedback_do_not_replace_full_independent_label(tmp_path):
    result, labels = trace(tmp_path, 'advisor', [('execute', '明确错误', 'FAIL'),
                                               ('advisor', '{"verdict":"APPROVE"}', None)])
    row = audit(result, labels, criteria_sha256=CRITERIA)
    assert row['quality'] == 'FAIL' and row['falseAllowed'] == 1
    unknown = audit(result, [], criteria_sha256=CRITERIA)
    assert unknown['quality'] == 'UNKNOWN' and unknown['reviewedUnknown'] == 1
    assert unknown['unknownAllowed'] == 1


def test_unnecessary_takeover_and_successful_repair_are_different(tmp_path):
    decision = json.dumps({'verdict': 'DEFECT', 'confidence': .99, 'evidenceIds': [], 'reason': '模拟判词'})
    result, labels = trace(tmp_path, 'escalation', [('execute', '正确交付', 'PASS'),
        ('escalation', decision, None), ('takeover', '正确交付', 'PASS')])
    row = audit(result, labels, criteria_sha256=CRITERIA)
    assert row['intervenedCandidates'] == 1 and row['unnecessaryInterventions'] == 1
    assert row['repairedKnownFailure'] is False and row['quality'] == 'PASS'
    assert len(result['calls']) == 3


def test_unresolved_is_failed_delivery_and_still_pays_judge(tmp_path):
    result, labels = trace(tmp_path, 'advisor', [('execute', '待确认', 'UNKNOWN'),
        ('advisor', '{"verdict":"UNRESOLVED"}', None)])
    row = audit(result, labels, criteria_sha256=CRITERIA)
    assert row['quality'] == 'UNKNOWN' and row['unknownAllowed'] == 0
    assert row['costObservation']['pricedCallAmountsComplete'] is True
    assert Decimal(row['costObservation']['costs'][0]['knownCalculated']) == Decimal('.00028')


@pytest.mark.parametrize('change', ['hash', 'scope', 'independent', 'criteria', 'method', 'duplicate', 'no-witness'])
def test_unbound_partial_or_model_only_annotations_cannot_become_gold(tmp_path, change):
    result, labels = trace(tmp_path, 'static', [('execute', '交付', 'PASS')])
    if change == 'hash': labels[0]['candidateSha256'] = '0' * 64
    elif change == 'scope': labels[0]['scope'] = 'selected-fact-fields'
    elif change == 'independent': labels[0]['independent'] = False
    elif change == 'criteria': labels[0]['criteriaSha256'] = '0' * 64
    elif change == 'method': labels[0]['method'] = 'model-majority'
    elif change == 'duplicate': labels.append(deepcopy(labels[0]))
    else: result['events'] = []
    with pytest.raises(ValueError):
        audit(result, labels, criteria_sha256=CRITERIA)


def test_missing_usage_prevents_savings_even_when_known_portion_is_cheap(tmp_path):
    baseline, left = trace(tmp_path / 'base', 'static', [('execute', '完整交付', 'PASS')])
    result, right = advisor_repair(tmp_path / 'route')
    result = deepcopy(result)
    result['calls'][-1]['status'] = 'unknown-usage'
    row = compare(baseline, result, baseline_annotations=left, reviewed_annotations=right, criteria_sha256=CRITERIA)
    assert row['costsComparable'] is False and row['costs'][0]['savingsFraction'] is None
    assert row['reviewed']['costObservation']['unknownCallIds']


@pytest.mark.parametrize('field', ['actual_model', 'input_sha256', 'reasoning_effort'])
def test_pair_rejects_different_execution_model_input_or_effort(tmp_path, field):
    baseline, left = trace(tmp_path / 'base', 'static', [('execute', '完整交付', 'PASS')])
    result, right = advisor_repair(tmp_path / 'route')
    result['calls'][0][field] = 'different'
    with pytest.raises(ValueError, match='配对'):
        compare(baseline, result, baseline_annotations=left, reviewed_annotations=right, criteria_sha256=CRITERIA)
