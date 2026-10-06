"""金额迁移的算账反例：单位、缓存、来源和真实预算边界。"""
from decimal import Decimal

import pytest

from refractrouter.currency_pricing import (
    VERSION, PriceSnapshot, calculate, openrouter_catalog_price, token_units,
    subscription_valuation,
)


def test_subscription_valuation_preserves_ark_route_without_inventing_cash_charge():
    route = {'provider': 'ark', 'model': 'model-v1', 'billingMode': 'subscription',
             'endpoint': 'https://ark.cn-beijing.volces.com/api/plan/v3'}
    mapping = {'match': 'verified-version', 'source': 'https://example.com/models',
               'checkedAt': '2026-10-06', 'description': '已核对同一模型版本'}
    result = subscription_valuation(route, price(), token_units(1000, 20), mapping=mapping)
    assert result['executionRoute'] == route
    assert result['priceSnapshot']['provider'] == 'official'
    assert result['basis'] == 'reference-price'
    assert Decimal(result['amountCny']) == Decimal('.022')
    assert result['cashCharge'] is None  # 不将未分摊订阅费描述为免费。
    assert result['eligibleForCashBudget'] is False
    assert result['cashChargeStatus'] == 'not-attributed-per-call'
    with pytest.raises(ValueError, match='版本映射'):
        subscription_valuation(route, price(), token_units(1, 1), mapping={})


def price(**changes):
    row = {'schemaVersion': VERSION, 'provider': 'official', 'model': 'model-v1',
           'endpoint': 'https://example.com/v1', 'currency': 'CNY',
           'rates': {'input': '.00002', 'cachedInput': '.000002',
                     'cacheWrite': '.00002', 'output': '.0001', 'request': '0'},
           'source': 'https://example.com/pricing', 'checkedAt': '2026-10-06',
           'basis': 'route-public-price'}
    row.update(changes)
    return PriceSnapshot.read(row)


def test_cached_input_and_cache_write_are_mutually_exclusive():
    # 与既有 Kimi 测试同一用量：200 普通输入、200 读、600 写、20 输出。
    bill = calculate(price(), token_units(1000, 20, cached_input=200, cache_write=600), budget=True)
    assert Decimal(bill['amountCny']) == Decimal('.0184')
    assert bill['status'] == 'calculated-not-provider-confirmed'
    assert sum(map(Decimal, bill['breakdown'].values())) == Decimal(bill['amount'])


def test_usd_conversion_preserves_raw_currency_and_exact_small_cost():
    usd = price(currency='USD', rates={'input': '.000000042', 'output': '0', 'request': '0'})
    fx = {'base': 'USD', 'quote': 'CNY', 'rate': '7.123456',
          'source': 'https://example.com/fx', 'asOf': '2026-10-06'}
    bill = calculate(usd, token_units(11, 0), usd_cny=fx)
    assert bill['currency'] == 'USD'
    assert Decimal(bill['amount']) == Decimal('.000000462')
    assert Decimal(bill['amountCny']) == Decimal('.000003291036672')
    assert bill['exchangeRate']['asOf'] == '2026-10-06'


@pytest.mark.parametrize('value', [-1, 'NaN', 'Infinity', True, None])
def test_invalid_prices_cannot_be_zero_or_free(value):
    with pytest.raises(ValueError):
        price(rates={'input': value})


def test_afp_and_unattributed_fx_cannot_enter_cash_budget():
    with pytest.raises(ValueError, match='AFP'):
        price(currency='AFP')
    with pytest.raises(ValueError, match='汇率'):
        calculate(price(currency='USD'), token_units(1, 1))
    with pytest.raises(ValueError):
        calculate(price(currency='USD'), token_units(1, 1),
                  usd_cny={'base': 'USD', 'quote': 'CNY', 'rate': 7})


def test_reference_price_cannot_authorize_cash_call():
    snapshot = price(basis='reference-price')
    assert calculate(snapshot, token_units(1, 1))['basis'] == 'reference-price'
    with pytest.raises(ValueError, match='参考估值'):
        calculate(snapshot, token_units(1, 1), budget=True)


def test_cache_counts_and_missing_rates_fail_closed():
    with pytest.raises(ValueError, match='不能超过'):
        token_units(10, 2, cached_input=9, cache_write=2)
    with pytest.raises(ValueError, match='整数'):
        token_units(True, 2)
    with pytest.raises(ValueError, match='缺少 cachedInput'):
        calculate(price(rates={'input': '.01', 'output': '.02', 'request': '0'}),
                  token_units(100, 10, cached_input=10))


def test_non_token_prices_remain_per_unit():
    bill = calculate(price(rates={'image': '.2', 'videoSecond': '.3', 'request': '.01'}),
                     {'image': 2, 'videoSecond': '2.5', 'request': 1})
    assert Decimal(bill['amountCny']) == Decimal('1.16')


def test_openrouter_per_token_not_per_million_and_catalog_is_reference_only():
    snapshot = openrouter_catalog_price({'id': 'typesafe/jev-1.13',
        'pricing': {'prompt': '.000000042', 'completion': '0'}}, checked_at='2026-10-06')
    fx = {'base': 'USD', 'quote': 'CNY', 'rate': '7',
          'source': 'https://example.com/fx', 'asOf': '2026-10-06'}
    bill = calculate(snapshot, token_units(1_000_000, 0), usd_cny=fx)
    assert Decimal(bill['amount']) == Decimal('.042')
    with pytest.raises(ValueError, match='参考估值'):
        calculate(snapshot, token_units(100, 0), usd_cny=fx, budget=True)


@pytest.mark.parametrize('pricing', [
    {'prompt': '-1', 'completion': '-1'},
    {'prompt': '.001'},
    {'prompt': '.001', 'completion': '.002', 'overrides': [{'min_prompt_tokens': 100}]},
    {'prompt': '.001', 'completion': '.002', 'internal_reasoning': '.1'},
])
def test_dynamic_conditional_or_extra_prices_require_explicit_adapter(pricing):
    with pytest.raises(ValueError):
        openrouter_catalog_price({'id': 'model', 'pricing': pricing}, checked_at='2026-10-06')


def test_source_and_endpoint_cannot_contain_credentials():
    for field in ('source', 'endpoint'):
        for value in ('https://user:secret@example.com/', 'https://example.com/?key=secret'):
            with pytest.raises(ValueError):
                price(**{field: value})
