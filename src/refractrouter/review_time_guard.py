"""检查材料明确区分的审核等待上限和执行阶段预留；不代替通用语义审核。"""
import re

VERSION = 'review-time-reservation-guard-v1'
_VALUE = r'(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>毫秒|秒|ms|seconds?)'
_WAIT = re.compile(r'审核\s*(?:最多等待|等待上限(?:为|是)?|最大等待(?:为|是)?)\s*' + _VALUE)
_RESERVE = re.compile(r'(?:给审核预留|为审核预留|审核预留)\s*' + _VALUE)
_PARTS = re.compile(r'[。！？\n|；;]')
_NEGATION = re.compile(r'(?:不会|不能|不应|不得|并非|不等于|不要|不可|不代表)[^，,。！？；;]{0,18}$')
_MISUSE = re.compile(r'(?:误把|误将|错误(?:地)?(?:把|将)|不能把|不应把|不要把|假设实现)[^。！？；;]{0,80}')


def _milliseconds(match):
    return float(match['value']) * (1 if match['unit'] in {'毫秒', 'ms'} else 1000)


def _values(pattern, task):
    return {_milliseconds(match) for match in pattern.finditer(task)}


def check_review_time(task, answer):
    """只检查唯一、明确的中文时间合同；未覆盖表达交由正常 Judge 审核。

    预留是执行阶段须留下的时间，不是进入审核后另行开始的计时器。
    条件词不能让这个错误计时器成立；明确讨论错误实现、否定错误做法则允许。
    不从运行配置推断任务材料，也不根据两个数值不同认定冲突。
    """
    waits, reserves = _values(_WAIT, re.sub(r'[*`]', '', task)), _values(_RESERVE, re.sub(r'[*`]', '', task))
    result = {'version': VERSION, 'applicable': False, 'passed': True,
              'scope': 'explicit-review-wait-and-execution-reserve', 'findings': []}
    if len(waits) != 1 or len(reserves) != 1:
        return {**result, 'reason': '材料没有唯一、明确的审核等待与执行预留合同；未作确定性判定。'}
    wait, reserve = next(iter(waits)), next(iter(reserves))
    result.update(applicable=True, review_wait_ms=wait, execution_reserve_ms=reserve)
    # 相同数值本身不能区分合同角色；仍交给语义审核，不推断冲突。
    if wait == reserve:
        return {**result, 'reason': '数值相同，仍需审核用途；此检查不据数值判定冲突。'}
    reserve_seconds = format(reserve / 1000, 'g')
    reserve_value = rf'(?:{re.escape(reserve_seconds)}\s*秒|{format(reserve, "g")}\s*毫秒)'
    reserve_mention = rf'(?:{reserve_value}\s*(?:的)?\s*预留|预留\s*(?:的)?\s*{reserve_value})'
    expires = re.compile(reserve_mention + r'[^。！？；;]{0,18}(?:到期|用完|耗尽)'
                         r'[^。！？；;]{0,45}审核[^。！？；;]{0,35}(?:截断|停止|中止|结束|等不满)')
    wrong_cap = re.compile(r'审核\s*(?:最多等待|至多等待|等待上限(?:为|是)?|硬上限(?:为|是)?)\s*'
                           + reserve_value)
    for part in _PARTS.split(answer):
        plain = re.sub(r'[*`]', '', part)
        for pattern, check_id in ((expires, 'reserve-as-expiring-review-timer'),
                                  (wrong_cap, 'reserve-as-review-wait-cap')):
            for match in pattern.finditer(plain):
                prefix = plain[:match.start()]
                if _NEGATION.search(prefix) or _MISUSE.search(prefix):
                    continue
                # 否定到期本身也不是错误因果，不用整行的“若／可能”作豁免。
                if re.search(r'(?:不会|不能|不应|并非)[^，,]{0,8}(?:到期|用完|耗尽)', match.group()):
                    continue
                result['findings'].append({'check_id': check_id, 'answer_quote': part.strip(),
                    'reason': '把执行阶段预留当成审核阶段的独立到期计时器或等待上限。'})
    result['passed'] = not result['findings']
    result['reason'] = ('未发现本检查覆盖的预留／等待混淆；其他语义仍须审核。' if result['passed'] else
        '执行阶段预留是进入审核时应留下的时间；审核等待由材料规定的等待上限和任务剩余期限约束，'
        '不能因预留数值先到期就截断审核。请纠正时间解释并复核其他材料事实。')
    return result
