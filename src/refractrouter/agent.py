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
import math
import os
from dataclasses import asdict

from .application_config import execution_capacity_model, compile_configuration, configured_profile, prepare_configured_plan
from pathlib import Path
from uuid import uuid4

from .routing_actions import action_identity
from .manifest import load_model_manifest
from .node_routing import number
from .openai_compatible import OpenAICompatibleClient
from .output_constraints import validate_output_constraints
from .task_plan import text, validate_plan, preview_plan
from .task_runtime import run_task
from .task_materials import validate_materials
from .agent_progress import ProgressRecorder, dag_snapshot
from .route_observations import RouteObservationStore, route_value_observation
from .live_execution import (authorization_binding, complexity_gate,
                             create_authorization_preview, review_decision,
                             validate_authorization)

PRESETS = {
    'economy': {'name': '省成本', 'method': 'A', 'qualityMin': 80},
    'balanced': {'name': '均衡', 'method': 'B', 'qualityMin': 80,
                 'weights': {'quality': .5, 'cost': .3, 'latency': .2}},
    'quality': {'name': '质量优先', 'method': 'B', 'qualityMin': 80,
                'weights': {'quality': 1, 'cost': 0, 'latency': 0}},
}
AUTO_PRESET = {'name': '自动路由', 'method': 'A', 'qualityMin': 0}
POLICY_VERSION = 'refractagent-presets-v1'
AUTO_POLICY_VERSION = 'refractagent-auto-runtime-v1'
MAX_CONTEXT_BYTES = 120000
RELAXED_CONTEXT_BYTES = 1000000
RELAXED_COST_MAX = 1e12
# 下游选模与原子账本要求有限数；该内部值仅表示用户显式取消金额上限，
# 不作为审计硬预算披露，实际调用仍受模型容量与 v4 调用次数限制。
UNLIMITED_COST_INTERNAL = 1e300
RELAXED_INPUT_CAP = 1_000_000


def resource(name):
    return files('refractrouter').joinpath('resources', name)


def automatic_cost_trace(result, manifest):
    """只投影可公开的费用依据；路由预测、调用预留与结算各自保留原义。"""
    assignments = (result.get('routing') or {}).get('assignments') or {}
    basis = (result.get('routing_profile') or {}).get('forecast_basis') or {}
    models = {model.model_id: model for model in manifest.models}
    selected = []
    expected = {'CNY': 0.0} if result.get('accounting_basis') == 'public-reference-valuation' else {'AFP': 0.0, 'CNY': 0.0}
    for node_id, model_id in assignments.items():
        row = basis.get(node_id, {}).get(model_id)
        model = models.get(model_id)
        if row is None or model is None:
            continue
        amount = (row['input_tokens'] * model.input_cost_per_1k
                  + row['output_tokens'] * model.output_cost_per_1k) / 1000
        unit = model.billing_unit
        expected[unit] = expected.get(unit, 0.0) + amount
        selected.append({'node_id': node_id, 'model_id': model_id, 'unit': unit,
                         'expected_cost': amount, 'expected_input_tokens': row['input_tokens'],
                         'expected_output_tokens': row['output_tokens'],
                         'conservative_input_bound': row.get('conservative_input_bound'),
                         'input_source': row.get('cost_forecast_source', row.get('input_forecast_source')),
                         'output_source': row.get('output_forecast_source', row.get('source'))})
    calls = [{'label': call['label'], 'model_id': call['model_id'],
              'unit': call.get('billing_unit') or manifest.billing_unit,
              'status': call['status'], 'reserved': call['reserved'],
              'charged': call['charged'], 'billing_mode': call.get('billing_mode', 'metered'),
              'cost_basis': call.get('cost_basis'), 'cash_cost_cny': call.get('cash_cost_cny')}
             for call in result.get('calls', ())]
    trace = {'schema_version': 'automatic-cost-trace-v1', 'selected_nodes': selected,
            'selected_expected_by_unit': expected, 'calls': calls,
            'accounting_basis': result.get('accounting_basis'),
            'reference_costs_cny': result.get('reference_costs_cny'),
            'cash_costs_cny': result.get('cash_costs_cny'),
            'review_protection': (result.get('review') or {}).get('protection')}
    if trace['accounting_basis'] == 'public-reference-valuation':
        decision = (result.get('complexity_gate') or {}).get('local_decision') or {}
        external = decision.get('costCny') if decision.get('backend') == 'jev' else 0
        confirmed = type(external) in (int, float) and math.isfinite(external) and external >= 0
        trace['external_structure_judge'] = {'call_id': decision.get('callId'),
            'cost_cny': external if confirmed else None, 'confirmed': confirmed}
        for field, ledger in (('all_in_known_cash_cost_cny', 'cash_costs_cny'),
                              ('all_in_known_reference_cost_cny', 'reference_costs_cny')):
            amounts = trace[ledger] or {}
            trace[field] = sum(amounts.get(k, 0) for k in ('production', 'evaluation')) + external if confirmed else None
    return trace


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


def build_request(payload, *, mode, production_budget, timeout_ms, automatic_routing=False):
    if not isinstance(payload, dict) or set(payload) - {'task', 'strategy', 'template', 'plan', 'acceptanceCriteria', 'context', 'temperature', 'outputConstraints', 'maxPlanRepairs',
            'planningMode', 'plannerPolicy', 'contextPolicy', 'prefixPolicy', 'materials', 'plannerModelId', 'plannerMaxOutputTokens', 'plannerTimeoutMs',
            'maxDynamicSplits', 'maxConcurrency', 'providerConcurrency', 'providerMinIntervalMs', 'maxTotalOutputTokens', 'verifyDependencies', 'limits',
            'complexityPolicy', 'reviewPolicy', 'authorization', 'unlimitedNodeOutput', 'maxDshToolCalls',
            'decompositionDecision', 'boundedCallOutput', 'reviewReserveMs', 'reviewMaxOutputTokens', 'reviewTimeoutMs'}:
        raise ValueError('invalid RefractAgent request fields')
    if 'boundedCallOutput' in payload and type(payload['boundedCallOutput']) is not bool:
        raise ValueError('boundedCallOutput must be boolean')
    validate_materials(payload.get('materials', []))
    limits = payload.get('limits', {})
    if (not isinstance(limits, dict) or set(limits) - {'relaxBudget', 'relaxContext', 'unlimitedTime'}
            or any(not isinstance(limits[key], bool) for key in limits)):
        raise ValueError('limits may only contain boolean relaxBudget, relaxContext and unlimitedTime')
    relax_budget = limits.get('relaxBudget', False)
    relax_context = limits.get('relaxContext', False)
    if 'unlimitedNodeOutput' in payload and (type(payload['unlimitedNodeOutput']) is not bool or not automatic_routing):
        raise ValueError('unlimitedNodeOutput requires a v4 boolean setting')
    if 'maxDshToolCalls' in payload and (not automatic_routing or
            (payload['maxDshToolCalls'] != 'unlimited' and
             (type(payload['maxDshToolCalls']) is not int or not 1 <= payload['maxDshToolCalls'] <= 100000))):
        raise ValueError('maxDshToolCalls requires a v4 integer in 1..100000 or unlimited')
    strategy = payload.get('strategy', 'auto' if automatic_routing else 'balanced')
    allowed_strategies = {'auto'} if automatic_routing else set(PRESETS)
    if not isinstance(strategy, str) or strategy not in allowed_strategies:
        raise ValueError('v4 strategy must be auto' if automatic_routing else
                         'strategy must be economy, balanced or quality')
    template = payload.get('template', 'auto' if automatic_routing else 'single')
    if automatic_routing and (template != 'auto' or 'plan' in payload):
        raise ValueError('v4 automatic routing requires template auto without an explicit plan')
    budget = number(production_budget, 'production budget', positive=True)
    task = text(payload.get('task'), 'task')
    criteria = payload.get('acceptanceCriteria')
    automatic = template == 'auto' and 'plan' not in payload
    plan = (None if automatic else validate_plan(payload['plan'], required_criteria=criteria).to_dict() if 'plan' in payload
            else plan_template(template, criteria))
    preset = AUTO_PRESET if automatic_routing else PRESETS[strategy]
    request = {**deepcopy(preset), 'task': task,
               'mode': {'preflight': 'preflight', 'demo': 'demo', 'live': 'run'}[mode],
               'costMax': RELAXED_COST_MAX if relax_budget else budget,
               'latencyMaxMs': number(timeout_ms, 'timeout', positive=True),
               'maxConcurrency': 1, 'maxNodeFallbacks': 0}
    if automatic_routing:
        request['reviewReserveMs'] = payload.get('reviewReserveMs', 60000)
        request['reviewMaxOutputTokens'] = payload.get('reviewMaxOutputTokens', 8192)
        if 'reviewTimeoutMs' in payload:
            request['reviewTimeoutMs'] = payload['reviewTimeoutMs']
    elif any(key in payload for key in ('reviewReserveMs','reviewMaxOutputTokens','reviewTimeoutMs')):
        raise ValueError('review limits require automatic routing')
    if limits.get('unlimitedTime', False):
        request['unlimitedTime'] = True
    if plan is not None:
        request['plan'] = plan
    if automatic:
        repairs = payload.get('maxPlanRepairs', 0)
        if type(repairs) is not int or not 0 <= repairs <= 1:
            raise ValueError('maxPlanRepairs must be an integer in 0..1')
        request['maxPlanRepairs'] = repairs
        request['planningMode'] = payload.get('planningMode','compact')
        request['unrestrictedPlanning'] = request['planningMode'] == 'compact'
        if 'plannerPolicy' in payload:
            request['plannerPolicy'] = payload['plannerPolicy']
        request['maxDynamicSplits'] = payload.get('maxDynamicSplits', 0 if automatic_routing
            or payload.get('plannerPolicy') in ('minimal-v1', 'minimal-v2') else 1)
    elif 'maxPlanRepairs' in payload:
        raise ValueError('maxPlanRepairs requires the automatic template')
    if 'plannerPolicy' in payload and not automatic:
        raise ValueError('plannerPolicy requires the automatic template')
    for key in ('contextPolicy', 'prefixPolicy', 'materials'):
        if key in payload:
            request[key] = deepcopy(payload[key])
    request['verifyDependencies'] = payload.get('verifyDependencies',True)
    for key in ('plannerModelId','plannerMaxOutputTokens','plannerTimeoutMs','maxDynamicSplits',
                'maxConcurrency','providerConcurrency','providerMinIntervalMs','maxTotalOutputTokens'):
        if key in payload:
            request[key] = payload[key]
    if 'maxTotalOutputTokens' in request:
        if type(request['maxTotalOutputTokens']) is not int or not 1000 <= request['maxTotalOutputTokens'] <= 1_000_000:
            raise ValueError('maxTotalOutputTokens must be an integer in 1000..1000000')
    if request.get('unrestrictedPlanning'):
        request.pop('plannerMaxOutputTokens', None)
        request.pop('plannerTimeoutMs', None)
    if criteria is not None:
        request['acceptanceCriteria'] = criteria
    del request['name']
    if 'outputConstraints' in payload:
        request['outputConstraints'] = validate_output_constraints(payload['outputConstraints'])
    context = payload.get('context', '')
    context_limit = RELAXED_CONTEXT_BYTES if relax_context else MAX_CONTEXT_BYTES
    if not isinstance(context, str) or len(context.encode()) > context_limit:
        raise ValueError('conversation context exceeds the RefractAgent input limit')
    return strategy, request, context, {'relaxBudget': relax_budget, 'relaxContext': relax_context, **({'unlimitedTime': limits['unlimitedTime']} if 'unlimitedTime' in limits else {})}


def run_agent(payload, *, mode='preflight', runs_dir, production_budget=40,
              evaluation_budget=80, timeout_ms=300000, max_output_tokens=2048,
              manifest_path=None, profile_path=None, execute_paid_run=False,
              client=None, cancel_event=None, provider_config=None, preset=None, progress=None, tool_runtime=None,
              model_profile_provenance=None, route_observation_path=None,
              route_observation_scope='local', dsh_catalog_snapshot=None, final_validator=None):
    if mode not in {'preflight', 'demo', 'live'}:
        raise ValueError('mode must be preflight, demo or live')
    automatic_routing = (isinstance(provider_config, dict)
                         and provider_config.get('schemaVersion') in {'refractagent-providers-v4',
                                                                      'refractagent-providers-v5', 'refractagent-providers-v6'})
    mixed = (automatic_routing and provider_config.get('schemaVersion') == 'refractagent-providers-v5')
    if (mode == 'live') != execute_paid_run:
        raise ValueError('live requires explicit --execute-paid-run; preview/demo forbid paid execution')
    if (production_budget == 'unlimited' or evaluation_budget == 'unlimited') and not (
            automatic_routing and mode in {'preflight', 'live'}):
        raise ValueError('unlimited budgets require v4 preflight or live execution')
    production_choice, evaluation_choice = production_budget, evaluation_budget
    production_budget = UNLIMITED_COST_INTERNAL if production_budget == 'unlimited' else production_budget
    evaluation_budget = UNLIMITED_COST_INTERNAL if evaluation_budget == 'unlimited' else evaluation_budget
    if mixed:
        for label, limits_by_unit in (('production', production_budget), ('evaluation', evaluation_budget)):
            if not isinstance(limits_by_unit, dict) or set(limits_by_unit) != {'AFP', 'CNY'}:
                raise ValueError(f'mixed automatic routing requires AFP and CNY {label} budgets')
            for unit, value in limits_by_unit.items():
                number(value, f'{unit} {label} budget')
    else:
        number(evaluation_budget, 'evaluation budget', positive=True)
    if type(max_output_tokens) is not int or not 1000 <= max_output_tokens <= 128000:
        raise ValueError('output cap must be an integer in 1000..128000')
    strategy, request, context, limits = build_request(
        payload, mode=mode, production_budget=1 if mixed else production_budget, timeout_ms=timeout_ms,
        automatic_routing=automatic_routing)
    if payload.get('boundedCallOutput'):
        request['unrestrictedPlanning'] = False
        # 只在应用入口显式有界时开放较大的规划包络；旧 task API 上限保持原合同。
        request['boundedPlannerLimits'] = True
        planner_cap = payload.get('plannerMaxOutputTokens', 2048)
        if type(planner_cap) is not int or not 256 <= planner_cap <= 128000:
            raise ValueError('explicit planner output cap must be an integer in 256..128000')
        request['plannerMaxOutputTokens'] = min(max_output_tokens, planner_cap)
        if 'plannerTimeoutMs' in payload:
            request['plannerTimeoutMs'] = payload['plannerTimeoutMs']
    if automatic_routing and mode in {'preflight', 'live'}:
        if (tool_runtime is None) != ('maxDshToolCalls' not in payload):
            raise ValueError('REFRACTAGENT_TOOLS_DISABLED: DSH 工具目录与调用上限必须同时提供')
        if tool_runtime is not None and tool_runtime.max_calls != payload['maxDshToolCalls']:
            raise ValueError('REFRACTAGENT_PREVIEW_MISMATCH: DSH 工具调用上限不一致')
    if mixed:
        request['costMax'] = 0
        request['costMaxByUnit'] = dict(production_budget)
    elif automatic_routing and mode in {'preflight', 'live'}:
        request['costMax'] = production_budget
    tools_allowed = tool_runtime is not None
    gate = (complexity_gate(payload, context, policy=payload.get('complexityPolicy', 'auto'),
                            tools_allowed=tools_allowed,
                            decomposition=payload.get('decompositionDecision'))
            if automatic_routing else None)
    review = (review_decision(payload, gate, policy=payload.get('reviewPolicy', 'adaptive'),
                              tools_allowed=tools_allowed)
              if automatic_routing else None)
    if gate is not None and gate['decision'] == 'blocked-tools':
        raise ValueError('REFRACTAGENT_TOOLS_DISABLED: 当前任务未启用 DSH 工具，或宿主未提供可用工具')
    relax_budget, relax_context = limits['relaxBudget'], limits['relaxContext']
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
    configured = compile_configuration(provider_config, strategy=strategy) if provider_config is not None else None
    if configured:
        manifest = configured.manifest
        if automatic_routing and mode in {'preflight', 'live'} and configured.privacy.get('dataMode') == 'live':
            # 真实会话可能含有确定性规则识别不了的业务信息。只有已声明本地或
            # 可信云的路线能参与这次任务的规划、执行与评审；配置目录仍保持原样。
            manifest = replace(manifest, models=tuple(model for model in manifest.models
                if model.deployment in {'local', 'trusted-cloud'}))
            for role in ('planner', 'worker', 'judge'):
                if not any(role in model.roles for model in manifest.models):
                    raise ValueError(f'REFRACTAGENT_TRUSTED_MODEL_REQUIRED: 真实数据缺少本地或可信云 {role} 模型')
        request['qualityMin'] = configured.quality_min
        request['plannerThinking'] = configured.snapshot.get('plannerThinking', 'inherit')
        if automatic_routing and payload.get('complexityPolicy', 'auto') == 'auto':
            dag_mode = configured.objective['dagMode']
            if dag_mode in {'never', 'force'}:
                gate = {**gate, 'decision': 'direct' if dag_mode == 'never' else 'dag',
                        'reasons': [f'objective-dag-{dag_mode}'],
                        'combination': 'objective-dag-mode', 'forced': True}
                review = review_decision(payload, gate,
                    policy=payload.get('reviewPolicy', 'adaptive'), tools_allowed=tools_allowed)
    else:
        manifest_file = Path(manifest_path) if manifest_path else Path(str(resource('agent-plan.json')))
        manifest = load_model_manifest(manifest_file)
        manifest_data = json.loads(manifest_file.read_text())
    if automatic_routing and gate['decision'] == 'direct':
        request['plan'] = plan_template('single', payload.get('acceptanceCriteria'))
    if automatic_routing and mode == 'live':
        if configured.snapshot.get('security', {}).get('dataMode') not in {'synthetic', 'desensitized', 'live'}:
            raise ValueError('REFRACTAGENT_DATA_MODE_UNSUPPORTED: 未声明有效数据模式')
        if manifest.billing_unit not in {'USD', 'CNY', 'AFP', 'MIXED'}:
            raise ValueError('REFRACTAGENT_BILLING_UNIT_UNSUPPORTED: 真实执行计费单位未获支持')
        if (request.get('maxPlanRepairs', 0) != 0 or request.get('maxDynamicSplits', 0) != 0
                or request.get('maxNodeFallbacks', 0) != 0):
            raise ValueError('live canary requires zero repair/split/fallback')
    # 容量编译、规划模型选择与实际派发必须看到同一输出上限。若在编译 DAG 后才
    # 收窄 worker，会把 DSH 目录的模型最大输出（例如 256K）错误当成每个父节点
    # 都会交接的文本量，导致普通多节点任务虚假地失去可用的本地路线。
    unlimited_node_output = automatic_routing and payload.get('unlimitedNodeOutput', False)
    generated_automatic = automatic_routing or (payload.get('template') == 'auto' and 'plan' not in payload)
    if generated_automatic:
        manifest = replace(manifest, models=tuple(
            # 先读取模型真实容量，再应用本次任务的单节点上限。
            (lambda capacity: replace(capacity,
                                      max_output_tokens=(capacity.max_output_tokens if unlimited_node_output
                                                         else min(capacity.max_output_tokens,
                                                                  max_output_tokens))))(execution_capacity_model(m))
            if 'worker' in getattr(m, 'roles', ())
            else replace(m, max_output_tokens=min(m.max_output_tokens, max_output_tokens))
            for m in manifest.models
        ))
    input_cap = (min(RELAXED_INPUT_CAP, max(131072, max(m.context_window for m in manifest.models) - max_output_tokens))
                 if relax_context else 131072)
    if 'plan' in request and (configured or relax_context):
        prepare_configured_plan(request, context, explicit_plan='plan' in payload,
                                output_cap=max_output_tokens, input_cap=input_cap)
    temperature = number(payload.get('temperature', 0), 'temperature', maximum=2)
    if not generated_automatic:
        manifest = replace(manifest, models=tuple(
            execution_capacity_model(m) if 'worker' in getattr(m, 'roles', ())
            else replace(m, max_output_tokens=min(m.max_output_tokens, max_output_tokens))
            for m in manifest.models))
    if automatic_routing and mode == 'live':
        request['adaptiveOutputBudget'] = True
    manifest = replace(manifest, models=tuple(replace(m, request_options={**m.request_options, 'temperature': temperature})
                                             if (m.role == 'candidate' or 'worker' in getattr(m, 'roles', ())) and m.wire_api != 'responses' else m for m in manifest.models))
    if (automatic_routing or payload.get('template') == 'auto') and 'plan' not in payload:
        request['maxConcurrency'] = payload.get('maxConcurrency', 1 if (automatic_routing and mode == 'live')
            or any(m.wire_api == 'dsh-llm' for m in manifest.models) else 4)
    if configured:
        manifest_data = {'schema_version': manifest.schema_version, 'billing_unit': manifest.billing_unit,
                         'models': [asdict(m) for m in manifest.models]}
    profile = (configured_profile(configured, manifest, request.get('plan') or preview_plan(request['task'],
                   required_criteria=request.get('acceptanceCriteria')).to_dict()) if configured else
               json.loads(Path(profile_path).read_text() if profile_path else resource('report-profile.json').read_text()))
    binding = (authorization_binding(payload, provider_config=provider_config,
        catalog_snapshot=dsh_catalog_snapshot, production_budget=production_choice,
        evaluation_budget=evaluation_choice, max_output_tokens=max_output_tokens,
        gate=gate, review=review,
        data_mode=configured.snapshot.get('security', {}).get('dataMode'),
        billing_unit=manifest.billing_unit,
        tool_schemas=tool_runtime.schemas if tools_allowed else None,
        max_tool_calls=tool_runtime.max_calls if tools_allowed else 0) if automatic_routing else None)
    approved_authorization = None
    if automatic_routing and mode == 'live':
        approved_authorization = validate_authorization(payload.get('authorization'), binding)
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
        client = OpenAICompatibleClient(max_retries=0, timeout_seconds=None, environment=environment,
            **({"dsh_bridge": tool_runtime.bridge} if tool_runtime is not None else {}))
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:12]
    directory = Path(runs_dir).expanduser().resolve() / run_id
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    request_path = directory / 'request.json'
    atomic_json(request_path, {'schema_version': 'refractagent-request-v1', 'payload': payload,
        'runtime_request': request,
        'policy_version': AUTO_POLICY_VERSION if automatic_routing else POLICY_VERSION, 'mode': mode,
        'production_budget': production_choice, 'evaluation_budget': evaluation_choice,
        'max_output_tokens': max_output_tokens, 'limits': limits,
        **({'complexity_gate': gate, 'review': review,
            'authorization': approved_authorization} if automatic_routing else {})})
    atomic_json(directory / 'profile.json', profile)
    atomic_json(directory / 'manifest.json', manifest_data)
    if configured:
        atomic_json(directory / 'provider-config.json', configured.snapshot)
    if model_profile_provenance is not None:
        atomic_json(directory / 'model-profile-provenance.json', model_profile_provenance)
    result_path = directory / 'result.json'
    recorder = ProgressRecorder(directory, manifest, progress)
    def checkpoint(value):
        atomic_json(result_path, value)
        recorder.record(value)
    max_model_calls = None
    if gate is not None and not (tools_allowed and tool_runtime.max_calls == 'unlimited'):
        max_model_calls = ((1 + int(review['required'])) if gate['decision'] == 'direct' else 8)
        if tools_allowed:
            max_model_calls += tool_runtime.max_calls
    result = run_task(request, manifest, profile,
        client=client if mode == 'live' else None,
        production_limit=(production_budget if mixed or automatic_routing and mode in {'preflight', 'live'}
                          else RELAXED_COST_MAX if relax_budget else production_budget),
        evaluation_limit=(evaluation_budget if mixed or automatic_routing and mode in {'preflight', 'live'}
                          else RELAXED_COST_MAX if relax_budget else evaluation_budget),
        checkpoint=checkpoint, cancel_event=cancel_event, tool_runtime=tool_runtime,
        conversation_context=context, configured_application=configured is not None, configuration=configured,
        context_limit_bytes=RELAXED_CONTEXT_BYTES if relax_context else MAX_CONTEXT_BYTES, input_cap=input_cap,
        privacy=configured.privacy if configured else None,
        decision_evidence=gate, review_evidence=review, max_model_calls=max_model_calls,
        final_validator=final_validator,
        alternative_direct_plan=(plan_template('single', payload.get('acceptanceCriteria'))
            if automatic_routing and mode == 'live' and gate['decision'] == 'dag'
            and configured.objective['dagMode'] == 'auto' else None))
    if result.get('routing_profile'):
        profile = result['routing_profile']
        atomic_json(directory / 'profile.json', profile)
    if result.get('plan'):
        atomic_json(directory / 'plan.json', result['plan'])
    assignments = result.get('assignments', (result.get('routing') or {}).get('assignments', {}))
    models = {m.model_id: m.api_model for m in manifest.models}
    actions = {m.model_id: action_identity(m) for m in manifest.models}
    if mode == 'demo' and result['final_output']:
        result['final_output'] = ('[SIMULATED] RefractAgent 安装演示，未调用真实模型。\n\n'
            + '策略：' + (AUTO_PRESET if automatic_routing else PRESETS[strategy])['name'] + '\n'
            + '模型分配：' + json.dumps({nid: models[mid] for nid,mid in assignments.items()}, ensure_ascii=False) + '\n'
            + '任务：' + request['task'] + '\n\n'
            + '安装、选路和结果保存已完成；启用真实执行后才会生成该任务的答案与独立评审。')
        atomic_json(result_path, result)
    if result['final_output']:
        (directory / 'answer.md').write_text(result['final_output'])
    calls = result['calls']
    observation_evidence = None
    if mode == 'live' and route_observation_path is not None and model_profile_provenance is not None:
        bindings = {row['compiled_model_id']: {
            'provider': route.split('/', 1)[0], 'model': route.split('/', 1)[1],
            'effective_model': row['effective_model'],
            'reasoning_effort': next((str(m.request_options.get('reasoning_effort', row.get('reasoning_effort', 'default')))
                for m in manifest.models if m.model_id == row['compiled_model_id']), row.get('reasoning_effort', 'default')),
        } for route, row in model_profile_provenance.items()
            if isinstance(row, dict) and isinstance(row.get('compiled_model_id'), str)
            and isinstance(row.get('effective_model'), str)
            and isinstance(row.get('reasoning_effort', 'default'), str)
            and '/' in route}
        store = RouteObservationStore(route_observation_path, scope=route_observation_scope)
        recorded = store.record_run(run_id, calls, bindings)
        observation_evidence = {'recorded': recorded, 'path': str(Path(route_observation_path).resolve()),
                                'policy': 'latest-50-successful-p90-v1'}
        if automatic_routing:
            value = route_value_observation(result.get('route_comparison'), result['plan_origin'],
                calls, manifest.billing_unit, result['status'], result['evaluation'],
                result.get('tool_validation'))
            observation_evidence['value_recorded'] = store.record_route_value(run_id, value)
            observation_evidence['value'] = value
    if mixed:
        totals = {'production': None, 'evaluation': None, 'unconfirmed': None,
            'by_unit': {unit: {
                'production': sum(c['charged'] for c in calls if c['billing_unit'] == unit
                    and c['category'] == 'production' and c['status'] == 'billed'),
                'evaluation': sum(c['charged'] for c in calls if c['billing_unit'] == unit
                    and c['category'] == 'evaluation' and c['status'] == 'billed'),
                'unconfirmed': sum(c['charged'] for c in calls if c['billing_unit'] == unit
                    and c['status'] in {'reserved', 'unknown-usage'}),
            } for unit in ('AFP', 'CNY')}}
        local_decision = gate.get('local_decision') if isinstance(gate, dict) else None
        if isinstance(local_decision, dict) and local_decision.get('backend') == 'jev':
            judge_cost = local_decision.get('costCny')
            confirmed = (type(judge_cost) in (int, float) and math.isfinite(judge_cost)
                         and judge_cost >= 0)
            totals['out_of_band_judge'] = {'unit': 'CNY',
                'cost': judge_cost if confirmed else None,
                'call_id': local_decision.get('callId'),
                'scope': 'decomposition-decision'}
            rows = totals['by_unit']
            totals['all_in_known_by_unit'] = {
                'AFP': rows['AFP']['production'] + rows['AFP']['evaluation'],
                'CNY': (rows['CNY']['production'] + rows['CNY']['evaluation'] + judge_cost
                        if confirmed else None)}
    else:
        totals = {kind: sum(c['charged'] for c in calls if c['category'] == kind and c['status'] == 'billed')
                  for kind in ('production', 'evaluation')}
        totals['unconfirmed'] = sum(c['charged'] for c in calls if c['status'] in {'reserved', 'unknown-usage'})
    cost_breakdown = ({phase: {unit: sum(c['charged'] for c in calls
        if c['billing_unit'] == unit and c['status'] == 'billed' and (
            c['category'] == 'evaluation' if phase == 'evaluation' else
            c['category'] == 'production' and (
                c['label'] in {'planner', 'planner-repair'} if phase == 'planning' else
                c['label'].startswith('dynamic-planner-') if phase == 'dynamic_planning' else
                c['label'] not in {'planner', 'planner-repair'} and not c['label'].startswith('dynamic-planner-'))))
        for unit in ('AFP', 'CNY')} for phase in ('planning', 'dynamic_planning', 'execution', 'evaluation')}
        if mixed else None)
    output = {'schema_version': 'refractagent-result-v1', 'run_id': run_id, 'mode': mode,
        'strategy': strategy,
        'strategy_name': (AUTO_PRESET if automatic_routing else PRESETS[strategy])['name'],
        'policy_version': AUTO_POLICY_VERSION if automatic_routing else POLICY_VERSION,
        'limits': limits,
        'status': result['status'], 'answer': result['final_output'], 'issues': result['issues'],
        'models': {nid: models[mid] for nid, mid in assignments.items()},
        'model_routes': {nid: actions[mid] for nid, mid in assignments.items()},
        'evaluation_model': actions[manifest.judge.model_id],
        'configuration_source': 'user' if configured else 'manifest' if manifest_path else preset or 'bundled-demo',
        'quality': result['evaluation'], 'costs': totals, 'billing_unit': manifest.billing_unit,
        'generation_status': result['generation_status'], 'format_validation': result['format_validation'],
        'tool_validation': result.get('tool_validation'),
        'simulated': mode == 'demo', 'wall_time_ms': result['wall_time_ms'],
        'plan_origin': result['plan_origin'], 'plan': result['plan'], 'dag': dag_snapshot(result, manifest),
        'plan_admission': result.get('plan_admission'),
        'route_comparison': result.get('route_comparison'),
        'planner': result.get('planner_selection'), 'plan_ready_ms': result.get('plan_ready_ms'),
        'model_call_limit': result.get('model_call_limit'),
        'content_validation': result.get('content_validation'),
        'dynamic_decomposition': result.get('dynamic_decomposition'),
        'cost_breakdown': cost_breakdown if mixed else {
            'planning': sum(c['charged'] for c in calls if c['category']=='production' and c['label'] in {'planner','planner-repair'}),
            'dynamic_planning': sum(c['charged'] for c in calls if c['category']=='production' and c['label'].startswith('dynamic-planner-')),
            'execution': sum(c['charged'] for c in calls if c['category']=='production' and c['label'] not in {'planner','planner-repair'} and not c['label'].startswith('dynamic-planner-')),
            'evaluation': sum(c['charged'] for c in calls if c['category']=='evaluation'),
        },
        'result_path': str(result_path), 'run_dir': str(directory),
        'usage': {'input_tokens': sum(c.get('input_tokens', 0)-c.get('cached_input_tokens', 0) for c in calls if c['status'] == 'billed'),
                  'output_tokens': sum(c.get('output_tokens', 0) for c in calls if c['status'] == 'billed'),
                  'cache_read_tokens': sum(c.get('cached_input_tokens', 0) for c in calls if c['status'] == 'billed'),
                  'reasoning_tokens': sum(c.get('reasoning_tokens', 0) for c in calls if c['status'] == 'billed')},
        'profile_scope': profile['scope'], 'limitations': result['limitations'],
        'model_profile_provenance': model_profile_provenance,
        **({'route_observations': observation_evidence} if observation_evidence is not None else {}),
        'artifact_hashes': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in sorted(directory.iterdir()) if p.is_file()}}
    if automatic_routing:
        output['complexity_gate'] = gate
        # 宿主先读取核心已编译的策略，再决定是否派发拆分 Judge。
        # 强制策略与简单任务均已有零调用结论，不能付费后再覆盖它。
        skip_judge = gate.get('forced') or 'trivial-workload' in gate.get('reasons', [])
        output['decomposition_judge'] = {
            'required': not bool(skip_judge),
            'reason': ('explicit-routing-policy' if gate.get('forced') else
                       'trivial-workload' if skip_judge else 'structure-decision-needed'),
            'policy_version': gate['policy_version'],
        }
        output['review'] = result.get('review', review)
        output['cost_trace'] = automatic_cost_trace(result, manifest)
        configured_candidates = configured.manifest.candidates if configured else manifest.candidates
        output['candidate_models'] = {m.model_id: {
            **action_identity(m), 'deployment': m.deployment,
            'billing_mode': m.billing_mode, 'billing_unit': m.billing_unit,
        } for m in configured_candidates}
        # live 在进入节点准入前就排除未获信任的云端；解释层也必须列出它们。
        removed = {m.model_id for m in configured_candidates} - {m.model_id for m in manifest.candidates}
        if removed and isinstance(output['plan_admission'], dict):
            output['plan_admission'] = deepcopy(output['plan_admission'])
            for row in output['plan_admission'].values():
                row.setdefault('model_reasons', {}).update({mid: 'data-domain-not-authorized'
                    for mid in sorted(removed)})
            if isinstance(output['route_comparison'], dict):
                output['route_comparison'] = deepcopy(output['route_comparison'])
                for nodes in output['route_comparison'].get('model_admission', {}).values():
                    for reasons in nodes.values():
                        reasons.update({mid: 'data-domain-not-authorized' for mid in sorted(removed)})
        output['model_selection_rule'] = (result.get('routing') or {}).get('cost_preference',
            'configured-routing-objective')
        if mode == 'preflight':
            prediction = (result.get('routing') or {}).get('prediction') or {}
            production_estimate = prediction.get('costs_by_unit', {'AFP': 0, 'CNY': 0}) if mixed else prediction.get('cost', 0)
            if not mixed and not isinstance(production_estimate, (int, float)):
                production_estimate = 0
            output['live_authorization_preview'] = create_authorization_preview(
                binding, billing_unit=manifest.billing_unit,
                production_estimate=production_estimate,
                evaluation_estimate=({unit: 0 if not review['required'] else evaluation_budget[unit]
                                      for unit in ('AFP', 'CNY')} if mixed else
                    0 if not review['required'] else (
                    None if evaluation_choice == 'unlimited' else evaluation_budget)),
                ready=result.get('status') == 'preview')
    if result.get('compact_planning', {}).get('policy_version'):
        output['planning_policy'] = result['compact_planning']['policy_version']
        output['planning_decision'] = result['compact_planning'].get('decision')
    output['prefix_policy'] = result.get('prefix_policy', 'legacy')
    if 'context_selection' in result:
        output['context_selection'] = result['context_selection']
    if automatic_routing:
        from .automatic_trace import project
        output['automatic_trace'] = project(output, result)
    atomic_json(directory / 'summary.json', output)
    return output
