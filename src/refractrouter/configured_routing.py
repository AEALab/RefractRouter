"""User-declared, action-specific forecasts resolved against each DAG node."""
from .node_routing import NodeProfile, number, validate_profiles
from .routing_actions import action_binding
from .task_plan import validate_plan


def prediction(raw, output_cap):
    if not isinstance(raw, dict) or set(raw) - {'quality', 'latencyMs', 'outputTokens'}:
        raise ValueError('invalid routing prediction fields')
    output = raw.get('outputTokens')
    if output is not None and (type(output) is not int or not 1 <= output <= output_cap):
        raise ValueError('routing outputTokens must fit model maxOutputTokens')
    return {'quality': number(raw.get('quality'), 'configured quality', maximum=100),
            'latency_ms': number(raw.get('latencyMs'), 'configured latency', positive=True),
            'output_tokens': output}


def compile_routing(raw, output_cap):
    if not isinstance(raw, dict) or set(raw) - {'quality', 'latencyMs', 'outputTokens', 'profiles'}:
        raise ValueError('invalid routing prediction fields')
    default = prediction({k: v for k, v in raw.items() if k != 'profiles'}, output_cap)
    overrides = raw.get('profiles', [])
    if not isinstance(overrides, list) or len(overrides) > 128:
        raise ValueError('routing profiles must be an array of at most 128 strata')
    profiles = []
    for item in overrides:
        selectors = {'nodeType', 'difficulty', 'risk', 'inputMinTokens', 'inputMaxTokens'}
        if not isinstance(item, dict) or set(item) - selectors - {'quality', 'latencyMs', 'outputTokens'}:
            raise ValueError('invalid routing profile fields')
        values = prediction({k: v for k, v in item.items() if k not in selectors}, output_cap)
        selector = NodeProfile('configured', item.get('nodeType'), values['quality'], 0,
            values['latency_ms'], 0, difficulty=item.get('difficulty'), risk=item.get('risk'),
            input_min_tokens=item.get('inputMinTokens', 256), input_max_tokens=item.get('inputMaxTokens', 131073))
        profiles.append((selector, values))
    validate_profiles(tuple(p for p, _ in profiles))
    return {**default, 'profiles': profiles}


def configured_profile(configuration, manifest, plan, *, input_forecasts=None):
    plan = validate_plan(plan)
    stratified = bool(plan.contracts)
    rows, basis = {}, {}
    for model in manifest.candidates:
        default = configuration.predictions[model.model_id]
        if default['profiles'] and not stratified:
            raise ValueError('routing profiles require a v2 DAG with node capability contracts')
        # Clipping an effort's expected token use would reuse its quality/latency
        # forecast for a different execution envelope. Reject instead of guessing.
        for forecast in [default, *(v for _, v in default['profiles'])]:
            if forecast['output_tokens'] is not None and forecast['output_tokens'] > model.max_output_tokens:
                raise ValueError(f'{model.model_id}: routing outputTokens exceeds effective maxOutputTokens; raise the application output cap or update predictions')
        for node in plan.nodes:
            matches = [(index, value) for index, (selector, value) in enumerate(default['profiles']) if selector.matches(node, plan)]
            index, forecast = matches[0] if matches else (None, default)
            capability = plan.contracts.get(node.node_id, {}).get('capability', {})
            input_cap = capability.get('input_budget_tokens', 131072)
            input_forecast = input_cap if input_forecasts is None else input_forecasts[node.node_id]
            number(input_forecast, 'forecast input', maximum=input_cap, positive=True)
            output = forecast['output_tokens'] if forecast['output_tokens'] is not None else model.max_output_tokens
            selector = ({'difficulty': capability['difficulty'], 'risk': capability['risk'],
                'input_min_tokens': input_cap, 'input_max_tokens': input_cap + 1} if stratified else {})
            row = {'model_id': model.model_id, 'node_type': node.node_type, 'samples': 0,
                'quality': forecast['quality'], 'latency_ms': forecast['latency_ms'],
                'cost': input_forecast / 1000 * model.input_cost_per_1k + output / 1000 * model.output_cost_per_1k,
                **selector}
            key = (model.model_id, node.node_type, *selector.values())
            rows[key] = row
            basis.setdefault(node.node_id, {})[model.model_id] = {'input_tokens': input_forecast,
                'output_tokens': output, 'source': 'default' if index is None else f'profiles[{index}]'}
            if input_forecasts is not None:
                basis[node.node_id][model.model_id].update(input_capacity=input_cap,
                    input_forecast_source='serialized-input-and-planned-parent-output')
    return {'schema_version': 'node-routing-profile-v2' if stratified else 'node-routing-profile-v1',
        'kind': 'configured', 'billing_unit': manifest.billing_unit,
        'scope': '用户配置的模型与推理档位路由预测；不是实测质量、时延或 SLA。',
        'provenance': '本次 provider-config.json；无模型探测、无观测样本。',
        'candidates': list(rows.values()), 'forecast_basis': basis,
        'model_bindings': {m.model_id: m.api_model for m in manifest.candidates},
        'action_bindings': {m.model_id: action_binding(m) for m in manifest.candidates}}
