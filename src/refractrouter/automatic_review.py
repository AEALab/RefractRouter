"""自动路由的自适应审核边界；只决定审核，不改选模或执行宿主工具。"""
from copy import deepcopy
import re

from .review_claims import state_claims
from .task_tool_evidence import tool_requirements

VERSION = 'adaptive-final-review-v1'
FAILURE_VERSION = 'final-review-failure-v1'

# 这些信号用于决定是否增加审核；不能作为事实错误或审核通过的结论。
FACT_TASK = re.compile(
    r'查证|查證|核实|核實|搜索|搜尋|检索|檢索|研究|调研|調研|引用|来源|來源|'
    r'最新|近期|现状|現狀|实时|即時|股价|股價|投资|投資|诊断|診斷|法律|'
    r'\b(?:research|verify|fact.check|citations?|sources?|latest|current|medical|legal|investment)\b', re.I)
CANDIDATE_SOURCE = re.compile(r'https?://|\[(?:\d+|来源|來源|source)\]|【\d+】', re.I)
STATE_ASSERTION = re.compile(
    r'(?:已|已经|已經)[^。！？\n]{0,16}(?:执行|執行|调用|調用|测试|測試|验证|驗證)|'
    r'(?:测试|測試|驗收|验收)[^。！？\n]{0,12}通过|'
    r'\b(?:tests? (?:have )?passed|verified|successfully executed)\b', re.I)
CONTEXT_DEPENDENT = re.compile(r'继续|繼續|上文|之前|刚才|剛才|这些|這些|那[么麼]?接[下著]|\bcontinue\b', re.I)


def preflight(payload, gate, *, policy, tools_allowed):
    if policy not in {'adaptive', 'always'}:
        raise ValueError('reviewPolicy must be adaptive or always')
    reasons = []
    if policy == 'always':
        reasons.append('always-review')
    if gate['decision'] != 'direct':
        reasons.append('dag-or-blocked')
    for key, label in (('materials', 'materials-present'),
                       ('acceptanceCriteria', 'acceptance-criteria-present'),
                       ('outputConstraints', 'strict-output-contract')):
        if payload.get(key):
            reasons.append(label)
    task = payload.get('task', '')
    if tool_requirements(task)['required']:
        reasons.append('task-requires-tools')
    if FACT_TASK.search(task):
        reasons.append('task-needs-factual-verification')
    if payload.get('context') and CONTEXT_DEPENDENT.search(task):
        reasons.append('context-dependent-request')
    # 非封闭任务的候选可能产生新风险。先保护审核名额及额度，最终边界再决定
    # 是否实际派发；注册工具本身不成为最终审核理由。
    protected = bool(reasons) or gate.get('reasons') != ['trivial-workload']
    return {'version': VERSION, 'policy': policy, 'phase': 'preflight',
            'required': protected, 'reserve_required': protected,
            'reason': ','.join(reasons) if reasons else ('awaiting-actual-evidence' if protected
                                                       else 'adaptive-low-risk-direct'),
            'task_reasons': reasons, 'tools_available': bool(tools_allowed)}


def finalize(initial, *, answer, tool_evidence=None, known_failure=None):
    """只消费实际候选及已完成证据；无法确认的回执由调用方先阻断。"""
    result = deepcopy(initial)
    reasons = list(initial['task_reasons'])
    records = (tool_evidence or {}).get('records', [])
    if records:
        reasons.append('host-tools-used')
    candidate_signals = []
    if CANDIDATE_SOURCE.search(answer):
        candidate_signals.append('candidate-cites-sources')
    if state_claims(answer) or STATE_ASSERTION.search(answer):
        candidate_signals.append('candidate-asserts-system-state')
    reasons.extend(candidate_signals)
    if known_failure is not None:
        reasons.append('deterministic-check-failed')
    result.update(phase='final', required=bool(reasons),
                  reason=','.join(dict.fromkeys(reasons)) if reasons else 'adaptive-low-risk-direct',
                  candidate_signals=candidate_signals, tool_result_count=len(records),
                  preflight_reason=initial['reason'])
    return result


def outcome(judged, quality_min):
    """只对明确候选缺陷开放纠正；信息不足或仅低分不重新派发。"""
    uncertain = [row['check_id'] for row in judged.get('grounding_checks', [])
                 if row.get('status') == 'UNCERTAIN']
    if uncertain:
        kind, repairable = 'insufficient-evidence', False
    elif judged['passed'] is False:
        kind, repairable = 'candidate-defect', True
    elif judged['score'] < quality_min:
        kind, repairable = 'below-quality-threshold', False
    else:
        kind, repairable = 'approved', False
    return {'version': FAILURE_VERSION, 'kind': kind, 'repairable': repairable,
            'uncertain_checks': uncertain}
