"""从独立节点观测导入能力分层，不从整任务评分或模型名称推断节点成绩。"""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path

from .profile_calibration import build_stratified_profile
from .routing_actions import action_binding

VERSION = 'node-quality-bundle-v1'
MAX_BYTES = 16 * 1024 * 1024


def import_node_quality(path, configuration):
    """只读、冻结并校验完整候选矩阵；局部语义失败显式排除对应分层。"""
    source = Path(path).expanduser().resolve()
    if not source.is_file() or source.stat().st_size > MAX_BYTES:
        raise ValueError('节点能力档案不存在或超过 16 MiB')
    content = source.read_bytes()
    raw = json.loads(content)
    if (not isinstance(raw, dict) or raw.get('schema_version') != VERSION
            or raw.get('kind') != 'empirical'):
        raise ValueError('节点能力档案必须包含独立的真实节点观测')
    corpus = raw.get('observations')
    if not isinstance(corpus, dict) or corpus.get('kind') != 'empirical':
        raise ValueError('模拟观测不能用作产品节点质量')
    bindings = raw.get('action_bindings')
    if not isinstance(bindings, dict) or not bindings:
        raise ValueError('节点能力档案缺少实际模型及参数绑定')
    candidates = {m.model_id: m for m in configuration.manifest.candidates}
    if not set(bindings) <= set(candidates):
        raise ValueError('节点能力档案包含当前执行模型池之外的路线')
    if any(bindings[mid] != action_binding(candidates[mid]) for mid in bindings):
        raise ValueError('节点能力档案与当前模型版本、推理参数或价格不匹配')
    execution_bindings = raw.get('execution_action_bindings')
    if execution_bindings is not None:
        from .application_config import execution_capacity_model
        if execution_bindings != {mid: action_binding(execution_capacity_model(candidates[mid])) for mid in bindings}:
            raise ValueError('节点能力档案与实际执行输出容量不匹配')
    manifest = replace(configuration.manifest, models=tuple(candidates[mid] for mid in bindings))
    profile = build_stratified_profile(corpus, manifest,
        calibration_task_ids=raw.get('calibration_task_ids', []),
        test_task_ids=raw.get('held_out_task_ids', []), min_samples=3,
        allow_unavailable_evaluation=True)
    validation = raw.get('held_out_observations')
    validation_profile = None
    if validation is not None:
        if not isinstance(validation, dict) or validation.get('kind') != 'empirical':
            raise ValueError('保留集必须包含独立的真实节点观测')
        # 保留集只用于否决已知失败，不参与校准平均分或输出用量预测。
        validation_profile = build_stratified_profile(validation, manifest,
            calibration_task_ids=raw.get('held_out_task_ids', []),
            test_task_ids=raw.get('calibration_task_ids', []), min_samples=3,
            allow_unavailable_evaluation=True)
    def stratum(row):
        return tuple(row[k] for k in ('model_id', 'node_type', 'difficulty', 'risk',
                                     'input_min_tokens', 'input_max_tokens'))
    vetoes = {stratum(row): 'held-out-' + row['reason']
        for row in (validation_profile or {}).get('exclusions', ())
        if row['reason'] != 'insufficient-samples'}
    digest = hashlib.sha256(content).hexdigest()
    profiles = {mid: [] for mid in bindings}
    rows = [(row, None) for row in profile['candidates']]
    rows += [(row, row['reason']) for row in profile['exclusions']]
    exclusions = []
    for row, excluded in rows:
        excluded = excluded or vetoes.get(stratum(row))
        # 无法确认或语义失败不能退回更乐观的全局分数。
        model = candidates[row['model_id']]
        forecast = configuration.predictions[model.model_id]
        aligned = [obs for obs in corpus['observations']
            if obs['model_id'] == row['model_id']
            and obs['features']['node_type'] == row['node_type']
            and obs['features']['difficulty'] == row['difficulty']
            and obs['features']['risk'] == row['risk']
            and row['input_min_tokens'] <= obs['features']['input_budget_tokens'] < row['input_max_tokens']]
        mean_output = math.ceil(sum(obs['usage']['output_tokens'] for obs in aligned) / len(aligned))
        validated = [obs for obs in (validation or {}).get('observations', ())
            if obs['model_id'] == row['model_id']
            and obs['features']['node_type'] == row['node_type']
            and obs['features']['difficulty'] == row['difficulty']
            and obs['features']['risk'] == row['risk']
            and row['input_min_tokens'] <= obs['features']['input_budget_tokens'] < row['input_max_tokens']]
        if excluded:
            exclusions.append({**{k: row[k] for k in ('model_id', 'node_type', 'difficulty', 'risk',
                                                     'input_min_tokens', 'input_max_tokens')},
                               'reason': excluded})
        profiles[model.model_id].append({
            'nodeType': row['node_type'], 'difficulty': row['difficulty'], 'risk': row['risk'],
            'inputMinTokens': row['input_min_tokens'], 'inputMaxTokens': row['input_max_tokens'],
            'quality': 0 if excluded else row['quality'],
            'latencyMs': forecast['latency_ms'] if excluded else max(1, row['latency_ms']),
            **({'outputTokens': mean_output} if not excluded and mean_output > 0 else {}),
            'evidence': {'kind': 'independent-node-evaluation',
                'samples': len(aligned), 'bundleSha256': digest,
                'observationSha256': profile['observation_sha256'],
                'excludedReason': excluded, 'outputUsageMeanTokens': mean_output,
                'heldOutSamples': len(validated),
                'heldOutStatus': ('failed' if stratum(row) in vetoes else 'passed' if validated
                                  else 'not-observed'),
                'heldOutObservationSha256': (validation_profile or {}).get('observation_sha256'),
                'latencySource': 'independent-node-observations'},
        })
    return profiles, {'schema_version': VERSION, 'bundle_sha256': digest,
        'observations_sha256': profile['observation_sha256'],
        'calibration_tasks': profile['calibration_task_ids'],
        'held_out_tasks': profile['held_out_task_ids'],
        'model_count': len(bindings), 'strata': sum(not row['evidence']['excludedReason']
                                                  for values in profiles.values() for row in values),
        'excluded_strata': deepcopy(exclusions),
        'held_out_observations_sha256': (validation_profile or {}).get('observation_sha256'),
        'held_out_policy': 'known-failure-veto-only-no-score-or-usage-fitting',
        'unmatched_policy': 'global-prior-explicitly-unverified',
        'whole_task_scores_used': False}
