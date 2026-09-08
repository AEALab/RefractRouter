"""Installed RefractAgent application: presets, reusable plans and durable results.

All routing remains in the authoritative Python task runtime. A DSH model adapter
only passes the conversation, selected preset and deployment limits to this entry.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
from importlib.resources import files
import json
import os
from dataclasses import asdict

from .application_config import compile_configuration, configured_profile, prepare_configured_plan
from pathlib import Path
from uuid import uuid4

from .manifest import load_model_manifest
from .node_routing import number
from .openai_compatible import OpenAICompatibleClient
from .task_plan import text, validate_plan
from .task_runtime import run_task

PRESETS = {
    'economy': {'name': '省成本', 'method': 'A', 'qualityMin': 80},
    'balanced': {'name': '均衡', 'method': 'B', 'qualityMin': 80,
                 'weights': {'quality': .5, 'cost': .3, 'latency': .2}},
    'quality': {'name': '质量优先', 'method': 'B', 'qualityMin': 80,
                'weights': {'quality': 1, 'cost': 0, 'latency': 0}},
}
POLICY_VERSION = 'refractagent-presets-v1'
MAX_CONTEXT_BYTES = 120000


def resource(name):
    return files('refractrouter').joinpath('resources', name)


def atomic_json(path, value):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def plan_template(name, criteria=None):
    if name == 'compare':
        plan = json.loads(resource('compare-plan.json').read_text())
        # A DSH conversation includes its system instructions and history. The
        # application template reserves capacity for that context at every node.
        for node in plan['nodes']:
            node['contract']['capability']['input_budget_tokens'] = 131072
        if criteria is not None:
            raise ValueError('compare uses its published cost/risk criteria; use single or an explicit plan for custom criteria')
    elif name == 'single':
        criteria = criteria or ['完整回答用户当前任务，遵守提供的材料、约束和输出格式。']
        plan = {
            'schema_version': 'text-task-plan-v2',
            'decomposition_reason': '整任务模式直接交付，避免不必要的拆分、规划调用与上下文交接。',
            'nodes': [{'node_id': 'answer', 'node_type': 'generation', 'parents': [],
                'prompt_template': '根据完整对话材料回答用户当前任务；不虚构来源或声称完成工具操作。',
                'contract': {
                    'objective': '完整回答当前用户任务，保留要求的输出格式。', 'inputs': {},
                    'output': {'format': 'text', 'fields': {'text': '最终答案'}},
                    'capability': {'difficulty': 'medium', 'risk': 'high',
                                   'input_budget_tokens': 131072, 'expected_output_tokens': 1000},
                    'checks': criteria, 'covers': list(range(len(criteria))),
                    'execution': 'text-model', 'failure_policy': 'stop'}}],
            'final_node_id': 'answer', 'acceptance_criteria': criteria,
        }
    else:
        raise ValueError('template must be single or compare')
    return validate_plan(plan).to_dict()


def build_request(payload, *, mode, production_budget, timeout_ms):
    if not isinstance(payload, dict) or set(payload) - {'task', 'strategy', 'template', 'plan', 'acceptanceCriteria', 'context', 'temperature'}:
        raise ValueError('invalid RefractAgent request fields')
    strategy = payload.get('strategy', 'balanced')
    if not isinstance(strategy, str) or strategy not in PRESETS:
        raise ValueError('strategy must be economy, balanced or quality')
    task = text(payload.get('task'), 'task')
    criteria = payload.get('acceptanceCriteria')
    plan = (validate_plan(payload['plan'], required_criteria=criteria).to_dict() if 'plan' in payload
            else plan_template(payload.get('template', 'single'), criteria))
    request = {**deepcopy(PRESETS[strategy]), 'task': task,
               'mode': {'preflight': 'preflight', 'demo': 'demo', 'live': 'run'}[mode],
               'costMax': number(production_budget, 'production budget', positive=True),
               'latencyMaxMs': number(timeout_ms, 'timeout', positive=True),
               'maxConcurrency': 1, 'maxNodeFallbacks': 0, 'plan': plan}
    del request['name']
    context = payload.get('context', '')
    if not isinstance(context, str) or len(context.encode()) > MAX_CONTEXT_BYTES:
        raise ValueError('conversation context exceeds the RefractAgent input limit')
    return strategy, request, context


def run_agent(payload, *, mode='preflight', runs_dir, production_budget=40,
              evaluation_budget=80, timeout_ms=300000, max_output_tokens=2048,
              manifest_path=None, profile_path=None, execute_paid_run=False,
              client=None, cancel_event=None, provider_config=None, preset=None):
    if mode not in {'preflight', 'demo', 'live'}:
        raise ValueError('mode must be preflight, demo or live')
    if (mode == 'live') != execute_paid_run:
        raise ValueError('live requires explicit --execute-paid-run; preview/demo forbid paid execution')
    number(evaluation_budget, 'evaluation budget', positive=True)
    if type(max_output_tokens) is not int or not 1000 <= max_output_tokens <= 8192:
        raise ValueError('output cap must be an integer in 1000..8192')
    strategy, request, context = build_request(payload, mode=mode, production_budget=production_budget,
                                               timeout_ms=timeout_ms)
    if preset not in {None, 'ark-agent-plan'}:
        raise ValueError('unknown provider preset')
    if provider_config is not None and (preset or manifest_path or profile_path):
        raise ValueError('provider configuration cannot be combined with a preset or manifest/profile')
    if preset and (manifest_path or profile_path):
        raise ValueError('preset cannot be combined with a manifest/profile')
    if (manifest_path is None) != (profile_path is None):
        raise ValueError('custom manifest and profile must be supplied together')
    if mode == 'live' and provider_config is None and preset is None and manifest_path is None:
        raise ValueError('configure providers/models or explicitly select the ark-agent-plan preset')
    configured = compile_configuration(provider_config) if provider_config is not None else None
    if configured:
        manifest = configured.manifest
        request['qualityMin'] = configured.quality_min
        prepare_configured_plan(request, context, explicit_plan='plan' in payload, output_cap=max_output_tokens)

    else:
        manifest_file = Path(manifest_path) if manifest_path else Path(str(resource('agent-plan.json')))
        manifest = load_model_manifest(manifest_file)
        manifest_data = json.loads(manifest_file.read_text())
    temperature = number(payload.get('temperature', 0), 'temperature', maximum=2)
    manifest = replace(manifest, models=tuple(replace(m, max_output_tokens=min(m.max_output_tokens, max_output_tokens))
                                             for m in manifest.models))
    manifest = replace(manifest, models=tuple(replace(m, request_options={**m.request_options, 'temperature': temperature})
                                             if m.role == 'candidate' else m for m in manifest.models))
    if configured:
        manifest_data = {'schema_version': manifest.schema_version, 'billing_unit': manifest.billing_unit,
                         'models': [asdict(m) for m in manifest.models]}
    profile = (configured_profile(configured, manifest, request['plan']) if configured else
               json.loads(Path(profile_path).read_text() if profile_path else resource('report-profile.json').read_text()))
    if mode == 'live' and client is None and any(m.wire_api == 'dsh-llm' for m in manifest.models):
        if os.environ.get('REFRACTROUTER_DSH_BRIDGE') != 'stdio':
            raise ValueError('DSH providers require execution through the DSH plugin')
    if mode == 'live' and client is None:
        environment = os.environ
        private = os.environ.get('REFRACTROUTER_PROVIDER_CREDENTIALS')
        if private is not None:
            try:
                credentials = json.loads(private)
                if not isinstance(credentials, dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in credentials.items()):
                    raise ValueError()
            except (ValueError, TypeError):
                raise ValueError('invalid host credential envelope') from None
            environment = {**os.environ, **credentials}
        client = OpenAICompatibleClient(max_retries=0, environment=environment)
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:12]
    directory = Path(runs_dir).expanduser().resolve() / run_id
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    request_path = directory / 'request.json'
    atomic_json(request_path, {'schema_version': 'refractagent-request-v1', 'payload': payload,
        'runtime_request': request, 'policy_version': POLICY_VERSION, 'mode': mode,
        'production_budget': production_budget, 'evaluation_budget': evaluation_budget,
        'max_output_tokens': max_output_tokens})
    atomic_json(directory / 'profile.json', profile)
    atomic_json(directory / 'manifest.json', manifest_data)
    if configured:
        atomic_json(directory / 'provider-config.json', configured.snapshot)
    result_path = directory / 'result.json'
    result = run_task(request, manifest, profile,
        client=client if mode == 'live' else None,
        production_limit=production_budget, evaluation_limit=evaluation_budget,
        checkpoint=lambda value: atomic_json(result_path, value), cancel_event=cancel_event,
        conversation_context=context, configured_application=configured is not None)
    assignments = result.get('assignments', (result.get('routing') or {}).get('assignments', {}))
    models = {m.model_id: m.api_model for m in manifest.models}
    if mode == 'demo' and result['final_output']:
        result['final_output'] = ('[SIMULATED] RefractAgent 安装演示，未调用真实模型。\n\n'
            + '策略：' + PRESETS[strategy]['name'] + '\n'
            + '模型分配：' + json.dumps({nid: models[mid] for nid,mid in assignments.items()}, ensure_ascii=False) + '\n'
            + '任务：' + request['task'] + '\n\n'
            + '安装、选路和结果保存已完成；启用真实执行后才会生成该任务的答案与独立评审。')
        atomic_json(result_path, result)
    if result['final_output']:
        (directory / 'answer.md').write_text(result['final_output'])
    calls = result['calls']
    totals = {kind: sum(c['charged'] for c in calls if c['category'] == kind and c['status'] == 'billed')
              for kind in ('production', 'evaluation')}
    totals['unconfirmed'] = sum(c['charged'] for c in calls if c['status'] in {'reserved', 'unknown-usage'})
    output = {'schema_version': 'refractagent-result-v1', 'run_id': run_id, 'mode': mode,
        'strategy': strategy, 'strategy_name': PRESETS[strategy]['name'], 'policy_version': POLICY_VERSION,
        'status': result['status'], 'answer': result['final_output'], 'issues': result['issues'],
        'models': {nid: models[mid] for nid, mid in assignments.items()},
        'model_routes': {nid: {'provider': next(m.provider for m in manifest.models if m.model_id==mid), 'model': models[mid]}
                         for nid,mid in assignments.items()},
        'evaluation_model': {'provider': manifest.judge.provider, 'model': manifest.judge.api_model},
        'configuration_source': 'user' if configured else 'manifest' if manifest_path else preset or 'bundled-demo',
        'quality': result['evaluation'], 'costs': totals, 'billing_unit': manifest.billing_unit,
        'simulated': mode == 'demo', 'wall_time_ms': result['wall_time_ms'],
        'result_path': str(result_path), 'run_dir': str(directory),
        'usage': {'input_tokens': sum(c.get('input_tokens', 0)-c.get('cached_input_tokens', 0) for c in calls if c['status'] == 'billed'),
                  'output_tokens': sum(c.get('output_tokens', 0) for c in calls if c['status'] == 'billed'),
                  'cache_read_tokens': sum(c.get('cached_input_tokens', 0) for c in calls if c['status'] == 'billed'),
                  'reasoning_tokens': sum(c.get('reasoning_tokens', 0) for c in calls if c['status'] == 'billed')},
        'profile_scope': profile['scope'], 'limitations': result['limitations'],
        'artifact_hashes': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in sorted(directory.iterdir()) if p.is_file()}}
    atomic_json(directory / 'summary.json', output)
    return output
