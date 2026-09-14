"""材料选择、字段交接与原文核对；模拟模型，不发网络请求。"""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from threading import Event

import pytest

from refractrouter.agent import run_agent
from refractrouter.openai_compatible import ChatResponse
from refractrouter.selective_context import SELECTIVE_PLANNER_SYSTEM
from refractrouter.task_materials import select_materials, validate_materials
from tests.test_automatic_dag import config
from tests.test_fast_dynamic_dag import Client, compact
from refractrouter.task_budget import request_input_bound

MATERIALS = [
    {'id': 'rules', 'text': '任何方案都须保留免责条款。'},
    {'id': 'cost', 'text': '费用上限为 100。' + '费用原始记录。' * 80, 'scope': 'local', 'requires': ['exception']},
    {'id': 'risk', 'text': '实施风险为中等。' + '风险原始记录。' * 80, 'scope': 'local'},
    {'id': 'exception', 'text': '临时方案须额外核对条件。', 'scope': 'local'},
]
FIELDS = ['facts', 'evidence', 'conclusion', 'uncertainty']


def selective_plan():
    raw = {**compact(('cost_node', []), ('risk_node', []), ('answer', ['cost_node', 'risk_node'])),
           'decision': 'parallel'}
    raw['context'] = {
        'cost_node': {'sources': ['cost'], 'fields': FIELDS, 'uses': {}},
        'risk_node': {'sources': ['risk'], 'fields': FIELDS, 'uses': {}},
        'answer': {'sources': [], 'fields': ['text'],
                   'uses': {p: ['conclusion', 'evidence', 'uncertainty'] for p in ('cost_node', 'risk_node')}},
    }
    return raw


class ContextClient(Client):
    def __init__(self, *, plan=None, invalid=None, invalid_node='cost_node'):
        super().__init__(plan=plan or selective_plan())
        self.invalid, self.invalid_node = invalid, invalid_node
    def complete(self, model, messages, **kwargs):
        payload = json.loads(messages[-1]['content'])
        if messages[0]['content'] == SELECTIVE_PLANNER_SYSTEM:
            self.calls.append((model, payload, 0))
            return ChatResponse(json.dumps(self.plan), 100, 100, 0, 0, 10, 1, 'stop', 'mock')
        reply = super().complete(model, messages, **kwargs)
        if payload.get('contract', {}).get('output', {}).get('format') == 'json':
            data = {f: {'facts': '只列当前部分事实。',
                       'evidence': '[source:rules]「任何方案都须保留免责条款。」',
                       'conclusion': '在限制条件下适用。', 'uncertainty': '仍须保留全部例外。'}[f]
                    for f in payload['contract']['output']['fields']}
            if payload['node_id'] == self.invalid_node:
                if self.invalid == 'missing-field':
                    data.pop('uncertainty')
                elif self.invalid is not None:
                    data['evidence'] = self.invalid
            return replace(reply, content=json.dumps(data, ensure_ascii=False))
        return reply


def run(tmp_path, client, **payload):
    summary = run_agent({'task': '按规则核对费用与风险，再完整给出建议。', 'template': 'auto',
        'plannerPolicy': 'minimal-v1', 'contextPolicy': 'selective-v1', 'materials': deepcopy(MATERIALS),
        'context': '前次讨论要求保留所有原始例外。', 'acceptanceCriteria': ['覆盖全部规则与例外'], **payload},
        provider_config=config(), client=client, mode='live', execute_paid_run=True, runs_dir=tmp_path)
    return summary, json.loads(Path(summary['result_path']).read_text())


def test_selection_keeps_global_dependencies_final_and_judge_fulltext(tmp_path):
    client = ContextClient()
    summary, raw = run(tmp_path, client)
    assert summary['status'] == 'completed', summary['issues']
    assert len(client.calls) == 5  # 一次规划、三个执行节点、一次未改变的交付评审。
    payloads = {p['node_id']: p for _, p, _ in client.calls if 'node_id' in p}
    cost, risk, final = (payloads[n] for n in ('cost_node', 'risk_node', 'answer'))
    assert '风险原始记录' not in cost['task']
    assert '费用原始记录' not in risk['task']
    assert '临时方案须额外核对条件' in cost['task']
    for p in payloads.values():
        assert '保留免责条款' in p['task'] and '前次讨论' in p['task'] and '覆盖全部规则与例外' in p['task']
    judge = next(p for m, p, _ in client.calls if m.role == 'judge')
    assert judge['task'] == final['task']
    assert all(item['text'] in final['task'] for item in MATERIALS)
    assert all(set(fields) == set(FIELDS) for fields in final['upstream'].values())
    stats = summary['context_selection']['nodes']
    assert stats['cost_node']['task_bytes'] < stats['cost_node']['full_task_bytes']
    assert stats['answer']['task_bytes'] == stats['answer']['full_task_bytes']
    assert raw['compiled_input_estimates']['cost_node']['base_input_bound'] < raw['compiled_input_estimates']['answer']['base_input_bound']
    for nid, p in payloads.items():
        assert stats[nid]['task_bytes'] == len(p['task'].encode())
    assert all('input_tokens' in row and 'output_tokens' in row for row in raw['calls'])
    for nid in ('cost_node', 'risk_node'):
        call = next(c for c in raw['calls'] if c['label'] == nid)
        assert request_input_bound(call['request_messages']) == raw['plan_admission'][nid]['input_estimate']['base_input_bound']
        row = next(n for n in raw['nodes'] if n['node_id'] == nid)
        assert row['evidence_validation']['semantic_support_verified'] is False
    assert sum(summary['cost_breakdown'].values()) == pytest.approx(sum(summary['costs'].values()))


def test_intermediate_handoff_filters_fields_and_preserves_evidence(tmp_path):
    plan = selective_plan()
    plan['nodes'].insert(2, compact(('check', ['cost_node']))['nodes'][0])
    plan['nodes'][-1]['parents'] = ['check', 'risk_node']
    plan['context']['check'] = {'sources': [], 'fields': ['conclusion', 'evidence', 'uncertainty'],
        'uses': {'cost_node': ['conclusion', 'evidence', 'uncertainty']}}
    plan['context']['answer']['uses'] = {p: ['conclusion', 'evidence', 'uncertainty'] for p in ('check', 'risk_node')}
    client = ContextClient(plan=plan)
    summary, raw = run(tmp_path, client)
    assert summary['status'] == 'completed', summary['issues']
    p = next(p for _, p, _ in client.calls if p.get('node_id') == 'check')
    assert set(p['upstream']['cost_node']) == {'conclusion', 'evidence', 'uncertainty'}
    row = next(r for r in raw['nodes'] if r['node_id'] == 'check')
    assert row['handoff_bytes']['cost_node'] == len(json.dumps(p['upstream']['cost_node'], ensure_ascii=False).encode())


@pytest.mark.parametrize('bad', ['missing-field', '没有证据', '[source:unknown]「任何方案都须保留免责条款。」',
    '[source:rules]「材料并不存在的事实」', '[source:rules]「 」',
    '[source:rules]「任何方案都须保留免责条款。」 [source:unknown] 未提供原文'])
def test_bad_handoff_is_billed_and_blocks_join(tmp_path, bad):
    client = ContextClient(invalid=bad)
    summary, raw = run(tmp_path, client)
    assert summary['status'] == 'failed'
    assert not any(p.get('node_id') == 'answer' or m.role == 'judge' for m, p, _ in client.calls)
    assert all(row['status'] in {'billed', 'cancelled-before-dispatch'} for row in raw['calls'])
    assert summary['costs']['unconfirmed'] == 0


@pytest.mark.parametrize('bad', ['unknown-source', 'unknown-field', 'drop-evidence', 'missing-node'])
def test_bad_planning_contract_fails_before_execution(tmp_path, bad):
    p = selective_plan()
    if bad == 'unknown-source':
        p['context']['cost_node']['sources'] = ['not_available']
    elif bad == 'unknown-field':
        p['context']['answer']['uses']['cost_node'].append('fiction')
    elif bad == 'drop-evidence':
        p['context']['answer']['uses']['cost_node'] = ['conclusion']
    else:
        p['context'].pop('risk_node')
    client = ContextClient(plan=p)
    summary, raw = run(tmp_path, client)
    assert summary['status'] == 'failed' and len(client.calls) == 1
    assert raw['calls'][0]['status'] == 'billed'


def test_no_structured_materials_falls_back_to_complete_task(tmp_path):
    p = selective_plan()
    for row in p['context'].values():
        row['sources'] = []
    class Plain(ContextClient):
        def complete(self, model, messages, **kwargs):
            reply = super().complete(model, messages, **kwargs)
            payload = json.loads(messages[-1]['content'])
            if payload.get('node_id') in ('cost_node', 'risk_node'):
                data = json.loads(reply.content)
                data['evidence'] = '[source:task]「按规则核对费用与风险」'
                reply = replace(reply, content=json.dumps(data))
            return reply
    client = Plain(plan=p)
    summary, raw = run(tmp_path, client, materials=[])
    assert summary['status'] == 'completed', summary['issues']
    assert summary['context_selection']['material_partition'] == 'full-text-fallback'
    tasks = [p['task'] for _, p, _ in client.calls if 'node_id' in p]
    assert len(set(tasks)) == 1


def test_merge_unions_source_selection_and_keeps_all_fields(tmp_path):
    p = selective_plan()
    p['decision'] = 'isolation'
    p['merge_groups'] = [['cost_node', 'risk_node']]
    client = ContextClient(plan=p)
    summary, raw = run(tmp_path, client)
    assert summary['status'] == 'completed', summary['issues']
    assert len(client.calls) == 4
    node = next(p for _, p, _ in client.calls if p.get('node_id') == 'risk_node')
    assert '费用原始记录' in node['task'] and '风险原始记录' in node['task']
    assert set(node['contract']['output']['fields']) == set(FIELDS)


def test_merge_entire_graph_direct_keeps_full_input_and_text_delivery(tmp_path):
    p = selective_plan()
    p['decision'] = 'direct'
    p['merge_groups'] = [['cost_node', 'risk_node', 'answer']]
    summary, raw = run(tmp_path, ContextClient(plan=p))
    assert summary['status'] == 'completed', summary['issues']
    assert len(raw['calls']) == 3
    assert raw['plan']['nodes'][0]['contract']['output']['format'] == 'text'
    assert summary['context_selection']['nodes']['answer']['source_ids'] == [m['id'] for m in MATERIALS]


def test_source_dependency_cycles_terminate_and_global_is_default():
    pack = [{'id': 'a', 'text': '全局', 'requires': ['b']},
            {'id': 'b', 'text': '例外', 'scope': 'local', 'requires': ['a']}]
    assert select_materials(validate_materials(pack), []) == pack


@pytest.mark.parametrize('pack', [[{'id': 'task', 'text': '非法覆盖'}],
    [{'id': 'a', 'text': 'a', 'requires': ['missing']}],
    [{'id': 'a', 'text': 'a'}, {'id': 'a', 'text': '重复'}]])
def test_bad_material_pack_fails_before_paid_calls(tmp_path, pack):
    client = ContextClient()
    with pytest.raises(ValueError):
        run(tmp_path, client, materials=pack)
    assert not client.calls


def test_explicit_direct_comparator_gets_same_full_material_and_judge(tmp_path):
    client = ContextClient()
    summary = run_agent({'task': '核对规则', 'template': 'single', 'materials': MATERIALS},
        provider_config=config(), client=client, mode='live', execute_paid_run=True, runs_dir=tmp_path)
    assert summary['status'] == 'completed', summary['issues']
    assert len(client.calls) == 2
    node = next(p for _, p, _ in client.calls if 'node_id' in p)
    judge = next(p for m, p, _ in client.calls if m.role == 'judge')
    assert node['task'] == judge['task'] and all(m['text'] in node['task'] for m in MATERIALS)


def test_dynamic_combination_is_explicitly_rejected_before_calls(tmp_path):
    client = ContextClient()
    with pytest.raises(ValueError, match='no dynamic splitting'):
        run(tmp_path, client, maxDynamicSplits=1)
    assert not client.calls


def test_material_selection_preserves_parallel_dispatch(tmp_path):
    class Parallel(ContextClient):
        def __init__(self):
            super().__init__()
            self.cost, self.risk = Event(), Event()
        def complete(self, model, messages, **kwargs):
            nid = json.loads(messages[-1]['content']).get('node_id')
            if nid == 'cost_node':
                self.cost.set()
                assert self.risk.wait(2)
            if nid == 'risk_node':
                self.risk.set()
                assert self.cost.wait(2)
            return super().complete(model, messages, **kwargs)
    summary, raw = run(tmp_path, Parallel())
    assert summary['status'] == 'completed', summary['issues']
    assert raw['execution']['peak_running_nodes'] == 2


def test_unselected_source_cannot_be_cited_by_independent_branch(tmp_path):
    client = ContextClient(invalid='[source:risk]「实施风险为中等。」')
    summary, raw = run(tmp_path, client)
    assert summary['status'] == 'failed'
    assert not any(p.get('node_id') == 'answer' for _, p, _ in client.calls)


def test_native_tool_combination_fails_before_calls(tmp_path):
    client = ContextClient()
    with pytest.raises(ValueError, match='without native tools'):
        run_agent({'task': '核对材料', 'template': 'auto', 'plannerPolicy': 'minimal-v1',
            'contextPolicy': 'selective-v1'}, provider_config=config(), client=client,
            tool_runtime=object(), mode='live', execute_paid_run=True, runs_dir=tmp_path)
    assert not client.calls


def test_structured_multiline_schedule_keeps_original_dependency_guard(tmp_path):
    from refractrouter.task_inputs import prepare_inputs
    material = {'id': 'schedule', 'text': '第 0 天开始。\nA 需要 2 天\nB 需要 3 天且必须等 A 完成\n'}
    _, _, guard = prepare_inputs({'task': '核对排程', 'materials': [material], 'verifyDependencies': True})
    assert guard.status == 'supported'
    p = {**compact(('answer', [])), 'decision': 'direct',
         'context': {'answer': {'sources': [], 'fields': ['text'], 'uses': {}}}}
    client = ContextClient(plan=p)
    client.output = 'A→C'
    summary, raw = run(tmp_path, client, task='核对排程', materials=[material])
    assert summary['status'] == 'content-verification-failed'
    assert raw['dependency_evidence']['source_status'] == 'supported'
    assert not any(m.role == 'judge' for m, _, _ in client.calls)
