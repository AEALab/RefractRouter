"""成本优先规划：默认直接回答、成本依据显式记录且无硬截断；仅使用模拟模型。"""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from refractrouter.agent import run_agent
from refractrouter.minimal_planning import COST_FIRST_POLICY, MINIMAL_COST_SYSTEM, compile_minimal
from refractrouter.openai_compatible import ChatResponse
from refractrouter.selective_context import SELECTIVE_COST_PLANNER_SYSTEM
from tests.test_automatic_dag import config
from tests.test_fast_dynamic_dag import Client, compact
from tests.test_selective_context import (FIELDS, MATERIALS, ContextClient, selective_plan)


def cost_plan(decision, *jobs, drivers=(), risks=(), **extra):
    return {**compact(*jobs), 'decision': decision,
            'cost': {'drivers': list(drivers), 'risks': list(risks)}, **extra}


class CostClient(Client):
    def complete(self, model, messages, **kwargs):
        if messages[0]['content'] in (MINIMAL_COST_SYSTEM, SELECTIVE_COST_PLANNER_SYSTEM):
            self.calls.append((model, json.loads(messages[-1]['content']), 0))
            return ChatResponse(json.dumps(self.plan), 120, 100, 0, 0, 10, 1, 'stop', 'mock')
        return super().complete(model, messages, **kwargs)


class SelectiveCostClient(ContextClient):
    def complete(self, model, messages, **kwargs):
        if messages[0]['content'] == SELECTIVE_COST_PLANNER_SYSTEM:
            self.calls.append((model, json.loads(messages[-1]['content']), 0))
            return ChatResponse(json.dumps(self.plan), 120, 100, 0, 0, 10, 1, 'stop', 'mock')
        return super().complete(model, messages, **kwargs)


def run(tmp_path, client, **payload):
    summary = run_agent({'task': '按原始规则分别核对费用和条件，保留所有例外后给出建议。',
        'template': 'auto', 'plannerPolicy': 'minimal-v2', **payload},
        provider_config=config(), client=client, mode='live', execute_paid_run=True, runs_dir=tmp_path)
    return summary, json.loads(Path(summary['result_path']).read_text())


def test_direct_baseline_records_uncalibrated_cost_basis(tmp_path):
    client = CostClient(plan=cost_plan('direct', ('answer', [])))
    summary, raw = run(tmp_path, client)
    assert summary['status'] == 'completed', summary['issues']
    assert len(client.calls) == 3
    assert summary['planning_policy'] == COST_FIRST_POLICY
    decision = summary['planning_decision']
    assert decision['decision'] == 'direct' and decision['benefit_verified'] is False
    assert decision['cost_basis'] == {'policy': COST_FIRST_POLICY, 'declared_drivers': [],
        'declared_risks': [], 'estimate': None, 'calibration': 'unregistered', 'benefit_verified': False}
    assert decision['cost_gate']['verified_drivers'] == [] and decision['cost_gate']['fallback'] is None
    assert decision['cost_gate']['estimate'] is None
    assert raw['compact_planning']['cost_gate'] == decision['cost_gate']


def test_missing_cost_declaration_fails_before_production(tmp_path):
    client = CostClient(plan={**compact(('answer', [])), 'decision': 'direct'})
    summary, raw = run(tmp_path, client)
    assert summary['status'] == 'failed' and len(client.calls) == 1 and not raw['nodes']
    assert 'cost declaration' in raw['compact_planning']['attempts'][0]['error']


def test_declared_stop_condition_blocks_split_before_any_node(tmp_path):
    client = CostClient(plan=cost_plan('parallel', ('a', []), ('b', []), ('answer', ['a', 'b']),
        drivers=['parallel'], risks=['repeated-context']))
    summary, raw = run(tmp_path, client)
    assert summary['status'] == 'failed' and len(client.calls) == 1 and not raw['nodes']
    assert 'cost risks: repeated-context' in raw['compact_planning']['attempts'][0]['error']


def test_verified_parallel_and_cheap_model_drivers_keep_the_dag(tmp_path):
    client = CostClient(plan=cost_plan('parallel', ('left', []), ('right', []), ('answer', ['left', 'right']),
        drivers=['parallel', 'cheap-model'], risks=['handoff-overhead']))
    summary, raw = run(tmp_path, client)
    assert summary['status'] == 'completed', summary['issues']
    assert len(client.calls) == 5 and len(raw['plan']['nodes']) == 3
    decision = summary['planning_decision']
    assert decision['cost_gate']['verified_drivers'] == ['parallel', 'cheap-model']
    assert decision['cost_gate']['unverified_drivers'] == []
    assert decision['cost_gate']['fallback'] is None
    assert raw['plan_analysis']['parallel_opportunities'] == [['left', 'right']]


def test_unverified_driver_merges_back_to_direct_inside_the_same_call(tmp_path):
    client = CostClient(plan=cost_plan('isolation', ('facts', []), ('answer', ['facts']),
        drivers=['compact-output'], risks=['handoff-overhead']))
    summary, raw = run(tmp_path, client)
    assert summary['status'] == 'completed', summary['issues']
    assert len(client.calls) == 3
    nodes = raw['plan']['nodes']
    assert [n['node_id'] for n in nodes] == ['answer']
    assert 'facts 完成职责' in nodes[0]['prompt_template']
    assert 'answer 完成职责' in nodes[0]['prompt_template']
    assert nodes[0]['contract']['covers'] == [0]
    decision = summary['planning_decision']
    assert decision['decision'] == 'direct' and decision['proposed_decision'] == 'isolation'
    assert decision['merge_groups'] == [['facts', 'answer']] and decision['final_node_count'] == 1
    assert decision['cost_gate']['fallback'] == 'merged-to-direct'
    assert decision['cost_gate']['fallback_reason'] == 'no-verified-cost-driver'
    assert decision['cost_gate']['unverified_drivers'] == ['compact-output']
    assert decision['cost_gate']['structural_checks']['cheap-model'] is True
    assert not any(p.get('node_id') == 'facts' for _, p, _ in client.calls)
    assert '保留所有例外' in next(p['task'] for m, p, _ in client.calls if m.role != 'judge')


def test_structured_handoff_verifies_compact_output_driver(tmp_path):
    proposed = {**selective_plan(), 'cost': {'drivers': ['parallel', 'compact-output'], 'risks': []}}
    client = SelectiveCostClient(plan=proposed)
    summary, raw = run(tmp_path, client, contextPolicy='selective-v1', materials=deepcopy(MATERIALS),
        context='前次讨论要求保留所有原始例外。', acceptanceCriteria=['覆盖全部规则与例外'])
    assert summary['status'] == 'completed', summary['issues']
    decision = summary['planning_decision']
    assert decision['cost_gate']['verified_drivers'] == ['parallel', 'compact-output']
    assert decision['cost_gate']['fallback'] is None
    rows = raw['plan']['nodes']
    assert 'evidence' in rows[0]['contract']['output']['fields']
    for row in rows[:-1]:
        assert set(row['contract']['output']['fields']) <= set(FIELDS)
        assert any('不得复述' in check for check in row['contract']['checks'])
    final = rows[-1]['contract']['output']
    assert final['format'] == 'text' and '不复述' in final['fields']['text']
    assert raw['context_selection']['semantic_source_coverage_verified'] is False


def test_compact_delivery_changes_wording_without_lowering_any_cap():
    jobs = (('facts', []), ('answer', ['facts']))
    baseline, _ = compile_minimal({**compact(*jobs), 'decision': 'isolation'})
    compressed, decision = compile_minimal({**compact(*jobs), 'decision': 'isolation',
        'cost': {'drivers': ['compact-output'], 'risks': []}}, cost_first=True, delivery='compact-v1')
    for nid in ('facts', 'answer'):
        assert compressed.contracts[nid]['capability'] == baseline.contracts[nid]['capability']
    assert compressed.contracts['facts']['checks'] != baseline.contracts['facts']['checks']
    assert any('不得复述' in check for check in compressed.contracts['facts']['checks'])
    assert '不复述' in compressed.contracts['answer']['output']['fields']['text']
    assert decision['policy_version'] == COST_FIRST_POLICY
    assert decision['cost_basis']['estimate'] is None


@pytest.mark.parametrize('cost, message', [
    ({'drivers': ['parallel', 'parallel'], 'risks': []}, 'unique values'),
    ({'drivers': ['magic'], 'risks': []}, 'unique values'),
    ({'drivers': ['parallel'], 'risks': [], 'estimate': 1.0}, 'invalid cost declaration fields'),
    ({'drivers': [], 'risks': []}, 'split decision requires at least one cost driver'),
    ({'drivers': ['parallel'], 'risks': ['verbose-output']}, 'contradicts declared cost risks'),
])
def test_invalid_cost_declarations_are_rejected(cost, message):
    raw = {**compact(('left', []), ('right', []), ('answer', ['left', 'right'])),
           'decision': 'parallel', 'cost': cost}
    with pytest.raises(ValueError, match=message):
        compile_minimal(raw, cost_first=True, parallel_capacity=2)


def test_direct_decision_cannot_claim_split_drivers_and_v1_ignores_cost():
    split = {**compact(('answer', [])), 'decision': 'direct',
             'cost': {'drivers': ['parallel'], 'risks': []}}
    with pytest.raises(ValueError, match='must not declare cost drivers'):
        compile_minimal(split, cost_first=True)
    with pytest.raises(ValueError, match='cost declaration requires cost-first planning'):
        compile_minimal({**split, 'cost': {'drivers': [], 'risks': []}})
