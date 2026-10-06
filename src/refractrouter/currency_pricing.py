"""金额计价基础合同；不转换订阅额度，不隐式选择提供方或模型。

上层必须先按真实路线、时段和容量选定价格，再交给本模块计算。
金额使用 Decimal，JSON 边界使用十进制字符串，避免把展示舍入用于预算。
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit


VERSION = 'refractrouter-currency-price-v1'
DIMENSIONS = frozenset({'input', 'cachedInput', 'cacheWrite', 'output',
                        'request', 'image', 'videoSecond'})


def decimal(value, label):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError(f'{label} 必须为非负有限数值')
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f'{label} 必须为非负有限数值') from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f'{label} 必须为非负有限数值')
    return result


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'缺少 {label}')
    return value


def _date(value):
    _text(value, '查证日期')
    date.fromisoformat(value)
    return value


def _url(value):
    _text(value, '来源或路线地址')
    url = urlsplit(value)
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('价格来源及路线地址必须为不含凭据或查询参数的 HTTPS 地址')
    return value


@dataclass(frozen=True)
class PriceSnapshot:
    provider: str
    model: str
    endpoint: str
    currency: str
    rates: tuple[tuple[str, Decimal], ...]
    source: str
    checked_at: str
    basis: str
    provider_route: str | None = None

    @classmethod
    def read(cls, raw):
        if not isinstance(raw, dict) or raw.get('schemaVersion') != VERSION:
            raise ValueError('金额价格合同版本不兼容')
        if raw.get('currency') not in {'CNY', 'USD'}:
            raise ValueError('金额价格仅支持 CNY 或 USD；AFP 不能换算为现金')
        if raw.get('basis') not in {'route-public-price', 'reference-price'}:
            raise ValueError('必须说明实际路线公开价或参考价')
        route = raw.get('providerRoute')
        if route is not None:
            _text(route, 'providerRoute')
        if raw.get('provider') == 'openrouter' and raw['basis'] == 'route-public-price' and not route:
            raise ValueError('OpenRouter 预算价格必须绑定实际 provider 路线')
        rates = raw.get('rates')
        if not isinstance(rates, dict) or not rates or set(rates) - DIMENSIONS:
            raise ValueError('价格维度缺失或不支持')
        # 所有价格都以单个 token／请求／张／秒为单位，转换仅发生在适配边界。
        return cls(_text(raw.get('provider'), 'provider'), _text(raw.get('model'), 'model'),
                   _url(raw.get('endpoint')), raw['currency'],
                   tuple(sorted((key, decimal(value, key)) for key, value in rates.items())),
                   _url(raw.get('source')), _date(raw.get('checkedAt')), raw['basis'], route)

    def as_dict(self):
        return {'schemaVersion': VERSION, 'provider': self.provider, 'model': self.model,
                'endpoint': self.endpoint, 'currency': self.currency,
                'rates': {key: str(value) for key, value in self.rates},
                'source': self.source, 'checkedAt': self.checked_at, 'basis': self.basis,
                'providerRoute': self.provider_route}


def token_units(input_tokens, output_tokens, *, cached_input=0, cache_write=0):
    """输入三类互斥；输出已包含提供方计入的推理 token，不再次相加。"""
    values = (input_tokens, output_tokens, cached_input, cache_write)
    if any(type(value) is not int or value < 0 for value in values):
        raise ValueError('token 用量必须为非负整数')
    if cached_input + cache_write > input_tokens:
        raise ValueError('缓存读取和写入不能超过总输入')
    return {'input': input_tokens - cached_input - cache_write,
            'cachedInput': cached_input, 'cacheWrite': cache_write,
            'output': output_tokens, 'request': 1}


def calculate_units(rates, units):
    """共用的精确金额运算；调用方持有价格身份与计费单位。"""
    if not isinstance(rates, dict) or not rates or set(rates) - DIMENSIONS:
        raise ValueError('价格维度缺失或不支持')
    rates = {key: decimal(value, key) for key, value in rates.items()}
    if not isinstance(units, dict) or set(units) - DIMENSIONS:
        raise ValueError('用量维度不支持')
    breakdown = {}
    for key, raw in units.items():
        amount = decimal(raw, f'{key} 用量')
        if not amount:
            continue
        if key not in rates:
            raise ValueError(f'缺少 {key} 单价；不得按零费用结算')
        breakdown[key] = amount * rates[key]
    return sum(breakdown.values(), Decimal(0)), breakdown


def calculate(snapshot, units, *, usd_cny=None, budget=False):
    """计算明确用量的公开价；结果不宣称提供方已经扣款。"""
    if not isinstance(snapshot, PriceSnapshot):
        raise ValueError('需要已校验价格快照')
    if budget and snapshot.basis != 'route-public-price':
        raise ValueError('参考估值不能用于实际现金预算')
    total, breakdown = calculate_units(dict(snapshot.rates), units)
    fx = None
    if snapshot.currency == 'USD':
        if not isinstance(usd_cny, dict) or usd_cny.get('base') != 'USD' or usd_cny.get('quote') != 'CNY':
            raise ValueError('USD 费用需要明确的 USD/CNY 汇率快照')
        rate = decimal(usd_cny.get('rate'), '汇率')
        if not rate:
            raise ValueError('汇率必须大于零')
        fx = {'base': 'USD', 'quote': 'CNY', 'rate': str(rate),
              'source': _url(usd_cny.get('source')), 'asOf': _date(usd_cny.get('asOf'))}
        cny = total * rate
    else:
        cny = total
    return {'amount': str(total), 'currency': snapshot.currency, 'amountCny': str(cny),
            'basis': snapshot.basis, 'status': 'calculated-not-provider-confirmed',
            'breakdown': {key: str(value) for key, value in breakdown.items()},
            'priceSnapshot': snapshot.as_dict(), 'exchangeRate': fx,
            'usage': {key: str(decimal(value, key)) for key, value in units.items()}}


def subscription_valuation(execution, snapshot, units, *, mapping, usd_cny=None):
    """保留订阅执行身份，以明确匹配的公开价估值，不生成现金扣款。

    mapping 是人工或目录核对证据；价格模型可以不同于执行渠道的模型 ID，
    但必须明确版本对应关系。此函数不修改端点、凭证、信任或预算。
    """
    if not isinstance(execution, dict) or execution.get('billingMode') != 'subscription':
        raise ValueError('需要明确订阅执行路线')
    route = {key: _text(execution.get(key), key) for key in ('provider', 'model')}
    route['endpoint'] = _url(execution.get('endpoint'))
    route['billingMode'] = 'subscription'
    if not isinstance(mapping, dict) or mapping.get('match') not in ('verified-version', 'published-model-name'):
        raise ValueError('订阅参考价需要已核对的模型版本映射')
    evidence = {'match': mapping['match'],
                'source': _url(mapping.get('source')),
                'checkedAt': _date(mapping.get('checkedAt')),
                'description': _text(mapping.get('description'), '版本对应说明')}
    result = calculate(snapshot, units, usd_cny=usd_cny)
    result.update(basis='reference-price', status='subscription-reference-valuation',
                  executionRoute=route, mapping=evidence,
                  cashCharge=None, cashChargeStatus='not-attributed-per-call',
                  eligibleForCashBudget=False)
    return result


def openrouter_catalog_price(model, *, checked_at):
    """目录价仅作迁移预览；未绑定实际 provider，不能冒充可派发预算价格。"""
    raw = model.get('pricing')
    if not isinstance(raw, dict) or 'prompt' not in raw or 'completion' not in raw:
        raise ValueError('OpenRouter 目录缺少完整价格')
    if raw.get('overrides'):
        raise ValueError('存在条件价格；须按实际 provider 和调用条件物化后使用')
    supported = {'prompt', 'completion', 'request', 'input_cache_read', 'input_cache_write'}
    # 不忽略尚未适配的额外收费，避免把多模态或推理价格算漏。
    for key in set(raw) - supported:
        if key != 'overrides' and decimal(raw[key], key):
            raise ValueError(f'尚未适配 OpenRouter 价格维度：{key}')
    rates = {'input': raw['prompt'], 'output': raw['completion'], 'request': raw.get('request', '0')}
    for source, target in (('input_cache_read', 'cachedInput'), ('input_cache_write', 'cacheWrite')):
        if source in raw:
            rates[target] = raw[source]
    return PriceSnapshot.read({'schemaVersion': VERSION, 'provider': 'openrouter',
        'model': model.get('id'), 'endpoint': 'https://openrouter.ai/api/v1',
        'currency': 'USD', 'rates': rates, 'source': 'https://openrouter.ai/api/v1/models',
        'checkedAt': checked_at, 'basis': 'reference-price'})


def reference_price(reference, *, input_tokens=None):
    """参考价阶梯：默认返回预留上界，结算按实际总输入选择冻结阶梯。"""
    upper = PriceSnapshot.read(reference.get('price'))
    schedule = reference.get('schedule')
    if schedule is None:
        return upper
    if not isinstance(schedule, list) or not schedule:
        raise ValueError('参考阶梯必须为非空列表')
    tiers = []
    previous = -1
    for item in schedule:
        if not isinstance(item, dict) or set(item) != {'minInputTokens', 'price'}:
            raise ValueError('参考阶梯字段无效')
        threshold = item['minInputTokens']
        if type(threshold) is not int or threshold <= previous or (not tiers and threshold != 0):
            raise ValueError('参考阶梯须从零开始严格递增')
        tier = PriceSnapshot.read(item['price'])
        if (tier.provider, tier.model, tier.currency, tier.source) != (upper.provider, upper.model, upper.currency, upper.source):
            raise ValueError('参考阶梯价格身份不一致')
        bounds = dict(upper.rates)
        if any(key not in bounds or value > bounds[key] for key, value in tier.rates):
            raise ValueError('参考价上界未覆盖全部阶梯')
        tiers.append((threshold, tier))
        previous = threshold
    if input_tokens is None:
        return upper
    if type(input_tokens) is not int or input_tokens < 0:
        raise ValueError('参考价阶梯需要有效输入用量')
    return next(tier for threshold, tier in reversed(tiers) if input_tokens >= threshold)
