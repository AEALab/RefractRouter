"""订阅估值目录：只改变价格依据，不改变实际模型、端点或信任设置。"""
from copy import deepcopy
from importlib.resources import files
import json

ARK_ENDPOINT = 'https://ark.cn-beijing.volces.com/api/plan/v3'


def reference_for(model, *, endpoint=ARK_ENDPOINT):
    catalog = json.loads(files('refractrouter').joinpath('resources/subscription-reference-prices.json').read_text())
    if model not in catalog['models']:
        raise ValueError(f'{model} 尚无已核对的公开参考价格；不会保留 AFP 或猜测价格')
    return {'executionEndpoint': endpoint, **deepcopy(catalog['models'][model])}


def planning_binding(model):
    reference = reference_for(model['model'])
    from .currency_pricing import reference_price
    price = reference_price(reference)
    rates = dict(price.rates)
    return {**deepcopy(model), 'billingMode': 'subscription', 'billingUnit': price.currency,
            'referencePricing': reference,
            'inputPer1k': float(rates['input'] * 1000),
            'outputPer1k': float(rates['output'] * 1000),
            'cachedInputPer1k': float(rates.get('cachedInput', rates['input']) * 1000),
            'cacheWritePer1k': float(rates.get('cacheWrite', rates['input']) * 1000)}


def media_binding(route):
    catalog = json.loads(files('refractrouter').joinpath('resources/subscription-reference-prices.json').read_text())
    if (route.get('provider') != 'ark-plan' or route.get('endpoint', '').rstrip('/') != ARK_ENDPOINT
            or route.get('model') not in catalog.get('mediaModels', {})):
        raise ValueError('媒体订阅路线尚无已核对的公开参考价格')
    reference = {'executionEndpoint': ARK_ENDPOINT, **deepcopy(catalog['mediaModels'][route['model']])}
    price = reference['price']
    return {**deepcopy(route), 'billingMode': 'subscription', 'billingUnit': 'CNY',
            'referencePricing': reference,
            'pricing': {'basis': 'image', 'unitCost': float(price['rates']['image']),
                        'source': price['source'], 'checkedAt': price['checkedAt']}}
