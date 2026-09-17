"""按显式材料和字段契约交接；最终节点及评审始终获得全文。"""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import re

from .minimal_planning import (COST_PLANNER_ADDENDUM, MINIMAL_PLANNER_SYSTEM, compile_minimal,
                               delivery_text)
from .task_contracts import exact
from .task_inputs import prepare_inputs
from .task_materials import select_materials
from .task_plan import validate_plan

CONTEXT_POLICY = 'selective-v1'
HANDOFF_FIELDS = {
    'facts': '仅列当前职责所需的事实，保留限定条件，避免复述完整报告。',
    'evidence': '可核对的原文摘录，格式为 [source:来源ID]「逐字原文」。任务/对话中的原文用 task；不得伪造来源。',
    'conclusion': '当前部分的结论与依据，不重复其他部分的完整报告。',
    'uncertainty': '适用限制、例外、缺失信息及不确定性；没有时明确说明。',
}
SELECTIVE_PLANNER_SYSTEM = MINIMAL_PLANNER_SYSTEM.replace(
    '所有节点收到完整原始材料。', '任务说明、对话与全局材料始终提供；局部材料按声明选择，最后节点获得全文。') + '''
额外返回 context 对象，以每个原始节点 ID 为键：{"sources":["材料ID"],"fields":["facts","evidence","conclusion","uncertainty"],"uses":{"父节点ID":["conclusion","evidence","uncertainty"]}}。
sources 只取 material_catalog 的 ID；保留所需局部材料及例外，无法确定时选全部材料。无结构化材料时 sources 为 []，仍获得完整任务。
中间节点 fields 从 facts/evidence/conclusion/uncertainty 选择，必须有 evidence、uncertainty，以及 facts 或 conclusion。最终节点 fields 为 ["text"]。
uses 恰好覆盖 parents，选择父节点已声明的字段，并始终携带 evidence、uncertainty；最终节点读取所有父字段。合并后 sources 和职责字段取并集。不要复制材料原文到规划输出。'''
SELECTIVE_COST_PLANNER_SYSTEM = SELECTIVE_PLANNER_SYSTEM + COST_PLANNER_ADDENDUM


def compile_selective(raw, *, materials, cost_first=False, delivery='full', **kwargs):
    if not isinstance(raw, dict) or 'context' not in raw:
        raise ValueError('selective-v1 requires context declarations')
    clean = {k: v for k, v in raw.items() if k != 'context'}
    plan, decision = compile_minimal(clean, cost_first=cost_first, delivery=delivery, **kwargs)
    specs = raw['context']
    original = {n['id']: n for n in raw['nodes']}
    exact(specs, set(original), 'node context declarations')
    original_final = raw['nodes'][-1]['id']
    for nid, spec in specs.items():
        exact(spec, {'sources', 'fields', 'uses'}, 'node context')
        select_materials(materials, spec['sources'])
        fields = spec['fields']
        if not isinstance(fields, list) or not fields or any(not isinstance(f, str) for f in fields) or len(set(fields)) != len(fields):
            raise ValueError('invalid handoff fields')
        if nid == original_final:
            if fields != ['text']:
                raise ValueError('final node must deliver text')
        elif not set(fields) <= set(HANDOFF_FIELDS) or not {'evidence', 'uncertainty'} < set(fields):
            raise ValueError('intermediate fields require evidence, uncertainty and facts or conclusion')
        exact(spec['uses'], set(original[nid]['parents']), 'parent field selections')
    for nid, spec in specs.items():
        for parent, fields in spec['uses'].items():
            if (not isinstance(fields, list) or not fields or any(not isinstance(f, str) for f in fields)
                    or len(set(fields)) != len(fields) or not set(fields) <= set(specs[parent]['fields'])
                    or not {'evidence', 'uncertainty'} <= set(fields)):
                raise ValueError('handoff selection must preserve declared evidence and uncertainty')
    final_ids = {n.node_id for n in plan.nodes}
    mapping = {nid: nid for nid in original}
    for group in raw.get('merge_groups', []):
        target = next(nid for nid in group if nid in final_ids)
        mapping.update({nid: target for nid in group})
    selections = {}
    compiled = plan.to_dict()
    for row in compiled['nodes']:
        nid = row['node_id']
        members = [key for key in original if mapping[key] == nid]
        refs = list(dict.fromkeys(p for key in members for p in specs[key]['sources']))
        chosen = materials if nid == plan.final_node_id else select_materials(materials, refs)
        fields = ['text'] if nid == plan.final_node_id else [f for f in HANDOFF_FIELDS
            if any(f in specs[key]['fields'] for key in members)]
        if fields == ['text']:
            row['contract']['output'] = {'format': 'text', 'fields': {'text': delivery_text(delivery, 'selective_final')}}
        else:
            row['contract']['output'] = {'format': 'json', 'fields': {f: HANDOFF_FIELDS[f] for f in fields}}
            check = delivery_text(delivery, 'intermediate_check')
            if check not in row['contract']['checks']:
                row['contract']['checks'] = [*row['contract']['checks'], check]
        uses = {}
        for parent in row['parents']:
            selected = set(f for key in members for old_parent, fs in specs[key]['uses'].items()
                           if mapping[old_parent] == parent for f in fs)
            uses[parent] = [f for f in HANDOFF_FIELDS if f in selected]
        selections[nid] = {'source_ids': [item['id'] for item in chosen], 'fields': fields, 'uses': uses}
    by_id = {row['node_id']: row for row in compiled['nodes']}
    for row in compiled['nodes']:
        nid = row['node_id']
        if nid == plan.final_node_id:
            selections[nid]['uses'] = {p: list(by_id[p]['contract']['output']['fields']) for p in row['parents']}
        row['contract']['inputs'] = {p: {'fields': fs, 'reason': '交接所需结果，并保留证据及限制条件。'}
                                     for p, fs in selections[nid]['uses'].items()}
    return validate_plan(compiled, required_criteria=plan.acceptance_criteria), decision, selections


@dataclass
class NodeContext:
    tasks: dict
    sources: dict
    record: dict
    final_node_id: str

    def validate_output(self, nid, decoded):
        if nid == self.final_node_id:
            return
        evidence = decoded['evidence']
        matches = re.findall(r'\[source:([a-z][a-z0-9_]{0,63})\]「([^」]+)」', evidence)
        mentioned = re.findall(r'\[source', evidence)
        if not matches or len(mentioned) != len(matches):
            raise ValueError('missing or malformed source evidence')
        for mid, quote in matches:
            if mid not in self.sources[nid] or not quote.strip() or quote not in self.sources[nid][mid]:
                raise ValueError('unknown source or nonverbatim evidence')
        return {'status': 'source-quotes-verified', 'quote_count': len(matches), 'semantic_support_verified': False}


def build_node_context(plan, request, conversation_context, selections):
    materials = request.get('materials', [])
    _, full, _ = prepare_inputs(request, conversation_context, for_node=True)
    _, base, _ = prepare_inputs({k: v for k, v in request.items() if k != 'materials'}, conversation_context)
    tasks, sources, nodes = {}, {}, {}
    for nid in plan.order():
        spec = selections[nid]
        chosen = [item for item in materials if item['id'] in spec['source_ids']]
        _, task, _ = prepare_inputs(request, conversation_context, selected_materials=chosen, for_node=True)
        if nid == plan.final_node_id:
            task = full
        tasks[nid] = task
        sources[nid] = {'task': base, **{item['id']: item['text'] for item in chosen}}
        for parent in spec['uses']:
            sources[nid].update(sources[parent])
        nodes[nid] = {**deepcopy(spec), 'task_bytes': len(task.encode()),
                      'full_task_bytes': len(full.encode()), 'task_sha256': hashlib.sha256(task.encode()).hexdigest()}
    return NodeContext(tasks, sources, {'policy_version': CONTEXT_POLICY,
        'material_partition': 'explicit' if materials else 'full-text-fallback',
        'semantic_source_coverage_verified': False, 'nodes': nodes}, plan.final_node_id)
