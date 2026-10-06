"""OpenRouter endpoint 身份、时段、长上下文与预算上界。"""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

import pytest

from refractrouter.openrouter_pricing import endpoint_price


def document():
    return {'model': 'maker/model', 'checkedAt': '2026-10-06',
        'source': 'https://openrouter.ai/api/v1/models/maker/model/endpoints',
        'data': {'endpoints': [{'tag': 'maker/fp8', 'model_id': 'maker/model',
            'pricing': {'prompt': '.000001', 'completion': '.000002', 'discount': 0,
                'overrides': [
                    {'min_prompt_tokens': 100, 'prompt': '.000003'},
                    {'utc_start': 2300, 'utc_end': 100, 'completion': '.000004'},
                    {'utc_days': ['saturday', 'sunday'], 'prompt': '.0000005'}]}}]}}


def rates(doc=None, *, day=6, hour=12, tokens=100, upper=False):
    return dict(endpoint_price(doc or document(), 'maker/fp8',
        at=datetime(2026, 10, day, hour, tzinfo=timezone.utc),
        prompt_tokens=tokens, upper_bound=upper).rates)


def test_strict_context_threshold_and_later_matching_override():
    assert rates()['input'] == Decimal('.000001')
    assert rates(tokens=101)['input'] == Decimal('.000003')
    assert rates(day=10, tokens=101)['input'] == Decimal('.0000005')


def test_wrapped_utc_window_and_conservative_bound():
    assert rates(hour=0)['output'] == Decimal('.000004')
    assert rates(hour=1)['output'] == Decimal('.000002')
    assert rates(hour=23)['output'] == Decimal('.000004')
    assert rates(day=10, upper=True)['input'] == Decimal('.000003')
    assert rates(upper=True)['output'] == Decimal('.000004')


@pytest.mark.parametrize('change', [
    {'discount': .5}, {'image': '.1'},
    {'overrides': [{'unknown_condition': 1, 'prompt': '0'}]},
    {'overrides': [{'utc_start': 99, 'utc_end': 100, 'prompt': '0'}]},
    {'overrides': [{'min_prompt_tokens': True, 'prompt': '0'}]},
    {'overrides': [{'utc_days': ['holiday'], 'prompt': '0'}]},
])
def test_unsupported_price_condition_never_silently_discounts(change):
    doc = document()
    doc['data']['endpoints'][0]['pricing'].update(change)
    with pytest.raises(ValueError):
        rates(doc)


def test_duplicate_endpoint_and_identity_mismatch_rejected():
    doc = document()
    doc['data']['endpoints'].append(deepcopy(doc['data']['endpoints'][0]))
    with pytest.raises(ValueError, match='重复'):
        rates(doc)
    doc = document()
    doc['data']['endpoints'][0]['model_id'] = 'other'
    with pytest.raises(ValueError, match='身份'):
        rates(doc)


def test_real_frozen_endpoint_prices_are_bound_and_upper_bounds_cover_quote():
    path = Path(__file__).parents[1] / 'data/model-catalogs/openrouter-manufacturer-endpoints-2026-10-06.json'
    rows = json.loads(path.read_text())
    assert len(rows) == 6
    for doc in rows:
        tag = doc['data']['endpoints'][0]['tag']
        actual = endpoint_price(doc, tag, at=datetime(2026, 10, 6, 2, tzinfo=timezone.utc), prompt_tokens=1000)
        upper = endpoint_price(doc, tag, at=datetime(2026, 10, 6, 2, tzinfo=timezone.utc), prompt_tokens=1000,
                               upper_bound=True)
        assert actual.provider_route == tag
        assert actual.basis == 'route-public-price'
        assert all(dict(upper.rates)[k] >= v for k, v in actual.rates)
