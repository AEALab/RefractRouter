"""将冻结的 OpenRouter endpoint 价格按派发条件物化，不选择或调用模型。"""
from datetime import timezone

from .currency_pricing import VERSION, PriceSnapshot, decimal


PRICE_FIELDS = {'prompt': 'input', 'completion': 'output', 'request': 'request',
                'input_cache_read': 'cachedInput', 'input_cache_write': 'cacheWrite'}
CONDITIONS = {'min_prompt_tokens', 'utc_days', 'utc_start', 'utc_end'}
WEEKDAYS = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')


def _minute(hhmm):
    if type(hhmm) is not int or not 0 <= hhmm < 2400 or hhmm % 100 >= 60:
        raise ValueError('OpenRouter UTC 时段无效')
    return hhmm // 100 * 60 + hhmm % 100


def _matches(row, at, prompt_tokens):
    if set(row) - CONDITIONS - PRICE_FIELDS.keys():
        raise ValueError('OpenRouter 条件价格含未适配字段')
    threshold = row.get('min_prompt_tokens')
    if threshold is not None and (type(threshold) is not int or threshold < 0):
        raise ValueError('OpenRouter 输入阶梯无效')
    days = row.get('utc_days')
    if days is not None and (not isinstance(days, list) or not days or
                             any(day not in WEEKDAYS for day in days)):
        raise ValueError('OpenRouter 星期条件无效')
    start, end = row.get('utc_start'), row.get('utc_end')
    in_window = True
    if start is not None or end is not None:
        start, end = _minute(start), _minute(end)
        moment = at.hour * 60 + at.minute
        in_window = start <= moment < end if start < end else moment >= start or moment < end
    return ((threshold is None or prompt_tokens > threshold)
            and (days is None or WEEKDAYS[at.weekday()] in days) and in_window)


def endpoint_price(document, provider_route, *, at, prompt_tokens, upper_bound=False):
    """预算上界覆盖所有价格阶梯；实际估算按 UTC 时刻和输入长度匹配。"""
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError('派发时刻必须包含时区')
    if type(prompt_tokens) is not int or prompt_tokens < 0:
        raise ValueError('输入 token 数无效')
    at = at.astimezone(timezone.utc)
    data = document['data']
    matches = [row for row in data['endpoints'] if row.get('tag') == provider_route]
    if len(matches) != 1:
        raise ValueError('实际 provider 路线缺失或重复')
    endpoint = matches[0]
    model = document['model']
    if endpoint.get('model_id') != model:
        raise ValueError('endpoint 模型身份不符')
    raw = endpoint.get('pricing')
    if not isinstance(raw, dict) or not {'prompt', 'completion'} <= raw.keys():
        raise ValueError('endpoint 价格缺失')
    if set(raw) - PRICE_FIELDS.keys() - {'discount', 'overrides'}:
        raise ValueError('endpoint 含尚未适配的费用维度')
    if decimal(raw.get('discount', 0), 'discount'):
        raise ValueError('促销折扣适用条件未确认')
    selected = {key: decimal(value, key) for key, value in raw.items() if key in PRICE_FIELDS}
    selected.setdefault('request', decimal(0, 'request'))
    overrides = raw.get('overrides', [])
    if not isinstance(overrides, list):
        raise ValueError('条件价格必须为列表')
    for override in overrides:
        if not isinstance(override, dict):
            raise ValueError('条件价格条目无效')
        matched = _matches(override, at, prompt_tokens)
        prices = {key: decimal(value, key) for key, value in override.items() if key in PRICE_FIELDS}
        if upper_bound:
            for key, value in prices.items():
                selected[key] = max(selected.get(key, value), value)
        elif matched:
            selected.update(prices)
    return PriceSnapshot.read({'schemaVersion': VERSION, 'provider': 'openrouter',
        'providerRoute': provider_route, 'model': model,
        'endpoint': 'https://openrouter.ai/api/v1', 'currency': 'USD',
        'rates': {PRICE_FIELDS[key]: str(value) for key, value in selected.items()},
        'source': document['source'], 'checkedAt': document['checkedAt'],
        'basis': 'route-public-price'})
