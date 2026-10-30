"""审核路线的独立标签与完整费用审计；不修改策略、不派发模型。"""
from collections import defaultdict
from decimal import Decimal

from .purpose_review import wire
from .task_cost_observation import observe, amount
from .task_outcomes import digest

VERSION = 'review-benefit-audit-v1'
EXECUTION = {'execute', 'redo', 'takeover', 'compaction'}
REVIEWS = {'advisor', 'escalation'}


def _hash(value):
    if type(value) is not str or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('必须绑定完整SHA-256')
    return value


def _labels(result, annotations, criteria):
    """接受受信离线评估器的材料；摘要绑定不认证裁定者或证明其语义正确。"""
    _hash(criteria)
    if type(annotations) is not list:
        raise ValueError('独立裁定必须为列表')
    candidates = {c['candidateId']: c for c in result['candidates']}
    rows = {}
    events = [r['event'] for r in result['events']]
    superseded = {e.get('supersedes') for e in events if e.get('supersedes')}
    for label in annotations:
        if type(label) is not dict or set(label) != {
            'candidateId', 'candidateSha256', 'criteriaSha256', 'scope', 'independent',
            'verdict', 'method', 'recordSha256'
        }:
            raise ValueError('独立裁定字段不完整')
        token = label['candidateId']
        if type(token) is not str or token not in candidates or token in rows:
            raise ValueError('裁定候选未知或重复')
        _hash(label['recordSha256'])
        call = next((c for c in result['calls'] if c.get('call_id') == token), {})
        scope = ('candidate-next-action' if call.get('finish_reason') == 'tool_calls'
                 else 'complete-delivery-and-requirements')
        if (label['candidateSha256'] != candidates[token]['candidateSha256']
                or label['criteriaSha256'] != criteria or label['independent'] is not True
                or label['scope'] != scope):
            raise ValueError('独立裁定范围、候选或评分版本不符')
        verdict, method = label['verdict'], label['method']
        if (type(verdict) is not str or verdict not in {'PASS', 'FAIL', 'UNKNOWN'}
                or type(method) is not str or method not in {
                    'explicit-acceptance', 'source-counterexample', 'human-decision', 'pending'}
                or (verdict == 'UNKNOWN') != (method == 'pending')
                or method == 'source-counterexample' and verdict != 'FAIL'):
            raise ValueError('裁定不能由模型多数票或局部通过替代')
        expected = {'PASS': 'accepted', 'FAIL': 'rejected', 'UNKNOWN': 'unknown'}[verdict]
        witnesses = [e for e in events if e['kind'] == 'feedback' and e['source'] == 'hidden-evaluation'
                     and e['eventId'] not in superseded and e.get('candidateId') == token
                     and e.get('candidateSha256') == label['candidateSha256']
                     and e.get('criteriaVersion') == criteria]
        if (not witnesses or {e['status'] for e in witnesses} != {expected}
                or not any(digest(label) in e.get('artifactSha256', []) for e in witnesses)):
            raise ValueError('裁定未写入独立评估通道或存在冲突')
        rows[token] = verdict
    return rows


def audit(result, annotations, *, criteria_sha256):
    wire(annotations)
    costs = observe(result)
    if result.get('strategy') not in {'static', 'advisor', 'escalation'}:
        raise ValueError('审核净收益只比较固定执行与单独Advisor或Escalation')
    labels = _labels(result, annotations, criteria_sha256)
    calls = result['calls']
    candidates = {c['candidateId']: c for c in result['candidates']}
    execution = [r for r in calls if r.get('purpose') in EXECUTION]
    decisions = [d for d in result['decisions'] if d.get('candidateCallId') in candidates]
    reviewed, allowed, intervened = set(), set(), set()
    positions = {r.get('call_id'): i for i, r in enumerate(calls)}
    episodes = []
    unresolved_attribution = []
    review_calls = [r for r in calls if r.get('purpose') in REVIEWS
                    and r.get('status') != 'cancelled-before-dispatch']
    unmapped_reviews = []
    review_ids = {r['call_id'] for r in review_calls}
    for review in review_calls:
        request_id = review.get('host_request_id')
        preceding = [r for r in execution if r.get('call_id') in candidates and request_id
                     and r.get('host_request_id') == request_id
                     and positions[r['call_id']] < positions[review['call_id']]]
        if preceding:
            reviewed.add(preceding[-1]['call_id'])
        else:
            unmapped_reviews.append(review['call_id'])
    for d in decisions:
        token, reason = d['candidateCallId'], d.get('reason', '')
        if reason.startswith(('advisor-', 'escalation-')):
            reviewed.add(token)
            # STALL 未达确认次数也会真正放行；按实际处置统计，不能只识别批准判词。
            if candidates[token]['routerDisposition'] == 'accepted':
                allowed.add(token)
            if candidates[token]['routerDisposition'] == 'discarded':
                source = next((c for c in calls if c.get('call_id') == token), {})
                request_id = source.get('host_request_id')
                boundary = max(positions.get(token, -1), positions.get(d.get('callId'), -1))
                bound_review = (d.get('callId') in review_ids
                                and positions[d['callId']] > positions.get(token, -1))
                attempts = [r for r in execution if bound_review and r.get('purpose') in {'redo', 'takeover'}
                    and request_id and r.get('host_request_id') == request_id
                    and positions[r['call_id']] > boundary]
                if attempts:
                    intervened.add(token)
                    attempt = attempts[0]
                    repaired = (labels.get(token) == 'FAIL' and labels.get(attempt['call_id']) == 'PASS'
                                and attempt.get('finish_reason') == 'stop')
                    episodes.append({'sourceCandidateId': token, 'reviewCallId': d.get('callId'),
                        'actionCallId': attempt['call_id'], 'action': attempt['purpose'],
                        'sourceQuality': labels.get(token, 'UNKNOWN'),
                        'actionQuality': labels.get(attempt['call_id'], 'UNKNOWN'),
                        'repairedCandidate': repaired,
                        'outcomeUnknown': attempt.get('finish_reason') != 'stop'
                                          or labels.get(attempt['call_id'], 'UNKNOWN') == 'UNKNOWN'})
                elif reason not in {'advisor-unresolved'}:
                    unresolved_attribution.append(token)
    accepted = [r for r in execution if r.get('disposition') == 'accepted'
                and r.get('purpose') != 'compaction']
    final = accepted[-1] if accepted and accepted[-1].get('finish_reason') == 'stop' else None
    final_label = labels.get(final['call_id'], 'UNKNOWN') if final and result['status'] == 'completed' else 'UNKNOWN'
    first = next((r for r in execution if r.get('purpose') == 'execute'), None)
    initial_label = labels.get(first['call_id'], 'UNKNOWN') if first else 'UNKNOWN'
    partitions, discarded = defaultdict(Decimal), defaultdict(Decimal)
    for row in calls:
        if row.get('status') == 'local-inference':
            continue
        lane = 'subscription-reference' if row['billing_mode'] == 'subscription' else 'metered-budget'
        key = lane, row['billing_unit']
        purpose = row['purpose']
        group = 'execution' if purpose in EXECUTION else 'review' if purpose in REVIEWS else 'other-managed'
        partitions[(*key, group)] += amount(row['charged'])
        if purpose in EXECUTION and row.get('disposition') == 'discarded':
            discarded[key] += amount(row['charged'])
    return {'schemaVersion': VERSION, 'runId': result['runId'], 'strategy': result['strategy'],
        'sourceResultSha256': digest(result), 'criteriaSha256': criteria_sha256,
        'costObservation': costs,
        'costPartitions': [{'lane': lane, 'unit': unit, 'group': group, 'ledgerOccupied': str(value)}
                           for (lane, unit, group), value in sorted(partitions.items())],
        'discardedExecutionSubset': [{'lane': lane, 'unit': unit, 'ledgerOccupied': str(value)}
                                     for (lane, unit), value in sorted(discarded.items())],
        'discardedFeesAddedAgain': False,
        'quality': final_label, 'initialCandidateQuality': initial_label,
        'routerFinalSelected': final is not None and result['status'] == 'completed',
        'transportDelivery': 'unknown',
        'reviewAttempts': len(review_calls),
        'reviewWithoutDecisionCallIds': [r['call_id'] for r in review_calls
            if r['call_id'] not in {d.get('callId') for d in decisions}],
        'unmappedReviewCallIds': unmapped_reviews,
        'reviewedCandidates': len(reviewed), 'reviewedUnknown': sum(labels.get(t, 'UNKNOWN') == 'UNKNOWN' for t in reviewed),
        'knownDefectiveReviewed': sum(labels.get(t) == 'FAIL' for t in reviewed),
        'falseAllowed': sum(labels.get(t) == 'FAIL' for t in allowed),
        'unknownAllowed': sum(labels.get(t, 'UNKNOWN') == 'UNKNOWN' for t in allowed),
        'intervenedCandidates': len(intervened),
        'unnecessaryInterventions': sum(labels.get(t) == 'PASS' for t in intervened),
        'interventionUnknown': sum(labels.get(t, 'UNKNOWN') == 'UNKNOWN' for t in intervened),
        'repairEpisodes': episodes, 'unresolvedInterventionAttribution': sorted(set(unresolved_attribution)),
        'repairOutcomeUnknown': sum(e['outcomeUnknown'] for e in episodes),
        'attemptedRepairOfKnownFailure': any(e['sourceQuality'] == 'FAIL' for e in episodes),
        'repairedKnownFailure': final_label == 'PASS' and any(e['repairedCandidate'] for e in episodes),
        'observations': {'taskTiming': result.get('timing'), 'calls': [{
            k: r.get(k) for k in ('call_id', 'purpose', 'latency_ms', 'ttft_ms', 'userFirstTextMs', 'deliveryMode')}
            for r in calls], 'p95': None, 'scope': 'raw-observations-not-latency-improvement-proof'},
        'toolBoundary': 'final-review-cannot-undo-host-actions',
        'actualProviderDebit': 'unknown-unless-independently-reconciled',
        'productionEnabled': False, 'modelCalls': 0}


def compare(baseline, reviewed, *, baseline_annotations, reviewed_annotations, criteria_sha256):
    """同执行模型/首输入的完整配对；独立来源与宿主快照仍由冻结研究负责。"""
    if baseline.get('strategy') != 'static' or reviewed.get('strategy') not in {'advisor', 'escalation'}:
        raise ValueError('必须以相同执行模型的无审核路线作主要对照')
    def first(result):
        return next((r for r in result['calls'] if r.get('purpose') == 'execute'), None)
    a, b = first(baseline), first(reviewed)
    if not a or not b or any(a.get(k) != b.get(k) for k in (
            'provider', 'actual_model', 'input_sha256', 'request_options_sha256', 'caller_output_cap', 'reasoning_effort')):
        raise ValueError('配对执行模型、输入或合同不同')
    left = audit(baseline, baseline_annotations, criteria_sha256=criteria_sha256)
    right = audit(reviewed, reviewed_annotations, criteria_sha256=criteria_sha256)
    def lanes(value):
        return {(r['lane'], r['unit']): r for r in value['costObservation']['costs']}
    l, r = lanes(left), lanes(right)
    comparable = set(l) == set(r) and all(
        v['costObservation']['pricedCallAmountsComplete'] for v in (left, right))
    costs = []
    for key in sorted(set(l) | set(r)):
        x, y = l.get(key), r.get(key)
        old, new = (Decimal(x['knownCalculated']) if x else None), (Decimal(y['knownCalculated']) if y else None)
        costs.append({'lane': key[0], 'unit': key[1], 'baselineKnown': str(old) if old is not None else None,
            'reviewedKnown': str(new) if new is not None else None,
            'savingsFraction': str((old - new) / old) if comparable and old else None})
    return {'schemaVersion': VERSION, 'baseline': left, 'reviewed': right,
        'costsComparable': comparable, 'costs': costs, 'pairedTaskUnits': 1, 'sourceIndependenceVerified': False,
        'qualityLost': left['quality'] == 'PASS' and right['quality'] == 'FAIL',
        'qualityImproved': left['quality'] == 'FAIL' and right['quality'] == 'PASS',
        'qualityUnknown': 'UNKNOWN' in (left['quality'], right['quality']),
        'netBenefitProven': False, 'releaseDecision': 'requires-frozen-independent-study', 'modelCalls': 0}
