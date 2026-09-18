"""用已封存的呼叫帳本投影「替換評審模型」能省多少 AFP；零模型呼叫。

輸入是既有付費批次的 analysis.json（call_table 逐次呼叫的 token 與 AFP）與
當時凍結的 manifest（單價表）。輸出各階段的成本結構，以及把評審階段換成
其他候選模型（含本地零 AFP 的 CLI 評審）之後的總額與節省。

投影只做算術，不代表替換後的品質；品質必須另外靠一致性實驗證明。
"""
import argparse
import json
from pathlib import Path

from refractrouter.agent import atomic_json
from refractrouter.quality_study import digest, file_digest

SCHEMA_VERSION = 'judge-cost-projection-v1'
DEFAULT_ANALYSIS = 'reports/pareto-development-v1/live-01-analysis/analysis.json'
DEFAULT_MANIFEST = 'reports/pareto-development-v1/live-01/frozen.json'
DEFAULT_OUT = 'reports/judge-cost-v1/substitution-projection.json'
JUDGE_STAGES = ('delivery-judge', 'research-judge')
LOCAL_FREE = {'model_id': 'local-cli-moa', 'input_cost_per_1k': 0.0,
              'output_cost_per_1k': 0.0, 'provider': 'local-cli'}


def load_prices(manifest_path):
    """取回凍結 manifest 的模型單價與快取單價。"""
    manifest = json.loads(Path(manifest_path).read_text())['manifest']
    prices = {}
    for model in manifest['models']:
        prices[model['model_id']] = {
            'provider': model['provider'],
            'input_cost_per_1k': model['input_cost_per_1k'],
            'output_cost_per_1k': model['output_cost_per_1k'],
            'cached_input_cost_per_1k': model.get('cached_input_cost_per_1k'),
        }
    return prices


def stage_totals(call_table):
    """逐階段加總呼叫數、token 與實際 AFP。"""
    totals = {}
    for row in call_table:
        bucket = totals.setdefault(row['stage'], {'calls': 0, 'input_tokens': 0,
                                                 'output_tokens': 0, 'afp': 0.0})
        bucket['calls'] += 1
        bucket['input_tokens'] += row['input_tokens']
        bucket['output_tokens'] += row['output_tokens']
        bucket['afp'] += row['actual_afp']
    return {stage: {**bucket, 'afp': round(bucket['afp'], 6)}
            for stage, bucket in totals.items()}


def stage_cost(bucket, price):
    """依單價重算某階段的 AFP。"""
    return (bucket['input_tokens'] * price['input_cost_per_1k']
            + bucket['output_tokens'] * price['output_cost_per_1k']) / 1000


def project(call_table, prices, targets=JUDGE_STAGES):
    """回傳基準結構與各替換情境；targets 之外的階段維持原帳。"""
    totals = stage_totals(call_table)
    baseline_afp = round(sum(bucket['afp'] for bucket in totals.values()), 6)
    baseline_calls = sum(bucket['calls'] for bucket in totals.values())
    missing = [stage for stage in targets if stage not in totals]
    if missing:
        raise ValueError('帳本缺少階段：' + ', '.join(missing))
    scenarios = []
    for model_id, price in list(prices.items()) + [(LOCAL_FREE['model_id'], LOCAL_FREE)]:
        for target in targets + (('both',) if len(targets) > 1 else ()):
            stages = list(targets) if target == 'both' else [target]
            replaced = sum(bucket['afp'] for stage, bucket in totals.items() if stage in stages)
            substituted = sum(stage_cost(totals[stage], price) for stage in stages)
            total = round(baseline_afp - replaced + substituted, 6)
            scenarios.append({
                'name': f'{target} → {model_id}',
                'stages': stages,
                'model_id': model_id,
                'provider': price['provider'],
                'unit_price_afp': price['input_cost_per_1k'],
                'replaced_afp': round(replaced, 6),
                'substituted_afp': round(substituted, 6),
                'projected_total_afp': total,
                'saving_afp': round(baseline_afp - total, 6),
                'saving_share': round((baseline_afp - total) / baseline_afp, 6),
                'relative_total': round(total / baseline_afp, 6),
            })
    no_cache_discount = all(
        price.get('cached_input_cost_per_1k') in (None, price['input_cost_per_1k'])
        for price in prices.values())
    return {
        'schema_version': SCHEMA_VERSION,
        'baseline': {'calls': baseline_calls, 'afp': baseline_afp,
                     'by_stage': totals,
                     'judge_share': round(sum(totals[stage]['afp'] for stage in targets)
                                          / baseline_afp, 6)},
        'price_table': prices,
        'scenarios': scenarios,
        'notes': {
            'cache_discount': ('凍結單價表的快取輸入價等於未快取價，'
                               '前綴快取不減少 AFP。' if no_cache_discount else
                               '部分模型有快取折扣，未計入本投影。'),
            'scope': ('純算術投影；token 量取自舊批次帳本，替換後的品質與時延'
                      '不在本投影的結論範圍。'),
        },
    }


def main():
    parser = argparse.ArgumentParser(description='投影替換評審模型的 AFP 節省（零呼叫）')
    parser.add_argument('--analysis', default=DEFAULT_ANALYSIS)
    parser.add_argument('--manifest', default=DEFAULT_MANIFEST)
    parser.add_argument('--out', default=DEFAULT_OUT)
    args = parser.parse_args()
    analysis = json.loads(Path(args.analysis).read_text())
    report = project(analysis['call_table'], load_prices(args.manifest))
    report['source'] = {'analysis_path': args.analysis,
                        'analysis_sha256': file_digest(args.analysis),
                        'manifest_path': args.manifest,
                        'manifest_sha256': file_digest(args.manifest),
                        'call_table_sha256': digest(analysis['call_table'])}
    atomic_json(Path(args.out), report)
    print(json.dumps({'baseline': report['baseline']['afp'],
                      'scenarios': [[s['name'], s['projected_total_afp'], s['saving_share']]
                                    for s in report['scenarios']]},
                     ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
