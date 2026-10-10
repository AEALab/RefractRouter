"""真实文件修改验收材料及独立检查；不实现或代替客户端工具。"""
from decimal import Decimal
import hashlib
import importlib.util
from pathlib import Path

FEES = '''from decimal import Decimal

def total_fee(amounts):
    return Decimal(str(sum(float(value) for value in amounts)))
'''
TIMEOUTS = '''def timeout_seconds(value, default_ms=3000):
    return (value or default_ms) / 1000
'''
PUBLIC = '''import unittest
from decimal import Decimal
from fees import total_fee

class FeesTests(unittest.TestCase):
    def test_fraction(self):
        self.assertEqual(total_fee(["0.1", "0.2"]), Decimal("0.3"))
    def test_empty(self):
        self.assertEqual(total_fee([]), Decimal("0"))
    def test_not_finite(self):
        with self.assertRaises(ValueError):
            total_fee(["NaN"])

if __name__ == "__main__":
    unittest.main()
'''
TIMEOUT_PUBLIC = '''import unittest
from timeouts import timeout_seconds

class TimeoutTests(unittest.TestCase):
    def test_unlimited(self):
        self.assertIsNone(timeout_seconds(0))
    def test_inherit(self):
        self.assertEqual(timeout_seconds(None, 1500), 1.5)
    def test_invalid(self):
        for value in (-1, True):
            with self.assertRaises(ValueError):
                timeout_seconds(value)

if __name__ == "__main__":
    unittest.main()
'''
SPEC = '''本目录为路由产品的受控功能验收夹具，代码缺陷是预置的。
修复 fees.py 的 total_fee：接收有限十进制字符串列表，精确求和并返回 Decimal；
空列表返回 Decimal(0)；NaN、Infinity 等非有限值须抛出 ValueError；不得修改输入。
不要修改测试、规格或目录以外的文件。工具由接入客户端执行，禁止委派及网络访问。
'''
TIMEOUT_SPEC = '''独立修复 timeouts.py 的 timeout_seconds：输入为非负整数毫秒或 None；
None 使用 default_ms，0 返回 None 表示不限制，正数返回秒数；负数、布尔值、
字符串、浮点数均抛出 ValueError。default_ms 同样只接受非负整数。
两项修改相互独立；先验证各自测试，再汇总。不要改测试或规格。
'''


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_fixture(path, *, independent=False):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=False)
    files = {'fees.py': FEES, 'test_fees.py': PUBLIC, 'SPEC.md': SPEC}
    if independent:
        files.update({'timeouts.py': TIMEOUTS, 'test_timeouts.py': TIMEOUT_PUBLIC,
                      'SPEC.md': SPEC + TIMEOUT_SPEC})
    for name, content in files.items():
        (path/name).write_text(content)
    return {name: digest(path/name) for name in files}


def check_fixture(path, original):
    """检查保留文件和未向客户端公开的边界；不依赖模型自报通过。"""
    path = Path(path)
    changed_protected = [name for name, sha in original.items()
        if name not in {'fees.py', 'timeouts.py'} and (not (path/name).is_file() or digest(path/name) != sha)]
    failures = [f'不得修改的文件变化：{name}' for name in changed_protected]
    checked = 0
    def load(name):
        spec = importlib.util.spec_from_file_location('acceptance_' + name, path/(name+'.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    try:
        fees = load('fees')
        for amounts in [[], ['0.1','0.2'], ['0.29','0.01'], ['-2.5','0.5'],
                        ['123456789012345678.12', '0.03'], ['0.000001']*1000]:
            before = list(amounts)
            result = fees.total_fee(amounts)
            checked += 1
            if not isinstance(result, Decimal) or result != sum(map(Decimal, amounts), Decimal(0)) or before != amounts:
                failures.append('金额精确求和、返回类型或输入保留不符合合同')
        for invalid in ['NaN', 'Infinity', '-Infinity', 'sNaN']:
            checked += 1
            try:
                fees.total_fee([invalid])
            except ValueError:
                continue
            except Exception:
                failures.append('非有限金额没有返回 ValueError')
            else:
                failures.append('非有限金额被接受')
        if 'timeouts.py' in original:
            timeouts = load('timeouts')
            for value, default, expected in [(0,3000,None),(None,1500,1.5),(250,3000,.25),(None,0,None)]:
                checked += 1
                if timeouts.timeout_seconds(value, default) != expected:
                    failures.append('毫秒、继承或不限制语义错误')
            for value, default in [(-1,3000),(True,3000),('0',3000),(1.5,3000),(None,-1),(None,False)]:
                checked += 1
                try:
                    timeouts.timeout_seconds(value, default)
                except ValueError:
                    continue
                else:
                    failures.append('非法期限参数被接受')
    except Exception as exc:
        failures.append(f'独立检查异常：{type(exc).__name__}')
    return {'passed': not failures, 'checks': checked, 'failures': failures,
            'protectedFilesPreserved': not changed_protected,
            'modifiedFiles': [name for name, sha in original.items() if (path/name).is_file() and digest(path/name) != sha]}
