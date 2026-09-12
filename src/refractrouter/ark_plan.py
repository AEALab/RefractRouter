"""官方文字模型清单、AFP 成本分档与应用配置；不改写冻结实验 manifest。"""
from copy import deepcopy
from importlib.resources import files
import json


def catalog():
    return json.loads(files('refractrouter').joinpath('resources/ark-agent-plan-catalog.json').read_text())


def afp_metadata():
    data = catalog()
    models = [row for row in data['models'] if row['capability'] == 'text-generation']
    coefficients = sorted({max(m['pricing']['input_coefficient'], m['pricing']['output_coefficient']) for m in models})
    return {
        'snapshotDate': data['snapshot_date'], 'sourceUrl': data['pricing_url'],
        'tiers': coefficients,
        'models': [{
            'model': m['model_id'], 'coefficient': max(m['pricing']['input_coefficient'], m['pricing']['output_coefficient']),
            'inputCoefficient': m['pricing']['input_coefficient'], 'outputCoefficient': m['pricing']['output_coefficient'],
            'planTiers': m['plan_tiers'],
        } for m in models],
    }


def application_configuration():
    """按常规 AFP 价格导出完整文字模型池；价格不能推导质量预测。"""
    models = []
    for row in catalog()['models']:
        if row['capability'] != 'text-generation':
            continue
        pricing = row['pricing']
        models.append({
            'id': row['model_id'], 'model': row['model_id'], 'provider': 'ark-plan', 'role': 'candidate',
            'contextWindow': row['context_window_tokens'], 'maxOutputTokens': 8192,
            'jsonMode': row.get('json_mode_strategy', 'json-object-hint'),
            'requestOptions': {'thinking': {'type': 'enabled' if row.get('thinking_policy') == 'required-cannot-disable' else 'auto'}},
            'pricing': {'unit': 'AFP', 'inputPer1k': pricing['input_coefficient'] / 10,
                        'outputPer1k': pricing['output_coefficient'] / 10,
                        'cachedInputPer1k': pricing['input_coefficient'] / 10},
            'routing': {'quality': 80, 'latencyMs': 10000},
        })
    judge = deepcopy(next(m for m in models if m['model'] == 'kimi-k3'))
    judge.update(id='evaluation-kimi-k3', role='judge')
    del judge['routing']
    models.append(judge)
    return {
        'schemaVersion': 'refractagent-providers-v1', 'billingUnit': 'AFP', 'qualityMin': 0,
        'providers': [{'id': 'ark-plan', 'type': 'ark-agent-plan', 'credentialEnv': 'CODEX_ARK_API_KEY'}],
        'models': models,
    }
