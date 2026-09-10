"""规划前公开执行约束，规划后核对容量；不伪造能力观测或修改风险标签。"""
from copy import deepcopy
from dataclasses import asdict
import json

from .responses_api import output_token_limit
from .task_execution import node_messages
from .task_plan import validate_plan, NODE_TYPES


def execution_support(manifest, profiles, *, configuration=None):
    support = {
        'schema_version': 'planning-support-v1',
        'allowed_node_types': sorted(NODE_TYPES),
        'handoff_example': {'parent_node_id': {'fields': ['result', 'evidence'],
            'reason': '当前节点必须消费该父节点的结果和依据。'}},
        'models': [{'id': m.model_id, 'context_window': m.context_window,
                    'max_output_tokens': output_token_limit(m)} for m in manifest.candidates],
        'profile_kind': 'configured' if configuration else 'empirical',
        'capacity_policy': 'compile-generated-input-estimate' if configuration else 'preserve-declared-contract',
        'instructions': (
            '先根据真实职责判断节点类型、难度和风险，不能为了命中画像而修改标签。'
            '模型能力画像和容量是执行限制；缺少观测不等于模型没有能力，也不能虚构画像。'
            '输出需求不能超过候选模型的输出上限。少用不必要的节点、字段和重复材料。'
            '简单任务直接一个节点；独立且分别要求交付的分析可拆分后汇总。'
            '每个节点只做必要工作，最终节点完整回答用户所有要求。'
            '用户配置模式由运行时根据完整请求和父节点输出容量计算输入预算；'
            '实测画像模式保留声明预算，必须落在已观测区间，无法覆盖时如实保留要求。'),
    }
    if configuration:
        support['forecasts'] = {mid: {
            'quality': p['quality'], 'latency_ms': p['latency_ms'],
            'profiles': [{'selector': asdict(selector), 'forecast': values}
                         for selector, values in p['profiles']],
        } for mid, p in configuration.predictions.items()}
        support['evidence_note'] = '用户声明的预测，零观测；不表示质量已经实测通过。'
    else:
        support['observations'] = [asdict(p) for p in profiles]
        support['evidence_note'] = '仅在所列类型、难度、风险及输入区间内有记录；不得扩大适用范围。'
    return support


def generate_plan(budget, model, messages, result, *, required_criteria, max_repairs,
                  cost_limit, remaining, persist):
    """只修正已结算规划的结构错误一次；不修复节点输出或改变历史研究协议。"""
    transcript = deepcopy(messages)
    result['planning_attempts'] = []
    for attempt in range(max_repairs + 1):
        label = 'planner' if attempt == 0 else 'planner-repair'
        reply = budget.complete(model, transcript, label=label, json_mode=True,
            timeout_seconds=remaining(), category_limit=cost_limit)
        record = {'attempt': attempt + 1, 'label': label, 'output': reply.content, 'error': None}
        result['planning_attempts'].append(record)
        if attempt == 0:
            result['planner_output'] = reply.content
        try:
            plan = validate_plan(json.loads(reply.content), required_criteria=required_criteria, require_v2=True)
        except ValueError as exc:
            record['error'] = str(exc)[:500]
            persist()
            if attempt == max_repairs:
                raise
            transcript.extend([
                {'role':'assistant', 'content':reply.content},
                {'role':'user', 'content':json.dumps({
                    'validation_error':record['error'], 'allowed_node_types':sorted(NODE_TYPES),
                    'handoff_example':{'parent_node_id':{'fields':['result'],'reason':'依赖原因'}},
                    'instructions':'检查整份计划并修正所有结构错误，返回完整 JSON。inputs 的每个父节点值必须是含 fields 数组与 reason 字符串的对象，不能直接给数组。保留原始任务与验收要求；不得降低风险或难度来命中画像。只有这一次修正机会。'}, ensure_ascii=False)},
            ])
        else:
            persist()
            return plan


def input_estimates(plan, task, candidates, *, output_constraints=None):
    """使用完整序列化输入；父输出按有效输出上限预留，运行时仍检查实际字节数。"""
    output_cap = max(output_token_limit(m) for m in candidates.values())
    rows = {}
    for node in plan.nodes:
        contract = plan.contracts.get(node.node_id)
        if not contract:
            continue
        upstream = {p: {field: '' for field in info['fields']}
                    for p, info in contract['inputs'].items()}
        messages = node_messages(task, node, contract, upstream,
            output_constraints=output_constraints if node.node_id == plan.final_node_id else None,
            check_input_budget=False)
        base = len(json.dumps(messages, ensure_ascii=False).encode()) + 256
        # 与应用模板使用相同的保守预留系数。不是供应商分词器保证；实发前会再检查。
        rows[node.node_id] = {'base_input_bound': base,
            'upstream_allowance': len(node.parents) * output_cap * 8,
            'estimated_input_bound': base + len(node.parents) * output_cap * 8 + 32,
            'forecast_input_tokens': base + sum(plan.contracts[p]['capability']['expected_output_tokens'] * 8
                                               for p in node.parents) + 32}
    return rows


def compile_generated_capacity(plan, task, candidates, *, output_constraints=None):
    """只用于应用自动生成的计划；不改显式合同、实测画像或节点的语义属性。"""
    raw = deepcopy(plan.to_dict())
    estimates = input_estimates(plan, task, candidates, output_constraints=output_constraints)
    for node in raw['nodes']:
        bound = max(256, estimates[node['node_id']]['estimated_input_bound'])
        if bound > 131072:
            raise ValueError(f"automatic-plan-input-capacity-exceeded: {node['node_id']}")
        node['contract']['capability']['input_budget_tokens'] = bound
    return validate_plan(raw, required_criteria=plan.acceptance_criteria), estimates


def admission_diagnostics(plan, task, candidates, profiles, quality_min, *, output_constraints=None):
    """整个图在首个节点派发前检查；不给不可执行的分支先花钱。"""
    estimates = input_estimates(plan, task, candidates, output_constraints=output_constraints)
    result = {}
    for node in plan.nodes:
        capability = plan.contracts.get(node.node_id, {}).get('capability')
        matches = [p for p in profiles if p.matches(node, plan) and p.quality >= quality_min]
        available = []
        for p in matches:
            m = candidates[p.model_id]
            if capability and (capability['input_budget_tokens'] + output_token_limit(m) > m.context_window
                    or capability['expected_output_tokens'] > output_token_limit(m)
                    or estimates[node.node_id]['base_input_bound'] > capability['input_budget_tokens']):
                continue
            available.append(p.model_id)
        result[node.node_id] = {'eligible_models': available,
            'reason': None if available else 'missing-quality-profile' if not matches else 'input-or-output-capacity',
            'input_estimate': estimates.get(node.node_id)}
    return result
