"""把 DSH 宿主模型目录编译为核心 v4 配置；运行时不联网更新公开档案。"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

from .application_config import compile_configuration


PROFILE_PATHS = (
    Path(__file__).resolve().parents[2] / 'data/model-profiles-v2.json',
    Path(sys.prefix) / 'share/refractrouter/model-profiles-v2.json',
    Path(__file__).resolve().parents[2] / 'data/model-profiles-v1.json',
    Path(sys.prefix) / 'share/refractrouter/model-profiles-v1.json',
)
PROFILE_SCHEMAS = {'refractrouter-model-profiles-v1', 'refractrouter-model-profiles-v2'}
DEPLOYMENTS = {'local', 'external-cloud', 'trusted-cloud', 'simulated-local'}


def _route_key(provider, model):
    return f'{provider}/{model}'


def _stable_id(prefix, value):
    return f'{prefix}-{hashlib.sha256(value.encode()).hexdigest()[:16]}'


def _record(value, label):
    if not isinstance(value, dict):
        raise ValueError(f'{label} must be an object')
    return value


def _number(value, label):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value < float('inf'):
        raise ValueError(f'{label} must be a non-negative finite number')
    return float(value)


def load_frozen_profiles(path=None):
    if path is None:
        path = next((candidate for candidate in PROFILE_PATHS if candidate.is_file()), PROFILE_PATHS[0])
    raw = json.loads(Path(path).read_text())
    if raw.get('schema_version') not in PROFILE_SCHEMAS or not isinstance(raw.get('profiles'), list):
        raise ValueError('invalid frozen model profile resource')
    identities = set()
    for profile in raw['profiles']:
        if (not isinstance(profile, dict) or not isinstance(profile.get('provider'), str)
                or not profile['provider'] or not isinstance(profile.get('model'), str) or not profile['model']):
            raise ValueError('frozen model profiles require provider/model identities')
        identity = (profile['provider'], profile['model'])
        if identity in identities:
            raise ValueError('frozen model profile identities must be unique')
        identities.add(identity)
        if raw['schema_version'] == 'refractrouter-model-profiles-v2':
            _validate_price_schedule(profile)
    return raw


def _validate_price_schedule(profile):
    pricing = _record(profile.get('pricing'), 'profile pricing')
    if pricing.get('unit') != 'USD' or set(pricing) != {
            'unit', 'inputPer1k', 'cachedInputPer1k', 'outputPer1k'}:
        raise ValueError('v2 frozen profiles require complete USD budget pricing')
    for key in ('inputPer1k', 'cachedInputPer1k', 'outputPer1k'):
        _number(pricing[key], f'profile pricing {key}')
    if pricing['cachedInputPer1k'] > pricing['inputPer1k']:
        raise ValueError('profile cachedInputPer1k cannot exceed inputPer1k')
    basis = _record(profile.get('pricing_basis'), 'profile pricing basis')
    if basis.get('kind') not in {'direct-provider-public-price', 'manufacturer-reference'}:
        raise ValueError('invalid profile pricing basis')
    if basis.get('equivalence') not in {'official-route', 'official-alias', 'unverified'}:
        raise ValueError('invalid profile price equivalence')
    if basis['kind'] == 'manufacturer-reference' and basis['equivalence'] != 'unverified':
        raise ValueError('manufacturer reference must not imply provider equivalence')
    schedule = _record(profile.get('pricing_schedule'), 'profile pricing schedule')
    if schedule.get('unit') != 'USD' or schedule.get('perTokens') != 1000:
        raise ValueError('invalid profile price schedule unit')
    tiers = schedule.get('tiers')
    if not isinstance(tiers, list) or not tiers:
        raise ValueError('profile price schedule requires tiers')
    tier_ids = set()
    for tier in tiers:
        tier = _record(tier, 'profile pricing tier')
        tier_id = tier.get('id')
        if not isinstance(tier_id, str) or not tier_id or tier_id in tier_ids:
            raise ValueError('profile pricing tier ids must be unique')
        tier_ids.add(tier_id)
        if not isinstance(tier.get('conditions'), dict):
            raise ValueError('profile pricing tier requires conditions')
        prices = _record(tier.get('prices'), 'profile tier prices')
        for key in ('inputPer1k', 'cachedInputPer1k', 'outputPer1k'):
            _number(prices.get(key), f'profile tier {key}')
        for key in set(prices) - {'inputPer1k', 'cachedInputPer1k', 'outputPer1k',
                                  'cacheWritePer1k'}:
            raise ValueError(f'unsupported profile tier price: {key}')
        if 'cacheWritePer1k' in prices:
            _number(prices['cacheWritePer1k'], 'profile tier cacheWritePer1k')
        budget = _record(tier.get('budgetPricing'), 'profile tier budget pricing')
        if set(budget) != {'inputPer1k', 'cachedInputPer1k', 'outputPer1k'}:
            raise ValueError('profile tier requires complete budget pricing')
        for key in budget:
            _number(budget[key], f'profile tier budget {key}')
    materialization = _record(profile.get('pricing_materialization'),
                              'profile pricing materialization')
    if materialization.get('strategy') != 'conservative-upper-bound':
        raise ValueError('v2 frozen profiles require conservative price materialization')
    selected = materialization.get('selectedTier')
    if selected not in tier_ids:
        raise ValueError('profile pricing materialization references an unknown tier')
    selected_budget = next(tier['budgetPricing'] for tier in tiers if tier['id'] == selected)
    if any(pricing[key] != selected_budget[key]
           for key in ('inputPer1k', 'cachedInputPer1k', 'outputPer1k')):
        raise ValueError('profile pricing must match the selected conservative tier')


def compile_dsh_model_pool(pool, catalog_snapshot, *, profiles=None):
    """返回可交给现有核心的 v4 配置与逐路线来源证据。"""
    pool = _record(pool, 'dshModelPool')
    snapshot = _record(catalog_snapshot, 'dshCatalogSnapshot')
    if pool.get('schemaVersion') != 'refractagent-dsh-model-pool-v1':
        raise ValueError('invalid dshModelPool schemaVersion')
    if snapshot.get('schemaVersion') != 'refractagent-dsh-catalog-v1':
        raise ValueError('invalid dshCatalogSnapshot schemaVersion')
    allow_shared_judge = pool.get('allowSharedJudge', False)
    if not isinstance(allow_shared_judge, bool):
        raise ValueError('dshModelPool.allowSharedJudge must be a boolean')
    routes = pool.get('routes')
    if not isinstance(routes, list):
        raise ValueError('dshModelPool.routes must be an array')
    catalog = {(_record(row, 'catalog route').get('provider'), row.get('model')): row
               for row in snapshot.get('routes', [])}
    frozen = profiles or load_frozen_profiles()
    public = {(row['provider'], row['model']): row for row in frozen['profiles']}
    if profiles is None and frozen['schema_version'] == 'refractrouter-model-profiles-v2':
        legacy_path = next((candidate for candidate in PROFILE_PATHS[2:] if candidate.is_file()), None)
        if legacy_path is not None:
            legacy = load_frozen_profiles(legacy_path)
            for row in legacy['profiles']:
                public.setdefault((row['provider'], row['model']), row)
    selected, evidence = [], {}
    seen = set()
    for raw in routes:
        row = _record(raw, 'dshModelPool route')
        if row.get('enabled', True) is False:
            continue
        provider, model = row.get('provider'), row.get('model')
        if not isinstance(provider, str) or not provider or not isinstance(model, str) or not model:
            raise ValueError('dshModelPool routes require provider and model')
        if provider == 'refractagent':
            raise ValueError('RefractAgent cannot route recursively to itself')
        identity = (provider, model)
        if identity in seen:
            raise ValueError('dshModelPool route identities must be unique')
        seen.add(identity)
        resolved = catalog.get(identity)
        if resolved is None:
            raise ValueError(f'DSH route is unavailable: {_route_key(provider, model)}')
        deployment = row.get('deployment')
        if deployment not in DEPLOYMENTS:
            raise ValueError('every DSH route requires an explicit deployment')
        base = deepcopy(public.get(identity, {}))
        overrides = _record(row.get('overrides', {}), 'route overrides')
        manual_complete = all(key in overrides for key in ('inputPer1k','outputPer1k','quality','latencyMs'))
        if not base and not manual_complete:
            raise ValueError(f'{_route_key(provider, model)} has no public profile; complete manual overrides are required')
        pricing = {**deepcopy(base.get('pricing') or {}),
                   **{k: overrides[k] for k in ('inputPer1k','cachedInputPer1k','outputPer1k') if k in overrides}}
        quality = overrides.get('quality', base.get('quality'))
        latency = overrides.get('latencyMs', base.get('latencyMs'))
        for key in ('inputPer1k', 'outputPer1k'):
            if key not in pricing:
                raise ValueError(f'{_route_key(provider, model)} requires complete manual pricing')
            pricing[key] = _number(pricing[key], key)
        pricing['cachedInputPer1k'] = _number(pricing.get('cachedInputPer1k', pricing['inputPer1k']), 'cachedInputPer1k')
        if pricing['cachedInputPer1k'] > pricing['inputPer1k']:
            raise ValueError('cachedInputPer1k cannot exceed inputPer1k')
        quality = _number(quality, 'quality') if quality is not None else None
        latency = _number(latency, 'latencyMs') if latency is not None else None
        if quality is None or quality > 100 or latency is None:
            raise ValueError(f'{_route_key(provider, model)} requires quality and latency predictions')
        context_window = resolved.get('contextWindow')
        max_output_tokens = resolved.get('maxOutputTokens')
        if not isinstance(context_window, int) or isinstance(context_window, bool) or context_window <= 0:
            raise ValueError(f'{_route_key(provider, model)} has no valid context window')
        if max_output_tokens is not None and (not isinstance(max_output_tokens, int)
                or isinstance(max_output_tokens, bool) or max_output_tokens <= 0):
            raise ValueError(f'{_route_key(provider, model)} has no valid output limit')
        selected.append({'provider': provider, 'model': model, 'deployment': deployment,
            'trustPolicy': row.get('trustPolicy'), 'contextWindow': resolved.get('contextWindow'),
            'maxOutputTokens': resolved.get('maxOutputTokens'), 'pricing': pricing,
            'quality': quality, 'latencyMs': latency})
        route_evidence = {
            'profile': 'user-declared-uncalibrated' if manual_complete and not base else 'frozen-public-profile',
            'samples': 0,
            'sources': deepcopy(base.get('sources', [])),
            'overrides': sorted(overrides),
            'note': overrides.get('note'),
        }
        for key in ('pricing_basis', 'pricing_schedule', 'pricing_materialization'):
            if key in base:
                route_evidence[key] = deepcopy(base[key])
        evidence[_route_key(provider, model)] = route_evidence
    if not selected:
        raise ValueError('dshModelPool requires at least one enabled route')
    overrides = _record(pool.get('roleOverrides', {}), 'roleOverrides')
    by_key = {_route_key(row['provider'], row['model']): row for row in selected}
    ranked = sorted(selected, key=lambda row: (row['quality'], row['contextWindow']), reverse=True)
    def exact(name):
        value = overrides.get(name)
        if value is None:
            return None
        if value not in by_key:
            raise ValueError(f'roleOverrides.{name} references an unavailable route')
        return by_key[value]
    judge = exact('judge') or ranked[0]
    workers = overrides.get('workers')
    if workers is None:
        worker_rows = [row for row in ranked if row is not judge]
        if not worker_rows and allow_shared_judge:
            worker_rows = [judge]
    else:
        if not isinstance(workers, list) or not workers or any(key not in by_key for key in workers):
            raise ValueError('roleOverrides.workers must reference available routes')
        worker_rows = [by_key[key] for key in dict.fromkeys(workers)]
    if not worker_rows:
        raise ValueError('worker and judge must use separate routes unless allowSharedJudge is enabled')
    if judge in worker_rows and not allow_shared_judge:
        raise ValueError('shared worker and judge route requires allowSharedJudge')
    planner = exact('planner') or ranked[0]
    classifier_candidates = [row for row in ranked if row['deployment'] in {'local','trusted-cloud','simulated-local'}]
    classifier = exact('classifier') or (classifier_candidates[0] if classifier_candidates else None)
    if classifier is None:
        raise ValueError('no deployment-compatible classifier route')
    provider_ids = {_route_key(row['provider'], row['model']):
                    _stable_id('dsh-provider', _route_key(row['provider'], row['model'])) for row in selected}
    providers = []
    for row in selected:
        route_key = _route_key(row['provider'], row['model'])
        providers.append({'id': provider_ids[route_key], 'type': 'dsh', 'dshProvider': row['provider'],
            'deployment': row['deployment'],
            **({'trustPolicy': row['trustPolicy']} if row.get('trustPolicy') else {})})
    models = []
    for row in selected:
        roles = []
        if row is planner: roles.append('planner')
        if row in worker_rows: roles.append('worker')
        if row is judge: roles.append('judge')
        if row is classifier: roles.append('classifier')
        if not roles:
            continue
        evidence[_route_key(row['provider'], row['model'])]['assigned_roles'] = roles
        evidence[_route_key(row['provider'], row['model'])]['independent_judge'] = (
            'worker' not in roles if 'judge' in roles else None)
        models.append({'id': _stable_id('dsh-model', _route_key(row['provider'], row['model'])),
            'provider': provider_ids[_route_key(row['provider'], row['model'])],
            'model': row['model'], 'roles': roles, 'contextWindow': row['contextWindow'],
            'maxOutputTokens': row['maxOutputTokens'], 'deployment': row['deployment'],
            'pricing': {'unit': pool.get('billingUnit', 'USD'), **row['pricing']},
            'routing': {'quality': row['quality'], 'latencyMs': row['latencyMs']} if 'worker' in roles else None})
        if models[-1]['routing'] is None: models[-1].pop('routing')
    security = deepcopy(pool.get('security', {'dataMode':'live','sensitiveTerms':[],
        'classifier':{'enabled':True,'modelId':_route_key(classifier['provider'], classifier['model'])}}))
    if isinstance(security.get('classifier'), dict) and security['classifier'].get('enabled', True):
        security['classifier']['modelId'] = _stable_id('dsh-model', _route_key(classifier['provider'], classifier['model']))
    config = {'schemaVersion':'refractagent-providers-v4', 'billingUnit':pool.get('billingUnit','USD'),
        'allowSharedJudge':allow_shared_judge,
        'objective':deepcopy(pool.get('objective', {'qualityMin':80,'primary':'cost','secondary':'latency','dagMode':'auto'})),
        'security':security, 'trustPolicies':deepcopy(pool.get('trustPolicies', [])),
        'providers':providers, 'models':models}
    compile_configuration(config)
    return config, evidence
