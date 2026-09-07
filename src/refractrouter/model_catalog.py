"""Read the documented Agent Plan model inventory; never invoke models or alter a manifest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parents[2] / 'data/model-catalogs/ark-agent-plan-2026-09-07.json'
CAPABILITIES = ('text-generation', 'embedding', 'image-generation', 'video-generation',
                'speech-synthesis', 'speech-recognition')
PLAN_TIERS = ('small', 'medium', 'large', 'max')


def load_catalog(path=CATALOG_PATH):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('schema_version') != 'ark-agent-plan-catalog-v1':
        raise ValueError('Unsupported model catalog schema')
    if data.get('base_url') != 'https://ark.cn-beijing.volces.com/api/plan/v3':
        raise ValueError('Agent Plan catalog must use the dedicated endpoint')
    seen = set()
    for model in data['models']:
        if model['model_id'] in seen:
            raise ValueError('Duplicate catalog model')
        seen.add(model['model_id'])
        if model['capability'] not in CAPABILITIES or not set(model['plan_tiers']) <= set(PLAN_TIERS):
            raise ValueError('Unknown model capability or plan tier')
        if not model.get('sources'):
            raise ValueError('Catalog model requires source attribution')
    return data


def list_models(*, capability=None, plan_tier=None, catalog=None):
    if capability is not None and capability not in CAPABILITIES:
        raise ValueError('Unknown capability')
    if plan_tier is not None and plan_tier not in PLAN_TIERS:
        raise ValueError('Unknown plan tier')
    data = load_catalog() if catalog is None else catalog
    return [model for model in data['models']
            if (capability is None or model['capability'] == capability)
            and (plan_tier is None or plan_tier in model['plan_tiers'])]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, default=CATALOG_PATH)
    parser.add_argument('--capability', choices=CAPABILITIES)
    parser.add_argument('--plan-tier', choices=PLAN_TIERS)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    catalog = load_catalog(args.catalog)
    models = list_models(capability=args.capability, plan_tier=args.plan_tier, catalog=catalog)
    if args.json:
        print(json.dumps(dict(snapshot_date=catalog['snapshot_date'], model_calls=0,
                             account_plan_tier=catalog['account_plan_tier'], models=models), ensure_ascii=False, indent=2))
    else:
        print(f"Agent Plan documented inventory ({catalog['snapshot_date']}); account entitlement unverified.")
        print('Model | Capability | Plan tiers | Integration | Lifecycle')
        for model in models:
            print(' | '.join((model['model_id'], model['capability'], ','.join(model['plan_tiers']),
                              model['integration'], model['lifecycle'])))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
