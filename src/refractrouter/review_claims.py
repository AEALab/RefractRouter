"""定位需逐项审核的状态措辞；仅作覆盖提示，不判定事实真假。"""
import re

VERSION = 'source-state-attention-v1'
LIMIT = 128
# 命中条件、引用或自述也保留，由审核器结合完整正文判断语义。
STATE = re.compile(
    r'未经(?:实测|验证|测试|核对|校验|确认)|'
    r'(?:尚未|未曾|从未|已经|已|未)(?:实际)?(?:完成|执行|进行)?'
    r'(?:实测|验证|测试|核对|校验|确认|配置|启用)|'
    r'未[^。！？；;|\n]{0,24}(?:核对|校验)|'
    r'无自动化(?:验证|测试)?|'
    r'\b(?:unverified|untested|never(?: been)? tested|not(?: been)? verified|not(?: been)? tested|already verified|already tested)\b',
    re.IGNORECASE,
)
BOUNDARY = re.compile(r'[。！？\n|；;]')


def state_claims(answer):
    """返回原文连续片段；不删除免责、条件或警告，不截断超量输入。"""
    rows = []
    for part in BOUNDARY.split(answer):
        # split 保留的单元与原正文逐字一致，不拼接或改写内容。
        if STATE.search(part):
            quote = part.strip()
            if not quote:
                continue
            if len(quote) > 1000:
                raise ValueError('review-source-claim-span-exceeded')
            rows.append({'check_id': f'source-claim-c{len(rows)+1}', 'quote': quote})
            if len(rows) > LIMIT:
                raise ValueError('review-source-claim-count-exceeded')
    return rows
