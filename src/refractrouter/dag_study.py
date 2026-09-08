"""冻结多任务对照的校验与零调用费用预检。"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .manifest import load_model_manifest
from .model_selection import Weights
from .node_routing import number
from .task_plan import validate_plan
from .task_scheduling import ExecutionPolicy
from .task_runtime import validate_models

METHODS = ('direct-strong', 'dag-strong-serial', 'dag-strong-parallel',
           'dag-calibrated-single', 'dag-node-a', 'dag-node-b')
SYMMETRIC_METHODS = METHODS + ('dag-single-a', 'dag-single-b')


def study_methods(raw):
    expected = {'dag-routing-study-v1': METHODS, 'dag-routing-study-v2': SYMMETRIC_METHODS,
                'dag-routing-study-v3': SYMMETRIC_METHODS}.get(raw.get('schema_version'))
    if expected is None or tuple(raw.get('methods', [])) != expected:
        raise ValueError('unsupported study protocol')
    return expected


def implementation_fingerprint():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(__file__).parent.glob('*.py'))}


def validate_implementation(raw):
    if ('implementation_sha256' in raw
            and raw['implementation_sha256'] != implementation_fingerprint()):
        raise ValueError('frozen implementation changed; create a new protocol revision')


def load_study(path):
    path = Path(path)
    raw = json.loads(path.read_text())
    study_methods(raw)
    if raw['schema_version'] != 'dag-routing-study-v1' and type(raw.get('method_order_seed')) is not int:
        raise ValueError('v2 study requires a frozen method order seed')
    validate_implementation(raw)
    manifest_path = (path.parent / raw['manifest_path']).resolve()
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != raw.get('manifest_sha256'):
        raise ValueError('frozen manifest hash mismatch')
    manifest = load_model_manifest(manifest_path)
    validate_models(manifest)
    if manifest.billing_unit != 'AFP' or any(m.provider != 'ark-plan' for m in manifest.models):
        raise ValueError('study only supports Ark Agent Plan')
    if raw.get('reference_model_id') not in {m.model_id for m in manifest.candidates}:
        raise ValueError('invalid reference model')
    for key in ('calibration_repeats', 'test_repeats'):
        if type(raw.get(key)) is not int or not 1 <= raw[key] <= 5:
            raise ValueError('invalid frozen repeats')
    policy = ExecutionPolicy.from_request(raw['execution_policy'])
    if set(policy.provider_concurrency) | set(policy.provider_min_interval_ms) != {'ark-plan'}:
        raise ValueError('study policy requires the explicit Ark provider boundary')
    ids, families = set(), {}
    for task in raw['tasks']:
        if not isinstance(task.get('task_id'), str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', task['task_id']) or task['task_id'] in ids or task.get('split') not in ('calibration', 'test'):
            raise ValueError('invalid or duplicate task split')
        ids.add(task['task_id'])
        if not isinstance(task.get('task'), str) or not task['task'].strip():
            raise ValueError('empty study task')
        validate_plan(task['plan'], require_v2=True)
        families.setdefault(task['family'], set()).add(task['split'])
    if not families or any(splits != {'calibration', 'test'} for splits in families.values()):
        raise ValueError('every family needs disjoint calibration and test tasks')
    if manifest.judge.api_model in {m.api_model for m in manifest.candidates}:
        raise ValueError('independent judge must differ from candidates')
    constraints = raw['constraints']
    number(constraints['qualityMin'], 'qualityMin', maximum=100)
    number(constraints['costMax'], 'costMax', positive=True)
    number(constraints['latencyMaxMs'], 'latencyMaxMs', positive=True)
    Weights(**constraints['weights']).normalized()
    for key in ('node_judge', 'final_judge'):
        cap = raw['input_caps'][key]
        if type(cap) is not int or not 256 <= cap <= 262144:
            raise ValueError('invalid judge input cap')
    failure_policy = ('isolate-observation-stop-on-infrastructure' if raw['schema_version'] == 'dag-routing-study-v3'
                      else 'stop-on-first-unavailable-or-invalid-result')
    if raw.get('failure_policy') != failure_policy:
        raise ValueError('unsupported experiment failure policy')
    if raw['schema_version'] == 'dag-routing-study-v3':
        from .dag_batch_study import validate_batch_protocol
        validate_batch_protocol(raw, manifest, path.parent)
    for key in ('minimum_final_quality', 'maximum_mean_quality_loss', 'minimum_cost_saving_fraction', 'maximum_latency_ratio'):
        number(raw['acceptance'][key], key)
    if (raw['acceptance']['bootstrap_unit'] != 'task_id' or type(raw['acceptance']['bootstrap_repeats']) is not int
            or not 100 <= raw['acceptance']['bootstrap_repeats'] <= 10000 or type(raw['acceptance']['bootstrap_seed']) is not int):
        raise ValueError('invalid bootstrap protocol')
    return raw, manifest


def study_preflight(raw, manifest):
    validate_implementation(raw)
    reference = next(m for m in manifest.candidates if m.model_id == raw['reference_model_id'])
    production = evaluation = 0.0
    calls = {'calibration_nodes': 0, 'calibration_probes': 0, 'node_judges': 0, 'final_judges': 0, 'test_nodes': 0}
    runs = []
    def cost(model, cap):
        output = min(model.max_output_tokens, 8192)
        if cap + output > model.context_window:
            raise ValueError('protocol input/output envelope exceeds model context')
        return cap / 1000 * model.input_cost_per_1k + output / 1000 * model.output_cost_per_1k
    for task in raw['tasks']:
        caps = [n['contract']['capability']['input_budget_tokens'] for n in task['plan']['nodes']]
        if task['split'] == 'calibration':
            if raw.get('calibration_source'):
                continue
            repeats = raw['calibration_repeats']
            n = len(caps) * len(manifest.candidates) * repeats
            calls['calibration_nodes'] += n
            calls['calibration_probes'] += n
            calls['node_judges'] += n
            calls['final_judges'] += len(manifest.candidates) * repeats
            production += 2 * repeats * sum(cost(m, cap) for m in manifest.candidates for cap in caps)
            evaluation += n * cost(manifest.judge, raw['input_caps']['node_judge'])
            evaluation += len(manifest.candidates) * repeats * cost(manifest.judge, raw['input_caps']['final_judge'])
        else:
            for method in study_methods(raw):
                selected_caps = [max(caps)] if method == 'direct-strong' else caps
                repeats = raw['test_repeats']
                if method in ('direct-strong', 'dag-strong-serial', 'dag-strong-parallel'):
                    ceiling = sum(cost(reference, cap) for cap in selected_caps)
                else:
                    ceiling = sum(max(cost(m, cap) for m in manifest.candidates) for cap in selected_caps)
                production += repeats * ceiling
                evaluation += repeats * cost(manifest.judge, raw['input_caps']['final_judge'])
                calls['test_nodes'] += len(selected_caps) * repeats
                calls['final_judges'] += repeats
                runs.append({'task_id': task['task_id'], 'method': method, 'repeats': repeats,
                             'nodes_per_run': len(selected_caps)})
    if raw['schema_version'] == 'dag-routing-study-v3':
        task = next(t for t in raw['tasks'] if t['task_id'] == raw['handoff_task_id'])
        caps = [n['contract']['capability']['input_budget_tokens'] for n in task['plan']['nodes']]
        calls['handoff_nodes'] = 6 * len(caps)
        calls['final_judges'] += 6
        production += 6 * sum(max(cost(m, cap) for m in manifest.candidates) for cap in caps)
        evaluation += 6 * cost(manifest.judge, raw['input_caps']['final_judge'])
    return {'schema_version': 'dag-study-preflight-v1', 'status': 'preflight', 'real_model_calls': 0,
        'protocol_sha256': hashlib.sha256(json.dumps(raw, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        'manifest_sha256': raw['manifest_sha256'], 'planned_calls': calls,
        'maximum_calls': sum(calls.values()), 'test_runs': runs,
        'budget': {'billing_unit': manifest.billing_unit, 'production': round(production, 6),
                   'evaluation': round(evaluation, 6), 'total': round(production + evaluation, 6)},
        'limits': ['依据冻结价格和逐次输入/输出上限估算，无缓存折扣；实际费用按 usage 结算。',
                   '固定计划没有模型规划调用；校准观测和测试严格隔离。',
                   '不含真实 DSH 助手的外层调用；该项需独立预算，不能由此预检授权。',
                   ('样本失败隔离并继续；基础设施异常停止整批。' if raw['schema_version'] == 'dag-routing-study-v3'
                    else '遇首个异常停止；调用数与预算是完整计划的上限，不表示已获准执行。')]}
