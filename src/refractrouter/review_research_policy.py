"""冻结研究用审核触发规则；不接入产品严格审核，不以机械通过证明语义。"""
from copy import deepcopy

from .judge_qualification import backend_identity
from .output_constraints import check_output_constraints, validate_output_constraints
from .purpose_review import decode, digest, wire

VERSION = 'review-trigger-research-v1'


def mechanical(candidate, *, length=None, json_object=False):
    if type(candidate) is not str or type(json_object) is not bool:
        raise ValueError('候选与确定性检查配置无效')
    wire(candidate)
    checks = []
    if length is not None:
        checked = check_output_constraints(validate_output_constraints(length), candidate)
        checks.append({'id': 'length', 'passed': checked['passed'], 'evidence': checked})
    if json_object:
        try:
            passed = type(decode(candidate)) is dict
        except ValueError:
            passed = False
        checks.append({'id': 'json-object', 'passed': passed})
    return {'schemaVersion': 'mechanical-delivery-check-v1', 'candidateSha256': digest(candidate),
            'checks': checks, 'passed': all(c['passed'] for c in checks) if checks else None,
            'semanticQuality': 'UNKNOWN', 'entireTaskAccepted': False, 'modelCalls': 0}


def freeze(*, purpose, mode, backend, qualification_sha256, development, eligible_families,
           review_every=1, max_reviews=2):
    """只接收开发样本身份，不接收留出答案；来源真实性仍由受信研究导入方核对。"""
    backend_identity(backend)
    if (type(qualification_sha256) is not str or len(qualification_sha256) != 64
            or any(c not in '0123456789abcdef' for c in qualification_sha256)):
        raise ValueError('必须冻结精确评审资格材料')
    if purpose not in {'advisor-delivery', 'escalation-takeover'} or mode not in {'strict', 'conditional-research'}:
        raise ValueError('研究用途或触发模式无效')
    if type(review_every) is not int or not 1 <= review_every <= 4 or type(max_reviews) is not int or not 1 <= max_reviews <= 2:
        raise ValueError('审核频率或次数未有界')
    if mode == 'strict' and review_every != 1:
        raise ValueError('严格审核不能跳过')
    if type(eligible_families) is not list or any(type(f) is not str or not f.strip() for f in eligible_families):
        raise ValueError('条件审核类别无效')
    if len(set(eligible_families)) != len(eligible_families) or type(development) is not list or not development:
        raise ValueError('开发来源缺失或类别重复')
    seen, families = set(), set()
    for row in development:
        if type(row) is not dict or set(row) != {'taskId', 'sourceClusterId', 'split', 'family', 'materialSha256'}:
            raise ValueError('开发声明不能夹带评分、答案或未知字段')
        if (row['split'] != 'development' or any(type(row[k]) is not str or not row[k].strip()
                for k in ('taskId', 'sourceClusterId', 'family', 'materialSha256'))
                or row['taskId'] in seen or len(row['materialSha256']) != 64
                or any(c not in '0123456789abcdef' for c in row['materialSha256'])):
            raise ValueError('不能从留出或重复任务冻结触发规则')
        seen.add(row['taskId']); families.add(row['family'])
    if not set(eligible_families) <= families:
        raise ValueError('触发类别未出现在冻结开发来源')
    body = {'schemaVersion': VERSION, 'purpose': purpose, 'mode': mode, 'backend': deepcopy(backend),
            'qualificationSha256': qualification_sha256,
            'development': deepcopy(development), 'eligibleFamilies': list(eligible_families),
            'reviewEvery': review_every, 'maxReviews': max_reviews, 'unknownAction': 'stop',
            'productionEnabled': False}
    return {**body, 'sha256': digest(body)}


def decide(policy, qualification, *, family, ordinal, reviews_used, candidate,
           length=None, json_object=False, is_revision=False):
    if type(policy) is not dict or 'sha256' not in policy:
        raise ValueError('需要冻结审核规则')
    body = {k: v for k, v in policy.items() if k != 'sha256'}
    if digest(body) != policy['sha256']:
        raise ValueError('审核规则摘要漂移')
    expected = freeze(purpose=policy['purpose'], mode=policy['mode'], backend=policy['backend'],
        qualification_sha256=policy['qualificationSha256'],
        development=policy['development'], eligible_families=policy['eligibleFamilies'],
        review_every=policy['reviewEvery'], max_reviews=policy['maxReviews'])
    if policy != expected:
        raise ValueError('审核规则版本或字段不符')
    if (type(ordinal) is not int or ordinal < 1 or type(reviews_used) is not int or reviews_used < 0
            or reviews_used >= ordinal or type(is_revision) is not bool or type(family) is not str):
        raise ValueError('候选次序、审核计数或返工状态无效')
    if digest(qualification) != policy['qualificationSha256']:
        raise ValueError('评审资格材料与冻结版本不符')
    checks = mechanical(candidate, length=length, json_object=json_object)
    action, reason = 'review', 'strict-or-ineligible'
    if checks['passed'] is False:
        action, reason = 'block', 'mechanical-constraint-failed'
    elif (type(qualification) is not dict or qualification.get('contract') != 'judge-qualification-v1'
          or not any(g.get('qualified') is True and g.get('identity') == {
              'purpose': policy['purpose'], 'backend': policy['backend']}
              for g in qualification.get('groups', []))):
        action, reason = 'stop', 'exact-purpose-backend-unqualified'
    elif reviews_used >= policy['maxReviews']:
        action, reason = 'stop', 'bounded-review-limit'
    elif (policy['mode'] == 'conditional-research' and family in policy['eligibleFamilies']
          and checks['passed'] is True and not is_revision and ordinal > 1
          and reviews_used > 0
          and (ordinal - 1) % policy['reviewEvery']):
        action, reason = 'unreviewed', 'frozen-conditional-frequency'
    return {'schemaVersion': VERSION, 'policySha256': policy['sha256'],
            'qualificationSha256': digest(qualification), 'action': action, 'reason': reason,
            'mechanicalChecks': checks,
            'approved': False, 'productionEnabled': False, 'modelCalls': 0}
