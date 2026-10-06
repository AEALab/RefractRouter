"""零调用检查公开目录价格；不更改 provider、预算或用户配置。"""
import argparse
import json
from datetime import date, datetime
from pathlib import Path

from refractrouter.currency_pricing import openrouter_catalog_price
from refractrouter.openrouter_pricing import endpoint_price
from refractrouter.price_refresh import compare_prices


def preview(catalog):
    rows = []
    for entry in catalog['models']:
        row = {'model': entry['id'], 'canonicalModel': entry.get('canonical_slug'),
               'dispatchReady': False}
        try:
            row['price'] = openrouter_catalog_price(
                entry, checked_at=catalog['checkedAt']).as_dict()
            row['status'] = '参考价可读取；实际 provider 与能力待绑定'
        except ValueError as exc:
            row.update(status='价格待适配', reason=str(exc))
        rows.append(row)
    return {'schemaVersion': 'refractrouter-currency-migration-preview-v1',
            'modelCalls': 0, 'configurationChanged': False,
            'source': catalog['source'], 'checkedAt': catalog['checkedAt'], 'models': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--endpoints', type=Path)
    parser.add_argument('--at', help='价格匹配时刻，ISO 8601，必须含时区')
    parser.add_argument('--previous', type=Path, help='上一份预览报告，用于比较价格变化')
    parser.add_argument('--as-of', default=date.today().isoformat(), help='价格有效期诊断日期')
    parser.add_argument('--max-age-days', type=int, default=30, help='查证超过此天数提示刷新')
    args = parser.parse_args()
    report = preview(json.loads(args.catalog.read_text()))
    if args.endpoints:
        if not args.at:
            parser.error('--endpoints 必须同时指定 --at')
        instant = datetime.fromisoformat(args.at)
        report['endpointPrices'] = []
        for document in json.loads(args.endpoints.read_text()):
            for endpoint in document['data']['endpoints']:
                row = {'model': document['model'], 'providerRoute': endpoint['tag'],
                       'dispatchReady': False, 'at': args.at, 'promptTokens': 1000}
                try:
                    row['price'] = endpoint_price(document, endpoint['tag'], at=instant,
                        prompt_tokens=1000).as_dict()
                    row['budgetPrice'] = endpoint_price(document, endpoint['tag'], at=instant,
                        prompt_tokens=1000, upper_bound=True).as_dict()
                    row['status'] = '路线价格可读取；宿主绑定、权限和能力验收待完成'
                except ValueError as exc:
                    row.update(status='价格待适配', reason=str(exc))
                report['endpointPrices'].append(row)
    previous = json.loads(args.previous.read_text()) if args.previous else {}
    for section in ('models', 'endpointPrices'):
        old_rows = {(row['model'], row.get('providerRoute')): row
                    for row in previous.get(section, [])}
        for row in report.get(section, []):
            if 'price' in row:
                old = old_rows.get((row['model'], row.get('providerRoute')), {})
                row['refresh'] = compare_prices(old.get('price'), row['price'],
                    as_of=args.as_of, max_age_days=args.max_age_days)
    # 不覆盖已有批次，包括失败记录。
    with args.output.open('x', encoding='utf-8') as output:
        output.write(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
