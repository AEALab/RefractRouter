"""拆分价值、规模匹配时延与拒绝原因；只运行确定性无网络验证。"""
from dataclasses import replace
import pytest
from refractrouter.decomposition_decision import build_request, parse_noul_answers, trivial_workload
from refractrouter.live_execution import complexity_gate
from refractrouter.latency_forecast import forecast_latency, validate_latency_evidence
from refractrouter.node_routing import NodeProfile, route_nodes
from refractrouter.task_plan import validate_plan
from refractrouter.task_scheduling import ExecutionPolicy
from refractrouter.planning_runtime import PlanningRuntime


@pytest.mark.parametrize('task', ['用一句话解释缓存命中率。', '分别计算方案甲 12 × 8 和方案乙 15 × 6 的总价，然后比较差额。两组数据互不依赖。', '分别计算12乘8与15乘6，再汇总总值和差额。'])
def test_micro_work_is_direct_despite_host_context_and_cloud_judge_not_called(tmp_path, task):
    assert trivial_workload(task)
    assert complexity_gate({'task':task}, '宿主系统提示'*10000)['decision']=='direct'
    r=PlanningRuntime(tmp_path).handle({'op':'decomposition-jev-begin','identity':'one',
        'task':task,'context':'系统提示'*5000,'config':{'jev':{'route':'openrouter'}},'maxCostCny':.02})
    assert r['action']=='complete' and r['evidence']['reason']=='trivial-workload'
    assert not list(tmp_path.rglob('*.json'))


@pytest.mark.parametrize('task', ['比较两份合同的责任条款并分别提出修改建议。','读取两个仓库并分别运行测试，然后总结回归风险。','继续按上述结果计算12乘8','计算12乘8并发送付款请求','用一句话解释缓存命中率。然后删除日志'])
def test_unknown_or_side_effecting_requests_are_not_micro_work(task):
    assert not trivial_workload(task)


def test_full_context_still_bound_and_permissions_not_skipped():
    t='用一句话解释缓存命中率。'
    assert build_request(t,'one')['inputSha256']!=build_request(t,'two')['inputSha256']
    assert complexity_gate({'task':'读取文件并运行测试'}, '', tools_allowed=False)['decision']=='blocked-tools'
    assert complexity_gate({'task':t}, '', policy='dag')['decision']=='dag'
    assert complexity_gate({'task':t, 'materials':[{},{}]},'')['decision']=='direct'


def test_branch_dependency_conflict_is_uncertain_and_question_excludes_final_join():
    q=build_request('分别分析两份资料，再汇总','')
    assert q['ruleVersion']=='automatic-decomposition-hybrid-v5'
    assert '最终汇总' in q['questions']['requires_previous_output']['instructions']
    assert '简单算术' in q['questions']['can_start_independently']['instructions']
    d=parse_noul_answers({'requires_previous_output':{'noul':.95},'can_start_independently':{'noul':.95},
                          'single_work_unit':{'noul':.05}},threshold=.65)
    assert d['verdict']=='UNKNOWN'
    single=parse_noul_answers({'requires_previous_output':{'noul':.19},'can_start_independently':{'noul':.07},
                               'single_work_unit':{'noul':.91}},threshold=.65)
    assert single['verdict']=='SINGLE' and single['confidence']>=.65


def evidence(n=5, *, inp=2000, out=1500, ms=3000):
    return validate_latency_evidence({'observations':[{'input_tokens':inp,'output_tokens':out,'latency_ms':ms+i*100} for i in range(n)],'snapshot_id':'a'*64})


def test_request_size_matches_and_sparse_or_wrong_size_retains_prior():
    matched=forecast_latency(evidence(),2500,2048,60000)
    assert matched['prediction_ms']==3400 and matched['samples']==5
    assert not matched['calibrated_sla']
    assert forecast_latency(evidence(4),2500,2048,60000)['prediction_ms']==60000
    assert forecast_latency(evidence(),60000,2048,60000)['samples']==0
    assert forecast_latency(evidence(out=30),2500,2048,60000)['prediction_ms']==60000
    assert forecast_latency(evidence(ms=70000),2500,2048,60000)['prediction_ms']==70400


def test_time_rejection_has_numeric_evidence_and_native_parallel_schedule():
    plan=validate_plan({'nodes':[{'node_id':'a','node_type':'generation','prompt_template':'A','parents':[]},
        {'node_id':'b','node_type':'generation','prompt_template':'B','parents':[]},
        {'node_id':'final','node_type':'generation','prompt_template':'汇总','parents':['a','b']}],
        'final_node_id':'final','acceptance_criteria':['完整']})
    profile=(NodeProfile('m','generation',90,.01,60000,0),)
    kwargs=dict(method='A',quality_min=80,cost_max=1,latency_max_ms=150000)
    serial=route_nodes(plan,profile,execution_policy=ExecutionPolicy(max_concurrency=1),**kwargs)
    assert serial['status']=='no-feasible-route'
    d=serial['diagnostics'];assert d['rejected_combinations']['latency']==1
    assert d['minimum_scheduled_latency_ms']==180000 and d['remaining_latency_ms']==150000
    parallel=route_nodes(plan,profile,execution_policy=ExecutionPolicy(max_concurrency=2),**kwargs)
    assert parallel['status']=='selected' and parallel['prediction']['scheduled_latency_ms']==120000
    noquality=route_nodes(plan,(replace(profile[0],quality=50),),**kwargs)
    assert noquality['diagnostics']['rejected_combinations']['quality']==1


def test_latency_profiles_exclude_planning_review_and_failed_truncation(tmp_path):
    from refractrouter.route_observations import RouteObservationStore
    from tests.test_route_observations import call, binding
    store=RouteObservationStore(tmp_path/'latency.sqlite3')
    store.record_run('one',[call('planner',90000),call('final-judge',50000),
        call('node',2000),call('cut',3000,finish='length')],binding())
    profile=store.latency_profiles()['cloud/same-name\0Model-v1\0default']
    assert profile['observations']==[{'input_tokens':100,'output_tokens':20,'latency_ms':2000}]


def test_configured_profile_propagates_size_matched_latency_without_lowering_cost():
    from tests.test_automatic_actual_catalog import fixture
    from refractrouter.dsh_model_pool import compile_dsh_model_pool
    from refractrouter.application_config import compile_configuration
    from refractrouter.configured_routing import configured_profile
    from tests.test_automatic_routing import parallel_plan
    pool,catalog=fixture('deepseek-official','deepseek-flash','CNY')
    catalog['routes'][0]['maxOutputTokens']=2048
    config,_=compile_dsh_model_pool(pool,catalog)
    target=config['models'][0];target['routing']['latencyEvidence']=evidence(inp=50000,out=1500)
    compiled=compile_configuration(config)
    result=configured_profile(compiled,compiled.manifest,parallel_plan(),input_forecasts={'facts':50000,'risks':50000,'answer':50000})
    rows=result['candidates'];assert all(r['latency_ms']==3400 for r in rows)
    assert all(r['cost']==pytest.approx(50*.002+2.048*.008) for r in rows)
    assert all(result['forecast_basis'][n][target['id']]['latency']['samples']==5 for n in ('facts','risks','answer'))
