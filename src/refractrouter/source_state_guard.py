"""材料限定任务的保守措辞检查；缺少归属不等于已证明该事实错误。"""
import re

VERSION = 'source-state-attribution-guard-v3'
_STRICT = re.compile(r'(?:仅|只)依据[^。！？\n]{0,32}材料')
_PARTS = re.compile(r'[。！？\n|；;，,、]')
_SENTENCES = re.compile(r'[。！？\n|]')
_NEGATIVE = re.compile(
    r'未经(?:实测|验证|测试|核对|校验|确认)|'
    r'(?:尚未|未曾|从未|未)(?:实际)?(?:完成|执行|进行)?(?:验证|测试|核对|校验)|'
    r'未与[^。！？，,；;|\n]{1,24}(?:核对|校验)')
_CONDITIONAL = re.compile(r'(?:若|如果|假设|假如)[^。！？，,；;]{0,40}$')
_SELF_PREFIX = r'(?:我|我们|本次|本轮|本回答)(?:本次|本轮)?(?:回答|检查|审查)?'
_SELF_ADVERBS = r'(?:也|还|仍|确实|实际|暂时|尚|并)?'
_SELF = re.compile(_SELF_PREFIX + r'\s*' + _SELF_ADVERBS + r'\s*$')
_META = re.compile(r'(?:不能|不应|不要|不得|不可)[^。！？，,；;]{0,12}(?:断言|认定|声称|说|把)[^。！？，,；;]{0,20}$')
_QUESTION = re.compile(r'(?:是否|能否)[^。！？，,；;]{0,8}$')
_SELF_CONTEXT = re.compile(_SELF_PREFIX + r'\s*' + _SELF_ADVERBS + r'\s*(?:未|没有)')
_ELLIPSIS = re.compile(r'^\s*(?:也|并且|且|同时|但|还|仍)?\s*$')
_OMITTED_SELF_VERB = re.compile(r'^\s*(?:也|并且|且|同时|但|还|仍)?\s*(?:未|没有)')


def _parts(text):
    return [re.sub(r'[*`]', '', part).strip() for part in _PARTS.split(text)]


def _framed(prefix):
    return bool(_CONDITIONAL.search(prefix) or _SELF.search(prefix)
                or _META.search(prefix) or _QUESTION.search(prefix))


def check_source_state(task, answer, *, tool_evidence=None):
    """只有材料限定任务启用；明确条件、本次行为、否定引用和字面来源均可保留。

    保守阻断的是未注明归属的否定验证措辞，要求澄清或引用原材料，
    不从来源缺失推断系统实际未验证。字面未匹配的同义改写也可能触发；
    这是有限的交付约束，不是事实真假分类器，其他语义继续由 Judge 审核。
    """
    result = {'version': VERSION, 'applicable': bool(_STRICT.search(task)), 'passed': True,
              'scope': 'strict-material-negative-verification-attribution', 'findings': []}
    if not result['applicable']:
        return {**result, 'reason': '不是明确限定材料的任务；未启用此措辞检查。'}
    sources = _parts(task)
    # 仅使用已收集的宿主证据，不采信模型输出自述为执行证据。
    def collect(value):
        if isinstance(value, str):
            sources.extend(_parts(value))
        elif isinstance(value, dict):
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)
    if tool_evidence is not None:
        collect(tool_evidence)
    for sentence in _SENTENCES.split(answer):
        self_context = False
        for part in _parts(sentence):
            if _SELF_CONTEXT.search(part):
                self_context = True
            elif self_context and not _OMITTED_SELF_VERB.match(part):
                self_context = False
            for match in _NEGATIVE.finditer(part):
                prefix = part[:match.start()]
                # 同一句的分号／逗号可以延续明确的本次自述；新句、换行和表格单元格不能继承。
                # 明确引入“系统／回滚”等另一主体的前缀也不能借自述免责。
                if _framed(prefix) or (self_context and _ELLIPSIS.fullmatch(prefix)):
                    continue
                if prefix and not _SELF.search(prefix):
                    self_context = False
                # 原材料中相同连续断言可引用；材料中的禁止、条件或疑问不能给事实自证。
                if any(part in source and any(not _framed(source[:m.start()])
                        for m in _NEGATIVE.finditer(source)) for source in sources):
                    continue
                result['findings'].append({'check_id': 'negative-verification-attribution',
                    'answer_quote': part,
                    'reason': '否定验证措辞没有明确本次主体、条件前提或匹配的原材料断言；需澄清归属。'})
    result['passed'] = not result['findings']
    result['reason'] = ('已覆盖措辞的归属检查未发现问题；不证明其他事实正确。' if result['passed'] else
        '材料没有交代系统的历史验证状态，不能把信息缺失改写为未经验证或未核对的事实。'
        '若只说明本次行为，明确写本次未执行／核对；若说明材料缺项，写材料未说明、尚待确认。'
        '保留明确条件风险，复核风险表和建议，不声称历史上从未验证。')
    return result
