"""条件审核仅作冻结研究决策；模拟资格不写入产品或替代语义验收。"""
from copy import deepcopy

import pytest

from refractrouter.purpose_review import digest
from refractrouter.review_research_policy import decide, freeze, mechanical


def materials(*, mode='strict', qualified=True, every=1):
    backend = {'provider': 'fixture', 'model': 'judge', 'modelRevision': 'fixture-r1',
        'templateSha256': digest('模拟模板'), 'contractVersion': 'purpose-review-v1', 'scoreThreshold': None}
    qualification = {'contract': 'judge-qualification-v1', 'groups': [
        {'identity': {'purpose': 'advisor-delivery', 'backend': backend}, 'qualified': qualified}]}
    development = [{'taskId': 'dev-1', 'sourceClusterId': 'source-1', 'split': 'development',
                    'family': 'closed-json', 'materialSha256': digest('模拟公开材料')}]
    policy = freeze(purpose='advisor-delivery', mode=mode, backend=backend,
        qualification_sha256=digest(qualification), development=development,
        eligible_families=['closed-json'], review_every=every)
    return policy, qualification


def decision(policy, qualification, **updates):
    args = {'family': 'closed-json', 'ordinal': 2, 'reviews_used': 1,
            'candidate': '{"result":"可能仍有语义错误"}', 'json_object': True}
    args.update(updates)
    return decide(policy, qualification, **args)


@pytest.mark.parametrize('candidate', ['[1]', '{"a":1,"a":2}', '{"a":NaN}', '不是JSON'])
def test_deterministic_failure_blocks_without_judge_or_semantic_approval(candidate):
    policy, qualification = materials(qualified=False)
    row = decision(policy, qualification, candidate=candidate)
    assert row['action'] == 'block' and row['modelCalls'] == 0
    assert row['approved'] is False and row['mechanicalChecks']['semanticQuality'] == 'UNKNOWN'


def test_length_and_unicode_check_keeps_original_candidate_unmodified():
    text = '中文🦀'
    row = mechanical(text, length={'maxLength': 3, 'unit': 'unicode-code-points', 'countWhitespace': True})
    assert row['passed'] is True and row['entireTaskAccepted'] is False
    assert mechanical(text, length={'maxLength': 3, 'unit': 'utf8-bytes', 'countWhitespace': True})['passed'] is False
    assert text == '中文🦀'


def test_strict_mode_never_silently_skips_when_checks_pass_or_quota_runs_out():
    policy, qualification = materials()
    assert decision(policy, qualification)['action'] == 'review'
    row = decision(policy, qualification, ordinal=3, reviews_used=2)
    assert row['action'] == 'stop' and row['reason'] == 'bounded-review-limit'


def test_conditional_skip_is_explicitly_unreviewed_and_never_entire_task_acceptance():
    policy, qualification = materials(mode='conditional-research', every=2)
    row = decision(policy, qualification)
    assert row['action'] == 'unreviewed' and row['approved'] is False and row['productionEnabled'] is False
    assert row['mechanicalChecks']['passed'] is True
    assert row['mechanicalChecks']['entireTaskAccepted'] is False
    assert decision(policy, qualification, ordinal=1, reviews_used=0)['action'] == 'review'
    assert decision(policy, qualification, reviews_used=0)['action'] == 'review'
    assert decision(policy, qualification, is_revision=True)['action'] == 'review'
    assert decision(policy, qualification, family='unverified')['action'] == 'review'
    assert decision(policy, qualification, json_object=False)['action'] == 'review'


def test_unknown_judge_cannot_turn_into_approval_or_conditional_skip():
    policy, qualification = materials(mode='conditional-research', qualified=False, every=2)
    row = decision(policy, qualification)
    assert row['action'] == 'stop' and row['reason'] == 'exact-purpose-backend-unqualified'
    assert row['approved'] is False


def test_qualification_drift_and_other_purpose_do_not_inherit_eligibility():
    policy, qualification = materials()
    changed = deepcopy(qualification)
    changed['groups'][0]['identity']['purpose'] = 'escalation-takeover'
    with pytest.raises(ValueError, match='冻结版本'):
        decision(policy, changed)
    policy['qualificationSha256'] = digest(changed)
    policy['sha256'] = digest({k: v for k, v in policy.items() if k != 'sha256'})
    assert decision(policy, changed)['action'] == 'stop'


@pytest.mark.parametrize('change', ['holdout', 'gold', 'strict-skip', 'unbounded', 'unknown-field'])
def test_freeze_rejects_holdout_answers_unbounded_and_silent_strict_changes(change):
    policy, _ = materials()
    args = dict(purpose=policy['purpose'], mode=policy['mode'], backend=policy['backend'],
        qualification_sha256=policy['qualificationSha256'], development=deepcopy(policy['development']),
        eligible_families=policy['eligibleFamilies'])
    if change == 'holdout': args['development'][0]['split'] = 'holdout'
    elif change == 'gold': args['development'][0]['answer'] = '不能进入触发规则'
    elif change == 'strict-skip': args['review_every'] = 2
    elif change == 'unbounded': args['max_reviews'] = 100
    else: args['development'][0]['unexpected'] = True
    with pytest.raises(ValueError):
        freeze(**args)


@pytest.mark.parametrize('updates', [{'reviews_used': True}, {'ordinal': 0}, {'reviews_used': 2}, {'is_revision': 1}])
def test_counter_and_revision_flags_are_not_coerced(updates):
    policy, qualification = materials()
    with pytest.raises(ValueError):
        decision(policy, qualification, **updates)
