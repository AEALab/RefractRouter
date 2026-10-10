"""工具验收只消费本任务宿主回执；模型正文不能替代实际执行证据。"""
from copy import deepcopy
import hashlib
import json
import re

from .responses_api import output_token_limit
from .task_budget import request_input_bound

VERSION = 'task-tool-evidence-v1'
# 包含嵌套 JSON 转义的请求增量；不截断证据，也不增加隐式摘要调用。
MAX_EVIDENCE_BYTES = 16 * 1024
_GENERIC = re.compile(
    r'搜索(?:网页|网络|互联网)|查找(?:最新|实时)|读取(?:文件|仓库)|'
    r'写入文件|修改代码|运行(?:命令|测试|脚本)|执行(?:命令|终端)|调用(?:工具|API)|'
    r'发送(?:消息|邮件)|\bsearch (?:the )?(?:web|internet)\b|'
    r'\bread (?:the )?(?:file|repository)\b|\brun (?:the )?(?:command|tests?|script)\b|'
    r'\bcall (?:a )?(?:tool|api)\b', re.I)
_NON_REQUIRED = re.compile(
    r'不要|不需要|无需|无须|不必|不得|请勿|禁止|避免|不(?:再|实际|直接)?(?:调用|使用|执行|运行|读取|搜索|发送)|'
    r'(?<![分特])别|可以|可选|例如|比如|示例|解释|说明如何|'
    r'如果|若|视情况|酌情|必要时|\b(?:do not|don\x27t|without|never|optional|may|could|'
    r'example|explain|how to|if|unless)\b', re.I)


def tool_requirements(task, schemas=()):
    """仅识别肯定式工具要求；完整操作、条件和结果语义仍由最终评审检查。"""
    source = re.sub(r'```[\s\S]*?```|「[^」]*」|“[^”]*”|"[^"\n]*"', '', task)
    source = source.replace('`', '')
    source = re.sub(r'(?:如果|若|\bif\b|\bunless\b)[^。！？!?\n]*', '', source, flags=re.I)
    names = {s['name'].casefold() for s in schemas} | {'bash', 'pwsh', 'shell'}
    required, matched = False, set()
    for clause in re.split(r'[，,。！？!?；;\n]', source):
        if _NON_REQUIRED.search(clause):
            continue
        if _GENERIC.search(clause):
            required = True
        for name in names:
            tool = re.escape(name)
            pattern = (r'(?:使用|调用|呼叫|透过|通过|用|执行|运行|\buse\s+|\bcall\s+|\brun\s+)'
                       r'\s*(?:the\s+)?' + tool + r'(?![\w.-])')
            if re.search(pattern, clause, re.I):
                required = True
                matched.add(name)
    return {'required': required, 'tools': sorted(matched)}


def _outcome(record):
    result = record.get('result') or {}
    fact = result.get('hostResult') or {}
    error = result.get('error') or {}
    code = error.get('code')
    sandbox = fact.get('sandbox') or {}
    if record.get('status') in {'dispatched', 'execution-unconfirmed'} or code in {
            'EXECUTION_UNCONFIRMED', 'UNKNOWN_RESULT', 'ABORTED', 'TOOL_RESULT_UNKNOWN'}:
        return 'unconfirmed'
    if record.get('status') == 'cancelled-before-dispatch':
        return 'not-dispatched'
    if code in {'PERMISSION_DENIED', 'APPROVAL_REJECTED', 'FS_PERMISSION_DENIED',
                'ABORTED_BEFORE_DISPATCH', 'TOOL_ABORTED_BEFORE_DISPATCH', 'TOOL_NOT_STARTED'} or sandbox.get('denied'):
        return 'denied'
    if code in {'AUTH', 'AUTHENTICATION', 'TRANSPORT', 'TIMEOUT', 'NETWORK'} or (
            fact.get('timedOut') or sandbox.get('runnerFailed')):
        return 'infrastructure-error'
    if fact.get('aborted') or fact.get('signal') is not None:
        return 'unconfirmed'
    if type(fact.get('exitCode')) is int:
        return 'completed' if fact['exitCode'] == 0 else 'task-failed'
    if result.get('isError') is True:
        return 'unclassified-error'
    if record.get('status') == 'completed' and result.get('isError') is False:
        return 'returned'  # 收到结果，不证明 shell 退出成功或语义正确。
    return 'unconfirmed'


def collect_tool_evidence(requirements, records, *, available, max_evidence_bytes=MAX_EVIDENCE_BYTES):
    # 旧冻结合同维持固定包络；现行货币参考合同检查实际完整审核请求。
    if max_evidence_bytes is not None and (type(max_evidence_bytes) is not int or max_evidence_bytes < 1):
        raise ValueError('invalid tool evidence envelope')
    rows = []
    for record in records:
        call = record.get('call') or {}
        function = call.get('function') or {}
        result = record.get('result') or {}
        rows.append({'node': record.get('node'), 'call_id': call.get('id'),
                     'tool': function.get('name'), 'arguments': function.get('arguments'),
                     'outcome': _outcome(record), 'is_error': result.get('isError'),
                     'content': deepcopy(result.get('content')),
                     'host_result': deepcopy(result.get('hostResult')),
                     'error': deepcopy(result.get('error'))})
    observed = [r for r in rows if r['outcome'] in {'completed', 'task-failed', 'returned'}]
    missing = [name for name in requirements['tools']
               if not any(str(r['tool']).casefold() == name for r in observed)]
    required = requirements['required']
    passed = not required or (bool(observed) and not missing)
    unconfirmed = any(r['outcome'] == 'unconfirmed' for r in rows)
    if unconfirmed:
        passed = False
    reason = ('host-tool-result-unconfirmed' if unconfirmed else
              'required-host-tool-not-observed' if not passed else
              'host-tool-receipt-observed' if required else 'no-explicit-tool-requirement')
    evidence = {'schema_version': VERSION, 'available': available,
                'requirements': requirements, 'records': rows}
    # 与 messages 的嵌套 JSON 序列化一致；所有材料计入容量，不取摘要或切片。
    size = len(json.dumps(json.dumps({'tool_evidence': evidence}, ensure_ascii=False),
                          ensure_ascii=False).encode())
    if passed and max_evidence_bytes is not None and size > max_evidence_bytes:
        passed, reason = False, 'tool-evidence-envelope-exceeded'
    summary = {'schema_version': VERSION, 'required': required, 'required_tools': requirements['tools'],
               'passed': passed, 'reason': reason, 'missing_tools': missing,
               'records': [{k: r[k] for k in ('node', 'call_id', 'tool', 'outcome')} for r in rows],
               'evidence_bytes': size, 'evidence_limit_bytes': max_evidence_bytes,
               'evidence_sha256': hashlib.sha256(json.dumps(evidence, sort_keys=True,
                                                          ensure_ascii=False).encode()).hexdigest()}
    return evidence, summary


def check_review_capacity(validation, model, messages):
    """检查带完整工具材料与引用目录的真实请求，不以证据大小猜测模型容量。"""
    result = deepcopy(validation)
    bound = request_input_bound(messages)
    limit = model.context_window - output_token_limit(model)
    result.update(capacity_basis='complete-review-request-v1', review_model_id=model.model_id,
                  review_input_bound=bound, review_input_limit=limit)
    if result['passed'] and bound > limit:
        result.update(passed=False, reason='review-input-capacity-exceeded')
    return result


def validation_message(summary):
    if summary['reason'] == 'tool-evidence-envelope-exceeded':
        return (f"工具证据为 {summary['evidence_bytes']} 字节，超过旧合同的 "
                f"{summary['evidence_limit_bytes']} 字节上限；审核未派发，证据未截断。")
    if summary['reason'] == 'review-input-capacity-exceeded':
        return (f"完整审核输入的保守计数为 {summary['review_input_bound']}，超过审核模型的 "
                f"{summary['review_input_limit']} 可用输入容量；审核未派发，证据未截断。")
    messages = {
        'host-tool-result-unconfirmed': '工具结果尚未确认，已停止验收；不会自动重新执行。',
        'required-host-tool-not-observed': '明确要求的工具操作缺少已确认的宿主执行回执，答案不能作为任务完成证明。',
        'host-tool-receipt-observed': '已核对宿主工具回执；操作及结果是否满足要求仍由语义评审检查。',
        'no-explicit-tool-requirement': '未识别到明确工具要求；已提供实际回执供语义评审检查。',
    }
    return messages[summary['reason']]
