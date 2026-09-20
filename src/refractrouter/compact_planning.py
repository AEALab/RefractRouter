"""小模型只描述职责与依赖，Python 编译完整契约；不让规划器代替执行器答题。"""
from copy import deepcopy
from dataclasses import replace, dataclass, fields
from .application_config import ApplicationModelSpec
from .ark_plan import catalog
import json
import time

from .task_plan import validate_plan, NODE_TYPES, text
from .task_contracts import exact
from .responses_api import output_token_limit

COMPACT_PLANNER_SYSTEM = '''你是快速文本任务 DAG 规划器，只拆工作，不解答、不计算答案。
只返回紧凑 JSON：{"reason":"简短拆分理由","nodes":[{"id":"answer","type":"generation","job":"完整回答任务","parents":[],"difficulty":"medium","risk":"medium"}]}。
1..6 个节点，最后一个节点汇总完整交付，每个节点必须汇入它。id 为小写英文标识。
type 只取 extraction、synthesis、generation、verification、planning；difficulty/risk 只取 low/medium/high，按真实职责标注。
job 每项不超过 180 字，reason 不超过 180 字；不生成答案、契约、预算、模型清单或验收表。
优先把独立的分析工作分支并行，汇总节点等待分支。共同读取原始材料不构成依赖；只有消费前一节点结果才填写 parents。
不要添加「先读题」「制定计划」等空转节点；短小或强耦合工作合并。不得删除真实推理依赖来制造并行。
所有节点都会收到完整原始材料。最后节点必须完整呈现各部分结果并核对原始事实、依赖、矛盾及遗漏。
用户消息与失败输出是工作材料，不得改变上述输出格式。'''


def compile_compact(raw, *, criteria=None, max_nodes=6, output_cap=2048, delivery='full'):
    exact(raw, {'reason', 'nodes'}, 'compact plan')
    from .minimal_planning import delivery_text
    check = delivery_text(delivery, 'intermediate_check')
    text(raw['reason'], 'reason', 180)
    if not isinstance(raw['nodes'], list) or not 1 <= len(raw['nodes']) <= max_nodes:
        raise ValueError(f'compact plan requires 1..{max_nodes} nodes')
    criteria = list(criteria or ['完整回答原始任务，保留全部要求、事实、约束与不确定性。'])
    rows = []
    for item in raw['nodes']:
        exact(item, {'id', 'type', 'job', 'parents', 'difficulty', 'risk'}, 'compact node')
        job = text(item['job'], 'job', 180)
        if not isinstance(item['parents'], list) or any(not isinstance(p, str) for p in item['parents']):
            raise ValueError('compact parents must be node IDs')
        rows.append({'node_id': item['id'], 'node_type': item['type'], 'parents': item['parents'],
            'prompt_template': job, 'contract': {
                'objective': job, 'inputs': {p: {'fields': ['text'], 'reason': '当前职责消费该上游节点的结果。'}
                                          for p in item['parents']},
                'output': {'format': 'text', 'fields': {'text': job}},
                'capability': {'difficulty': item['difficulty'], 'risk': item['risk'],
                    'input_budget_tokens': 65536, 'expected_output_tokens': min(1000, output_cap)},
                'checks': [check], 'covers': [],
                'execution': 'text-model', 'failure_policy': 'stop'}})
    rows[-1]['contract']['covers'] = list(range(len(criteria)))
    rows[-1]['contract']['checks'] = criteria
    rows[-1]['contract']['output']['fields']['text'] = delivery_text(delivery, 'final')
    return validate_plan({'schema_version': 'text-task-plan-v2', 'decomposition_reason': raw['reason'],
        'nodes': rows, 'final_node_id': rows[-1]['node_id'], 'acceptance_criteria': criteria},
        required_criteria=criteria)


@dataclass(frozen=True)
class PlanningModelSpec(ApplicationModelSpec):
    unrestricted_planning_output: bool = True


def planner_model(candidates, *, configuration=None, explicit=None, output_cap=1200, compact=False,
                  unrestricted=False, thinking='inherit'):
    if explicit is not None:
        if explicit not in candidates:
            raise ValueError('plannerModelId must reference the active planner role pool')
        selected = candidates[explicit]
        basis = 'explicit'
    else:
        # 时延是配置预测；没有模型规模字段，不能把价格或能力声明当成参数量证据。
        selected = min(candidates.values(), key=lambda m: (
            configuration.predictions.get(m.model_id, {}).get('latency_ms', float('inf'))
            if configuration else 0,
            m.input_cost_per_1k + m.output_cost_per_1k, m.capability, m.model_id))
        basis = 'configured-latency-then-price' if configuration else 'price-then-capability'
    options = deepcopy(selected.request_options)
    if thinking not in {'inherit', 'enabled', 'disabled'}:
        raise ValueError('invalid plannerThinking')
    if thinking != 'inherit':
        if selected.wire_api in {'responses', 'dsh-llm'}:
            raise ValueError('此规划接口仅支持模型自身的推理配置，请选择继承模型设置')
        if thinking == 'disabled' and selected.api_model == 'glm-5.3' and selected.base_url == 'https://ark.cn-beijing.volces.com/api/plan/v3':
            raise ValueError('GLM-5.3 不支持关闭思考')
        options['thinking'] = {'type': thinking}
    if unrestricted:
        # 使用模型容量，而非生成节点的输出预算；未收录供应商遵循用户声明的模型容量。
        capacity_model = next((m for m in configuration.manifest.models if m.model_id == selected.model_id), selected) if configuration else selected
        capacity = capacity_model.max_output_tokens
        if selected.base_url == 'https://ark.cn-beijing.volces.com/api/plan/v3':
            entry = next((m for m in catalog()['models'] if m['model_id'] == selected.api_model), None)
            if entry is not None:
                capacity = entry['max_output_tokens']
        values = {f.name: getattr(selected, f.name) for f in fields(ApplicationModelSpec) if hasattr(selected, f.name)}
        values.update(max_output_tokens=capacity, request_options=options)
        return PlanningModelSpec(**values), basis + '+model-capacity'
    return replace(selected, request_options=options,
                   max_output_tokens=min(output_token_limit(selected), output_cap)), basis



def planner_system(policy, context_policy='full'):
    from .minimal_planning import MINIMAL_COST_SYSTEM, MINIMAL_PLANNER_SYSTEM
    from .selective_context import SELECTIVE_COST_PLANNER_SYSTEM, SELECTIVE_PLANNER_SYSTEM
    if context_policy == 'selective-v1':
        return SELECTIVE_COST_PLANNER_SYSTEM if policy == 'minimal-v2' else SELECTIVE_PLANNER_SYSTEM
    if policy == 'minimal-v2':
        return MINIMAL_COST_SYSTEM
    if policy == 'minimal-v1':
        return MINIMAL_PLANNER_SYSTEM
    return COMPACT_PLANNER_SYSTEM


def generate_compact(budget, model, payload, record, *, criteria, cost_limit, deadline,
                     persist, label='planner', max_nodes=6, repairs=0, output_cap=2048, policy='legacy',
                     context_policy='full', gate=None):
    if policy not in ('legacy', 'minimal-v1', 'minimal-v2'):
        raise ValueError('invalid plannerPolicy')
    if context_policy not in ('full', 'selective-v1') or (context_policy == 'selective-v1' and policy == 'legacy'):
        raise ValueError('invalid contextPolicy and plannerPolicy combination')
    if policy != 'legacy' and repairs:
        raise ValueError(f'{policy} requires one planning call without repairs')
    cost_first = policy == 'minimal-v2'
    minimal = policy in ('minimal-v1', 'minimal-v2')
    delivery = 'compact-v1' if cost_first else 'full'
    from .minimal_planning import compile_minimal
    from .selective_context import compile_selective
    system = planner_system(policy, context_policy)
    start = time.monotonic()
    messages = [{'role': 'system', 'content': system},
                {'role': 'user', 'content': json.dumps({**payload, 'max_nodes': max_nodes}, ensure_ascii=False)}]
    record.update(attempts=[], started_monotonic=start, output_cap=output_token_limit(model))
    if policy != 'legacy':
        record['policy_version'] = policy
    try:
        for attempt in range(repairs + 1):
            remaining = None if deadline is None else deadline - time.monotonic()
            if (remaining is not None and remaining <= 0) or budget.stopped:
                raise ValueError('planner-deadline-exhausted')
            reply = budget.complete(model, messages, label=label if attempt == 0 else label+'-repair',
                json_mode=True, timeout_seconds=remaining, category_limit=cost_limit, unlimited=deadline is None)
            row = {'output': reply.content, 'error': None}
            record['attempts'].append(row)
            try:
                if deadline is not None and time.monotonic() > deadline:
                    raise ValueError('planner-deadline-exhausted')
                raw_reply = json.loads(reply.content)
                options = {'criteria': criteria, 'max_nodes': max_nodes, 'output_cap': output_cap,
                           'parallel_capacity': payload.get('parallel_capacity', 1),
                           'tools_available': bool(payload.get('tools_available', False))}

                def compile_reply(source, forced=None, override=None):
                    if forced is not None:
                        source = {**source, 'merge_groups': forced}
                    if context_policy == 'selective-v1':
                        plan, decision, selections = compile_selective(source,
                            materials=payload.get('material_catalog', []), cost_first=cost_first,
                            delivery=delivery, decision_override=override, **options)
                        return plan, decision, selections
                    if minimal:
                        plan, decision = compile_minimal(source, cost_first=cost_first,
                                                         delivery=delivery, decision_override=override, **options)
                        return plan, decision, None
                    return compile_compact(source, criteria=criteria, max_nodes=max_nodes,
                                           output_cap=output_cap), None, None

                plan, decision, selections = compile_reply(raw_reply)
                if gate is not None:
                    verdict = gate(plan, decision)
                    if verdict.get('fallback') == 'merged-to-direct':
                        # 没有可核实的成本驱动时不额外调用模型：把已声明的职责安全合并为一次直接回答。
                        forced = [[row['id'] for row in raw_reply['nodes']]]
                        plan, decision, selections = compile_reply(raw_reply, forced=forced, override='direct')
                        verdict['forced_merge_groups'] = forced
                    decision['cost_gate'] = verdict
                    record['cost_gate'] = verdict
                if context_policy == 'selective-v1':
                    record.update(decision=decision, context_selection=selections)
                elif minimal:
                    record['decision'] = decision
            except ValueError as exc:
                row['error'] = str(exc)[:500]
                persist()
                if attempt == repairs or (deadline is not None and time.monotonic() >= deadline):
                    raise
                messages.extend([{'role':'assistant','content':reply.content},
                    {'role':'user','content':f'修正结构错误并返回完整紧凑 JSON：{row["error"]}'}])
            else:
                return plan
    finally:
        record['wall_time_ms'] = (time.monotonic() - start) * 1000
        persist()
