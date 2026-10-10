"""自动路由展示读取冻结事实，不产生新调用或修改历史决策。"""
from copy import deepcopy
import json

import pytest

from refractrouter.automatic_trace import history, project
from refractrouter.planning_runtime import PlanningRuntime

RID = '20261007T064045Z-118980e3a74b'


def test_tool_review_capacity_is_visible_without_private_evidence_or_rewriting_old_failure():
    tool = {'passed': False, 'reason': 'review-input-capacity-exceeded',
        'message': '完整审核输入超出实际模型容量，未派发。', 'evidence_bytes': 65759,
        'evidence_limit_bytes': None, 'capacity_basis': 'complete-review-request-v1',
        'review_model_id': 'reviewer', 'review_input_bound': 200000, 'review_input_limit': 24576,
        'records': [{'tool': 'web_search', 'call_id': 'search-1', 'outcome': 'returned',
                     'content': '机密工具原文'}]}
    result = project({'run_id': RID, 'status': 'tool-requirement-failed', 'tool_validation': tool})
    assert result['tools']['evidence_bytes'] == 65759
    assert result['tools']['review_input_bound'] == 200000
    assert result['tools']['review_input_limit'] == 24576
    assert result['tools']['passed'] is False
    assert '机密工具原文' not in json.dumps(result, ensure_ascii=False)


def evidence():
    summary = {'run_id': RID, 'strategy': 'auto', 'status': 'completed',
        'model_routes': {'answer': {'id': 'subscription'}},
        'candidate_models': {mid: {'provider': 'ark' if mid == 'subscription' else 'official',
            'model': mid, 'billing_unit': 'CNY', 'billing_mode': 'subscription' if mid == 'subscription' else 'metered'}
            for mid in ['subscription', 'cheap', 'kimi', 'small', 'untrusted']},
        'plan_admission': {'answer': {'model_reasons': {'subscription': 'eligible', 'cheap': 'eligible',
            'kimi': 'eligible', 'small': 'input-or-output-capacity', 'untrusted': 'data-domain-not-authorized'}}},
        'complexity_gate': {'rule_decision': 'dag', 'decision': 'direct', 'combination': 'coupled-sequential-work',
            'local_decision': {'model': 'jev', 'backend': 'jev', 'rawAnswers': {'dependency': {'type': 'noul', 'noul': .8}},
                'probabilityBasis': 'derived-not-model', 'recordPath': '/secret/path', 'costCny': .001}},
        'quality': {'score': 100, 'passed': True, 'rationale': '工具回执一致'},
        'answer': '不应进入展示接口的正文'}
    runtime = {'status': 'completed', 'calls': [
        {'label': 'answer', 'model_id': 'subscription', 'category': 'production', 'billing_unit': 'CNY',
         'billing_mode': 'subscription', 'reserved': 3, 'charged': .3, 'status': 'billed',
         'input_tokens': 10, 'output_tokens': 20, 'ttft_ms': 100, 'latency_ms': 800,
         'route': {'provider': 'ark', 'model': 'flash', 'reasoning_effort': 'high'},
         'request_messages': ['机密'], 'response_output': '机密'},
        {'label': 'review', 'model_id': 'cheap', 'category': 'evaluation', 'billing_unit': 'CNY',
         'billing_mode': 'metered', 'reserved': .5, 'charged': .01, 'status': 'billed'}],
        'reference_costs_cny': {'production': .3, 'evaluation': .01},
        'cash_costs_cny': {'production': 0, 'evaluation': .01},
        'cash_limit_snapshot': {'production': 2, 'evaluation': 1},
        'accounting_basis': 'public-reference-valuation',
        'tool_validation': {'passed': True, 'records': [{'node': 'answer', 'tool': 'bash',
            'call_id': 'tool-1', 'outcome': 'completed', 'arguments': '机密'}]}}
    return summary, runtime


def test_trace_keeps_all_candidates_raw_judge_and_real_call_identity():
    s, r = evidence()
    before = deepcopy((s, r))
    trace = project(s, r)
    assert len(trace['candidates']) == 5
    assert trace['candidates'][2]['admission'][0]['reason'] == 'eligible'
    assert trace['candidates'][-1]['admission'][0]['reason'] == 'data-domain-not-authorized'
    assert trace['structure']['judge']['rawAnswers']['dependency']['noul'] == .8
    assert trace['structure']['judge']['probabilityBasis'] == 'derived-not-model'
    assert trace['structure']['decision'] == 'direct'
    assert trace['calls'][0]['route']['reasoning_effort'] == 'high'
    assert trace['calls'][0]['ttft_ms'] == 100
    assert '机密' not in json.dumps(trace, ensure_ascii=False)
    assert 'recordPath' not in json.dumps(trace)
    assert (s, r) == before


def test_dag_history_keeps_frozen_topology_and_states_without_private_payloads():
    summary, runtime = evidence()
    summary['status'] = 'failed'
    summary['wall_time_ms'] = 90238
    summary['dag'] = {'phase': 'finished', 'status': 'failed', 'simulated': False,
        'reason': '最后收到的流程', 'request_messages': ['私有提示'],
        'nodes': [{'id': 'first', 'objective': '读取材料', 'parents': [], 'node_type': 'extraction',
            'state': 'ok', 'attempt': 1, 'recovery': None,
            'model': {'id': 'frozen-model', 'provider': 'ark', 'model': 'flash',
                      'reasoning_effort': 'low', 'credential': '私有密钥'},
            'response_output': '私有正文'},
            {'id': 'second', 'objective': '汇总', 'parents': ['first'], 'node_type': 'synthesis',
             'state': 'blocked', 'attempt': 0, 'model': None, 'recovery': None}]}
    before = deepcopy((summary, runtime))
    trace = project(summary, runtime)
    assert trace['dag']['status'] == 'failed'
    assert trace['dag']['nodes'][1]['parents'] == ['first']
    assert trace['dag']['nodes'][1]['state'] == 'blocked'
    assert trace['dag']['nodes'][0]['model']['reasoning_effort'] == 'low'
    assert trace['wall_time_ms'] == 90238
    assert '私有' not in json.dumps(trace, ensure_ascii=False)
    assert (summary, runtime) == before
    assert project({}, {})['dag']['nodes'] == []


def test_final_correction_trace_keeps_decisions_and_protection_without_private_payloads():
    s,r=evidence()
    r['final_correction']={'version':'bounded-final-correction-v1','maximum':1,'attempt':1,
        'status':'accepted','accepted':True,'model_id':'subscription',
        'previous_output':'不应展示的被拒正文','corrected_output':'不应展示的整段正文',
        'initial_feedback':{'hidden_expected':'隐藏标准答案'},
        'initial_deterministic_validation':{'expected':'隐藏标准答案'},
        'initial_evaluation':{'passed':False,'score':55,'rationale':'材料外断言'},
        'evaluation':{'passed':True,'score':95,'rationale':'复审通过'},
        'review_protection':{'reserved':.7,'billing_unit':'CNY','input_upper_bound':50000,
                             'label':'final-judge-correction','messages':'私有输入'}}
    row=project(s,r)['final_correction']
    assert row['initial_evaluation']['passed'] is False and row['evaluation']['passed'] is True
    assert row['review_protection']['reserved']==.7
    assert '不应展示' not in json.dumps(row,ensure_ascii=False)
    assert '隐藏' not in json.dumps(row,ensure_ascii=False) and '私有' not in json.dumps(row,ensure_ascii=False)


def test_time_contract_block_is_visible_but_never_exports_full_candidate_or_source():
    s, r = evidence()
    r['time_contract_validation'] = {'version': 'review-time-reservation-guard-v1',
        'applicable': True, 'passed': False, 'reason': '预留不是到期计时器',
        'review_wait_ms': 180000, 'execution_reserve_ms': 60000,
        'findings': [{'answer_quote': '私有候选正文'}], 'task': '私有完整上下文'}
    trace = project(s, r)
    assert trace['quality_gate'] == 'failed'
    assert trace['time_contract_validation']['reason'] == '预留不是到期计时器'
    assert '私有' not in json.dumps(trace, ensure_ascii=False)


def test_source_attribution_check_preserves_conservative_reason_without_private_text():
    s, r = evidence()
    r['source_state_validation'] = {'version': 'source-state-attribution-guard-v1',
        'applicable': True, 'passed': False, 'reason': '需澄清归属，不证明实际未验证',
        'findings': [{'answer_quote': '私有候选全文'}]}
    trace = project(s, r)
    assert trace['quality_gate'] == 'failed'
    assert trace['source_state_validation']['passed'] is False
    assert '私有' not in json.dumps(trace, ensure_ascii=False)


def test_grounding_trace_preserves_verdicts_and_verified_short_quotes_only():
    s,r=evidence()
    s['quality']['grounding_checks']=[{'check_id':'source-state','status':'FAIL',
        'answer_quote':'未经实测','source_quote':None,'rationale':'未提供验证信息',
        'request_messages':['不应展示的完整上下文']}]
    rows=project(s,r)['quality']['grounding_checks']
    assert rows==[{'check_id':'source-state','status':'FAIL','answer_quote':'未经实测',
        'source_quote':None,'rationale':'未提供验证信息'}]
    assert 'request_messages' not in json.dumps(rows)


def test_review_format_trace_keeps_only_core_normalization_metadata():
    s,r=evidence()
    s['quality']['response_normalization']={'version':'review-field-spelling-v1','model_calls_added':0,
        'request_messages':['私有请求不展示'],'changes':[{'check_id':'source-claim-c3',
            'from':'rationalale','to':'rationale','private_payload':'私有上下文不展示'}]}
    value=project(s,r)['quality']['response_normalization']
    assert value=={'version':'review-field-spelling-v1','model_calls_added':0,
        'changes':[{'check_id':'source-claim-c3','from':'rationalale','to':'rationale'}]}
    assert '私有' not in json.dumps(value,ensure_ascii=False)


def test_cash_reference_pending_and_external_judge_are_separate():
    s, r = evidence()
    r['calls'].append({'label': 'inflight', 'model_id': 'cheap', 'category': 'production',
        'status': 'unknown-usage', 'charged': .5, 'reserved': .5, 'billing_mode': 'metered'})
    r['cash_costs_cny']['production'] = .5
    trace = project(s, r)
    row = trace['ledger'][0]
    assert row['billed_cash_cny'] == 0  # 订阅不是新增按量现金
    assert row['pending_cash_cny'] == .5 and row['pending_count'] == 1
    assert row['remaining_cash_cny'] == 1.5
    assert trace['external_judge_cost_cny'] == .001  # 不偷偷计入主任务额度
    del s['complexity_gate']['local_decision']['costCny']
    assert project(s, r)['external_judge_cost_cny'] is None
    r['calls'][-1]['charged'] = None
    assert project(s, r)['ledger'][0]['pending_cash_cny'] is None
    assert project(s, r)['ledger'][0]['remaining_cash_cny'] is None


@pytest.mark.parametrize('unit', ['CNY', 'AFP'])
def test_missing_call_unit_uses_only_frozen_evidence_and_preserves_explicit_units(unit):
    s, r = evidence()
    r['billing_unit'] = unit
    s['candidate_models']['subscription']['billing_unit'] = unit
    del r['calls'][0]['billing_unit']
    before = deepcopy((s, r))
    assert project(s, r)['calls'][0]['billing_unit'] == unit
    assert project(s, r)['calls'][1]['billing_unit'] == 'CNY'
    assert (s, r) == before
    del s['candidate_models']['subscription']['billing_unit']
    assert project(s, r)['calls'][0]['billing_unit'] == unit
    del r['billing_unit']
    assert 'billing_unit' not in project(s, r)['calls'][0]


def test_released_reservation_and_zero_unlimited_are_not_billed():
    s, r = evidence()
    r['calls'][1].update(status='cancelled-before-dispatch', charged=0)
    r['cash_limit_snapshot']['evaluation'] = 0
    row = project(s, r)['ledger'][1]
    assert row['billed_cash_cny'] == 0 and row['pending_count'] == 0
    assert row['unlimited_cash'] and row['remaining_cash_cny'] is None


def test_missing_records_do_not_invent_zero_cost_or_verified_budget():
    trace = project({'run_id': RID})
    assert trace['ledger'][0]['cash_limit_cny'] is None
    assert trace['ledger'][0]['reference_occupied_cny'] is None
    assert trace['ledger'][0]['billed_cash_cny'] is None
    assert trace['quality'] == {} and trace['review'] == {}
    assert 'per-candidate-budget-check' in trace['missing_evidence']
    assert 'call-ledger' in trace['missing_evidence']
    assert project({'run_id': RID}, {'calls': []})['ledger'][0]['billed_cash_cny'] == 0


def test_review_envelope_and_alias_evidence_are_exposed_without_raw_candidate():
    s, r = evidence()
    r['review'] = {'required': True, 'status': 'blocked-deterministic-check',
        'time_reserve_ms': 30000, 'output_cap': 8192, 'limits_version': 'automatic-review-envelope-v1'}
    s.pop('review', None)
    r['deterministic_validation'] = {'passed': False, 'reason': '固定事实不符', 'rawAnswer': '机密'}
    r['compact_planning'] = {'attempts': [{'output': '机密', 'type_normalization': {
        'version': 'compact-type-alias-v1', 'changes': [{'node_id': 'one', 'from': 'analysis', 'to': 'synthesis'}]}}]}
    trace = project(s, r)
    assert trace['review']['output_cap'] == 8192 and trace['review']['time_reserve_ms'] == 30000
    assert trace['deterministic_validation'] == {'passed': False, 'reason': '固定事实不符'}
    assert trace['planner_normalizations'][0]['type_normalization']['changes'][0]['to'] == 'synthesis'
    assert '机密' not in json.dumps(trace, ensure_ascii=False)


def test_judge_approve_below_quality_floor_does_not_become_verified_pass():
    s, r = evidence()
    s['status'] = 'quality-failed'
    s['quality']['score'] = 60
    r['routing'] = {'quality_min_per_node': 80}
    trace = project(s, r)
    assert trace['quality']['passed'] is True
    assert trace['quality_gate'] == 'failed'


def test_route_comparison_never_becomes_execution_or_quality_evidence():
    s, r = evidence()
    s['route_comparison'] = {'route': 'direct', 'reason': 'direct-estimated-cost-not-worse',
        'direct': {'total_estimated_cost': .7}, 'dag': {'total_estimated_cost': 1.4},
        'estimate_scope': 'known-calls-only', 'complete_task_cost_bound': None,
        'tool_call_limit': 'unlimited', 'decision_factors': {'task_specific_dag_quality_gain_verified': False}}
    trace = project(s, r)
    assert trace['comparison']['route'] == 'direct'
    assert trace['comparison']['complete_task_cost_bound'] is None
    assert not trace['comparison']['decision_factors']['task_specific_dag_quality_gain_verified']
    assert len(trace['calls']) == 2  # 未执行的 DAG 不生成假调用


def test_node_evidence_and_parallel_facts_are_projected_without_private_materials():
    s, r = evidence()
    s['cost_trace'] = {'selected_nodes': [{'node_id': 'answer', 'model_id': 'subscription',
        'expected_cost': .05, 'expected_input_tokens': 3000, 'expected_output_tokens': 1000,
        'quality_source': 'independent-node-evaluation', 'quality_prior': 90,
        'quality_evidence': {'kind': 'independent-node-evaluation', 'samples': 3,
            'bundleSha256': 'a' * 64, 'private_context': '不能展示的原始材料'},
        'node_features': {'type': 'generation', 'difficulty': 'medium', 'risk': 'high'}}]}
    s['cost_trace']['node_candidates'] = [{'node_id': 'answer', 'model_id': 'subscription',
        'provider': 'ark', 'model': 'flash', 'selected': True, 'eligible': True,
        'quality_evidence': {'samples': 3, 'heldOutStatus': 'passed', 'heldOutSamples': 1,
                             'private_context': '不能展示的原始材料'}}]
    r['execution'] = {'peak_active_nodes': 3, 'policy': {'max_concurrency': 3},
                      'failure_policy': 'stop-dispatch-and-drain', 'request_messages': ['私有请求']}
    row = project(s, r)
    assert row['node_forecasts'][0]['quality_evidence']['samples'] == 3
    assert row['parallel_execution']['peak_active_nodes'] == 3
    assert row['node_model_candidates'][0]['quality_evidence']['heldOutStatus'] == 'passed'
    assert '不能展示' not in json.dumps(row, ensure_ascii=False)
    assert '私有请求' not in json.dumps(row, ensure_ascii=False)


def test_history_uses_frozen_budget_and_does_not_write_or_reroute(tmp_path):
    s, r = evidence()
    del r['cash_limit_snapshot']
    path = tmp_path / RID
    path.mkdir()
    for name, data in [('summary', s), ('result', r), ('provider-config', {'cashLimits': {'production': 2, 'evaluation': 1}, 'apiKey': 'secret'})]:
        (path / (name+'.json')).write_text(json.dumps(data))
    before = {p.name: p.read_bytes() for p in path.iterdir()}
    result = history(tmp_path, [RID, RID])
    assert len(result['records']) == 1 and result['errors'] == []
    assert result['records'][0]['ledger'][0]['cash_limit_cny'] == 2
    assert 'secret' not in json.dumps(result)
    assert {p.name: p.read_bytes() for p in path.iterdir()} == before


@pytest.mark.parametrize('ids', [['../secret'], [RID+'/result.json'], [RID]*21, 'all', [None]])
def test_history_rejects_paths_unbounded_queries_and_invalid_ids(tmp_path, ids):
    with pytest.raises(ValueError):
        history(tmp_path, ids)


def test_history_rejects_symlink_and_reports_missing_evidence(tmp_path):
    target = tmp_path / 'secret'
    target.mkdir()
    (tmp_path / RID).symlink_to(target)
    value = history(tmp_path, [RID])
    assert value['records'] == [] and value['errors'][0]['run_id'] == RID


def test_worker_handshake_and_read_only_operation(tmp_path):
    runtime = PlanningRuntime(tmp_path)
    assert 'automatic-routing-trace-v1' in runtime._handle({'op': 'handshake'})['capabilities']
    assert runtime._handle({'op': 'automatic-trace', 'runIds': []})['records'] == []
    assert runtime.runs == {}


def test_per_candidate_budget_diagnostics_explain_actual_search_without_changing_choice():
    from refractrouter.node_routing import NodeProfile, route_nodes
    from refractrouter.task_plan import preview_plan
    plan = preview_plan('回答问题')
    profiles = [NodeProfile(mid, 'generation', 90, cost, 100, 0)
        for mid, cost in [('ark', .2), ('kimi', 2.3), ('cheap', .3)]]
    result = route_nodes(plan, profiles, method='A', quality_min=80, cost_max=10, latency_max_ms=None,
        cash_max=2, model_billing_modes={'ark': 'subscription', 'kimi': 'metered', 'cheap': 'metered'},
        model_providers={'ark': 'ark', 'kimi': 'kimi', 'cheap': 'deepseek'})
    node = plan.nodes[0].node_id
    assert result['assignments'][node] == 'ark'
    checks = result['diagnostics']['candidate_checks'][node]
    assert checks['kimi']['feasible_assignments'] == 0
    assert checks['kimi']['rejected_assignments']['cash'] == 1
    assert checks['cheap']['feasible_assignments'] == 1
    assert checks['ark']['status'] == 'selected'
