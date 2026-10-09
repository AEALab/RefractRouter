"""检查真实验收夹具能识别错误、独立边界和篡改测试，不能只信模型自报。"""
from experiments.automatic_workflow_fixtures import create_fixture, check_fixture


def test_workflow_checks_detect_original_defects_and_accept_real_repairs(tmp_path):
    path = tmp_path/'fixture'
    original = create_fixture(path, independent=True)
    assert not check_fixture(path, original)['passed']
    (path/'fees.py').write_text('''from decimal import Decimal
def total_fee(amounts):
    total = Decimal(0)
    for value in amounts:
        item = Decimal(value)
        if not item.is_finite():
            raise ValueError("非有限金额")
        total += item
    return total
''')
    (path/'timeouts.py').write_text('''def timeout_seconds(value, default_ms=3000):
    if type(default_ms) is not int or default_ms < 0:
        raise ValueError("非法默认期限")
    value = default_ms if value is None else value
    if type(value) is not int or value < 0:
        raise ValueError("非法期限")
    return value / 1000 if value else None
''')
    check = check_fixture(path, original)
    assert check['passed'] and check['checks'] == 20
    assert set(check['modifiedFiles']) == {'fees.py','timeouts.py'}
    (path/'test_fees.py').write_text('伪造通过')
    assert not check_fixture(path, original)['passed']
