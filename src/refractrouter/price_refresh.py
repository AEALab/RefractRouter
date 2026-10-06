"""公开价格刷新诊断；输出差异，不修改运行中已冻结的价格或历史账本。"""
from datetime import date

from .currency_pricing import PriceSnapshot


def compare_prices(previous, current, *, as_of, max_age_days=30):
    """接收适配器物化的价格；路线或币种变化不得解释成单纯涨跌。"""
    if type(max_age_days) is not int or max_age_days < 0:
        raise ValueError('价格有效期必须为非负整数天')
    today = date.fromisoformat(as_of)
    new = PriceSnapshot.read(current)
    age = (today - date.fromisoformat(new.checked_at)).days
    if age < 0:
        raise ValueError('价格查证日期不能晚于诊断日期')
    result = {'asOf': as_of, 'ageDays': age, 'maxAgeDays': max_age_days,
              'freshness': 'current' if age <= max_age_days else 'needs-refresh',
              'configurationWritten': False, 'modelCalls': 0,
              'changes': [], 'identityChanged': False}
    if previous is None:
        result['status'] = 'new-price'
        return result
    old = PriceSnapshot.read(previous)
    identity = ('provider', 'model', 'endpoint', 'provider_route', 'currency', 'basis')
    result['identityChanged'] = any(getattr(old, k) != getattr(new, k) for k in identity)
    before, after = dict(old.rates), dict(new.rates)
    for key in sorted(before.keys() | after.keys()):
        if before.get(key) != after.get(key):
            result['changes'].append({'dimension': key,
                'before': str(before[key]) if key in before else None,
                'after': str(after[key]) if key in after else None})
    result['status'] = ('requires-route-review' if result['identityChanged'] else
                        'price-changed' if result['changes'] else 'unchanged')
    return result
