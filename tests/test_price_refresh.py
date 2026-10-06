"""刷新诊断保留冻结记录，区分价格变化、渠道变化与过期。"""
from copy import deepcopy
import pytest
from refractrouter.price_refresh import compare_prices


def price():
    return {'schemaVersion': 'refractrouter-currency-price-v1',
            'provider': 'official', 'model': 'model', 'endpoint': 'https://example.com/v1',
            'currency': 'CNY', 'rates': {'input': '.000002', 'output': '.000008'},
            'source': 'https://example.com/prices', 'checkedAt': '2026-10-06',
            'basis': 'reference-price'}


def test_refresh_distinguishes_price_and_identity_and_preserves_original():
    old = price()
    original = deepcopy(old)
    new = deepcopy(old)
    new['rates']['input'] = '.000003'
    report = compare_prices(old, new, as_of='2026-10-06')
    assert report['status'] == 'price-changed'
    assert len(report['changes']) == 1
    assert not report['configurationWritten']
    new['currency'] = 'USD'
    assert compare_prices(old, new, as_of='2026-10-06')['status'] == 'requires-route-review'
    assert old == original


def test_refresh_age_and_missing_previous():
    assert compare_prices(None, price(), as_of='2026-11-06')['freshness'] == 'needs-refresh'
    assert compare_prices(None, price(), as_of='2026-11-05')['freshness'] == 'current'
    with pytest.raises(ValueError, match='晚于'):
        compare_prices(None, price(), as_of='2026-10-05')
    with pytest.raises(ValueError, match='有效期'):
        compare_prices(None, price(), as_of='2026-10-06', max_age_days=True)
