"""显式最终输出长度约束；计数、验收和原文保存互不混用。"""
import hashlib


def validate_output_constraints(raw):
    if not isinstance(raw, dict) or set(raw) != {'maxLength', 'unit', 'countWhitespace'}:
        raise ValueError('outputConstraints requires maxLength, unit and countWhitespace')
    if type(raw['maxLength']) is not int or not 1 <= raw['maxLength'] <= 1000000:
        raise ValueError('outputConstraints.maxLength must be an integer in 1..1000000')
    if raw['unit'] not in ('unicode-code-points', 'utf8-bytes'):
        raise ValueError('outputConstraints.unit must be unicode-code-points or utf8-bytes')
    if type(raw['countWhitespace']) is not bool:
        raise ValueError('outputConstraints.countWhitespace must be boolean')
    return dict(raw)


def check_output_constraints(constraints, answer=None):
    result = {'schema_version': 'output-length-check-v1',
              'status': 'not-requested' if constraints is None else 'not-evaluated',
              'constraints': constraints, 'passed': None, 'actual_length': None,
              'output_sha256': None}
    if constraints is None or answer is None:
        return result
    constraints = validate_output_constraints(constraints)
    measured = answer if constraints['countWhitespace'] else ''.join(c for c in answer if not c.isspace())
    actual = len(measured.encode('utf-8')) if constraints['unit'] == 'utf8-bytes' else len(measured)
    passed = actual <= constraints['maxLength']
    return {**result, 'status': 'passed' if passed else 'failed', 'passed': passed,
            'actual_length': actual, 'output_sha256': hashlib.sha256(answer.encode('utf-8')).hexdigest()}


def output_constraint_instruction(constraints):
    unit = 'Unicode 码点（不是 token 或视觉字形）' if constraints['unit'] == 'unicode-code-points' else 'UTF-8 字节'
    spaces = '计入所有空白' if constraints['countWhitespace'] else '计数前排除 Python str.isspace() 识别的空白'
    return (f"最终交付正文最多 {constraints['maxLength']} 个{unit}；{spaces}。"
            '数字、标点和 Markdown 标记均计入；只约束最终交付正文，不约束中间节点。')
