"""冻结失败节点的输出格式验证；不调用下游或评审，不改变严格契约。"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from .dag_study_execution import write_json
from .manifest import load_model_manifest
from .task_budget import TaskCallBudget
from .task_contracts import decode_output
from .task_execution import node_messages
from .task_plan import validate_plan
from .task_runtime import validate_models


def load_replay(path):
    path = Path(path)
    raw = json.loads(path.read_text())
    if raw.get('schema_version') != 'text-handoff-replay-v1':
        raise ValueError('unsupported replay protocol')
    manifest_path = (path.parent/raw['manifest_path']).resolve()
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != raw['manifest_sha256']:
        raise ValueError('frozen manifest hash mismatch')
    manifest = load_model_manifest(manifest_path)
    validate_models(manifest)
    if manifest.billing_unit != 'AFP' or any(m.provider != 'ark-plan' for m in manifest.models):
        raise ValueError('replay requires Agent Plan')
    source_path = (path.parent/raw['source_result_path']).resolve()
    if hashlib.sha256(source_path.read_bytes()).hexdigest() != raw['source_result_sha256']:
        raise ValueError('frozen failure evidence changed')
    source = json.loads(source_path.read_text())
    plan = validate_plan(source['plan'], require_v2=True)
    node = next(n for n in plan.nodes if n.node_id == raw['node_id'])
    contract = plan.contracts[node.node_id]
    if node.parents or contract['output']['format'] != 'json':
        raise ValueError('replay only supports a frozen root JSON node')
    # 原始任务来自已归档请求；不可替换为事后简化的任务。
    request_path = (path.parent/raw['source_request_path']).resolve()
    if hashlib.sha256(request_path.read_bytes()).hexdigest() != raw['source_request_sha256']:
        raise ValueError('frozen request changed')
    request = json.loads(request_path.read_text())
    task = json.loads(request['messages'][-1]['content'])['task']
    messages = node_messages(task, node, contract, {})
    messages_hash = hashlib.sha256(json.dumps(messages, ensure_ascii=False).encode()).hexdigest()
    if messages_hash != raw['messages_sha256']:
        raise ValueError('replay prompt changed; refreeze before paid execution')
    if raw['model_ids'] != [m.model_id for m in manifest.candidates] or raw['maximum_calls'] != len(manifest.candidates):
        raise ValueError('replay requires one call per frozen candidate')
    cap = contract['capability']['input_budget_tokens']
    ceiling = 0
    for model in manifest.candidates:
        output = min(model.max_output_tokens, 8192)
        if cap+output > model.context_window:
            raise ValueError('replay context capacity exceeded')
        ceiling += cap/1000*model.input_cost_per_1k + output/1000*model.output_cost_per_1k
    preflight = {'status': 'preflight', 'real_model_calls': 0,
        'protocol_sha256': hashlib.sha256(json.dumps(raw, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        'maximum_calls': len(manifest.candidates), 'max_production_cost': round(ceiling, 8),
        'max_evaluation_cost': 0, 'billing_unit': 'AFP', 'messages_sha256': messages_hash,
        'limitations': ['只验证原始 JSON 输出契约，不运行下游或评审，不证明语义质量或路由收益。',
                       '每模型最多一次，零重试，首个失败停止；不自动重启完整实验。']}
    return raw, manifest, messages, contract, preflight


def run_replay(loaded, output_dir, *, client, production_limit):
    raw, manifest, messages, contract, preflight = loaded
    if client.max_retries != 0 or production_limit < preflight['max_production_cost']:
        raise ValueError('replay requires zero retries and the complete budget envelope')
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=False)
    write_json(out/'protocol.json', raw)
    write_json(out/'manifest.json', asdict(manifest))
    write_json(out/'preflight.json', preflight)
    # TaskCallBudget 要求两个正数上限；本入口固定只调用候选模型的生产账本。
    budget = TaskCallBudget(client, production_limit, 1, max_calls=preflight['maximum_calls'], capture_payload=True)
    result = {'status': 'started', 'nodes': [], 'issues': [], 'evaluation': None}
    def persist():
        result['charged'], result['calls'] = budget.snapshot()
        write_json(out/'result.json', result)
    budget.on_reserve = lambda reservation: persist()
    budget.on_response = lambda row, response: write_json(out/(row['model_id']+'-response.json'), asdict(response))
    try:
        for model in manifest.candidates:
            response = budget.complete(model, messages, label='contract-replay:'+model.model_id,
                                       json_mode=True, timeout_seconds=120)
            decode_output(response.content, contract)
            result['nodes'].append({'model_id': model.model_id, 'contract_status': 'structure-valid',
                                   'semantic_status': 'not-evaluated'})
            persist()
        result['status'] = 'contract-valid'
    except Exception as exc:
        budget.stop()
        result['status'] = 'failed'
        result['issues'] = [str(exc) if isinstance(exc, ValueError) else type(exc).__name__]
    finally:
        persist()
        write_json(out/'artifact-index.json', {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(out.iterdir()) if p.is_file() and p.name != 'artifact-index.json'})
    return result
