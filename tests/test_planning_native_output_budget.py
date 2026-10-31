"""#223：原生回答、思考和总输出预算的零模型调用反例。"""
from copy import deepcopy
from dataclasses import replace

import pytest

from refractrouter.planning_budget import PlanningBudget
from refractrouter.planning_config import PlanningModel,compile_config
from refractrouter.planning_output_budget import output_contract,reservation_bound
from refractrouter.planning_runtime import PlanningRuntime
from refractrouter.openai_compatible import ChatResponse
from tests.test_planning_routing import (configuration,escalation_configuration,
    advisor_gate_configuration,task_pool_configuration,begin,step)


def model(scope='answer-only',*,context=1_024_000,output=131072,price=.45):
    return PlanningModel('native','fixture',price,price,0,billing_unit='CNY',api_model='native',
        context_window=context,max_output_tokens=output,output_budget={
            'scope':scope,'parameter':'max_tokens','sourceSha256':'a'*64})


def receipt(*,output=250000,reasoning=249000,known=True):
    return ChatResponse('正确的固定夹具',100,output,0,reasoning,1,1,'stop','fixture',
        usage_available=known,raw_usage={'completion_tokens_details':{'reasoning_tokens':reasoning}})


def test_issue_223_reproducer_is_rejected_before_any_dispatch():
    budget=PlanningBudget({'CNY':70})
    with pytest.raises(ValueError,match='budget-exhausted'):
        budget.reserve(model(),[{'role':'user','content':'探针'}],label='原生回答不代表全部输出')
    assert budget.records==[] and budget.remaining('CNY')==70


def test_answer_only_preserves_native_limit_and_covers_reasoning_above_answer_limit():
    configured=model();budget=PlanningBudget({'CNY':1000})
    reserved=budget.reserve(configured,[],label='允许合法思考')
    assert reserved.model.max_output_tokens==131072
    assert reserved.row['wire_output_tokens']==131072
    assert reserved.row['reserved']==pytest.approx(460.8)
    assert reserved.row['reserved_output_tokens']==1_024_000
    budget.dispatch(reserved);budget.settle(reserved,receipt())
    assert reserved.row['charged']==pytest.approx(112.545)
    assert reserved.row['observed_answer_tokens']==1000
    assert reserved.row['observed_reasoning_tokens']==249000
    assert reserved.row['answer_bound_confirmed'] is True
    assert reserved.row['status']=='billed'


def test_explicit_total_output_reserves_native_capacity_above_8192():
    configured=model('answer-and-reasoning-total',output=32768)
    budget=PlanningBudget({'CNY':100});reservation=budget.reserve(configured,[],label='原生总输出')
    assert reservation.row['reserved_output_tokens']==32768
    assert reservation.model.max_output_tokens==32768
    assert reservation.row['reserved']>32768/1000*.45
    budget.dispatch(reservation);budget.settle(reservation,receipt(output=20000,reasoning=19000))
    assert reservation.row['total_output_bound_confirmed'] is True


@pytest.mark.parametrize('scope,output,reasoning',[
    ('answer-only',250000,1),('answer-and-reasoning-total',250000,249000),
    ('answer-only',1_100_000,1_099_000)])
def test_known_usage_outside_native_contract_is_billed_then_stopped(scope,output,reasoning):
    budget=PlanningBudget({'CNY':1000});reservation=budget.reserve(model(scope),[],label='超合同回执')
    budget.dispatch(reservation)
    with pytest.raises(ValueError,match='exceeded conservative budget'):
        budget.settle(reservation,receipt(output=output,reasoning=reasoning))
    assert reservation.row['status']=='billed'
    assert reservation.row['charged']==pytest.approx((100+output)/1000*.45)
    assert budget.ledgers['CNY'].stopped


def test_missing_reasoning_breakdown_does_not_use_placeholder_zero_as_answer_length():
    budget=PlanningBudget({'CNY':1000});reservation=budget.reserve(model(),[],label='缺少细分')
    budget.dispatch(reservation)
    with pytest.raises(ValueError,match='exceeded conservative budget'):
        budget.settle(reservation,replace(receipt(),raw_usage={}))
    assert reservation.row['status']=='billed'
    assert reservation.row['observed_answer_tokens'] is None
    assert reservation.row['answer_bound_confirmed'] is False


def test_legacy_unknown_contract_uses_full_context_and_records_uncertainty():
    budget=PlanningBudget({'CNY':1000});reservation=budget.reserve(replace(model(),output_budget=None),[],label='旧配置')
    native=reservation.row['native_output_budget']
    assert native['scopeVerified'] is False
    assert native['contract']['scope']=='unknown'
    assert reservation.row['reserved']==pytest.approx(460.8)
    assert reservation.model.max_output_tokens==131072


def test_cancel_and_rollback_do_not_release_dispatched_unknown_usage(tmp_path):
    budget=PlanningBudget({'CNY':1000});reservation=budget.reserve(model(),[],label='未知用量')
    budget.dispatch(reservation)
    with pytest.raises(ValueError,match='usage'):
        budget.settle(reservation,receipt(known=False))
    protected=deepcopy(reservation.row);budget.stop()
    assert reservation.row==protected
    assert budget.snapshot()[0]['CNY']['production']==pytest.approx(460.8)


@pytest.mark.parametrize('strategy',['static','stage','task','advisor','escalation','composite'])
def test_all_six_strategies_share_one_cost_and_reservation_calculation(tmp_path,strategy):
    runtime=PlanningRuntime(tmp_path);cfg=configuration(strategy);run=begin(runtime,strategy,config=cfg)
    configured=runtime.runs[run]['config']['models']['small']
    messages=[{'role':'user','content':'零调用校验'}]
    expected=runtime._cost_bound(configured,messages,[],None)
    reserved=runtime.runs[run]['budget'].reserve(configured,messages,label='单一费用口径')
    assert reserved.row['reserved']==expected
    assert reserved.row['wire_output_tokens']==configured.max_output_tokens


@pytest.mark.parametrize('factory',[task_pool_configuration,advisor_gate_configuration,escalation_configuration])
def test_required_judge_and_execution_path_rejects_insufficient_combined_budget(tmp_path,factory):
    cfg=factory();cfg['maxProductionCostByUnit']={'CNY':.1}
    for item in cfg['models']:item['outputBudget']['scope']='answer-only'
    runtime=PlanningRuntime(tmp_path);run=begin(runtime,cfg['defaultStrategy'],config=cfg)
    with pytest.raises(ValueError):step(runtime,run)
    assert runtime.runs[run]['budget'].records==[]


def test_shared_context_uses_expensive_cache_write_rate_and_subscription_reference():
    configured=replace(model(context=10000,output=1000,price=.01),billing_mode='subscription',cache_write_cost_per_1k=2)
    budget=PlanningBudget({'CNY':.001},reference_limit=21)
    reservation=budget.reserve(configured,[],label='订阅缓存费用')
    assert reservation.row['reserved']==20
    assert budget.remaining('CNY')==.001
    assert budget.reference_snapshot()['occupied']==20


def test_source_and_parameter_are_explicit_and_do_not_infer_scope_from_parameter_name():
    with pytest.raises(ValueError,match='来源'):
        output_contract({'scope':'answer-only','parameter':'max_tokens','sourceSha256':None},10000)
    assert output_contract(None,10000)['scope']=='unknown'
    a=model();b=replace(a,output_budget={**a.output_budget,'scope':'answer-and-reasoning-total'})
    assert reservation_bound(a,300)['amount']>reservation_bound(b,300)['amount']
    cfg=configuration();cfg['models'][0]['outputBudget']['sourceSha256']='错误'
    assert 'small' not in compile_config(cfg)['models']


def test_host_native_reasoning_breakdown_survives_runtime_receipt_envelope(tmp_path):
    cfg=configuration('static');cfg.update(billingUnit='CNY',schemaVersion='refractagent-planning-v8',
        maxProductionCostByUnit={'CNY':1000})
    cfg.pop('maxProductionCost')
    raw=cfg['models'][0];raw.update(billingUnit='CNY',contextWindow=1_024_000,maxOutputTokens=131072,
        inputPer1k=.45,outputPer1k=.45,outputBudget={'scope':'answer-only',
            'parameter':'host-maxTokens','sourceSha256':'a'*64})
    runtime=PlanningRuntime(tmp_path);run=begin(runtime,'static',config=cfg);action=step(runtime,run)
    assert action['model']['maxTokens']==131072
    result=runtime.handle({'op':'complete','runId':run,'callId':action['callId'],'response':{
        'content':'宿主原生回执','inputTokens':100,'outputTokens':250000,'reasoningTokens':249000,
        'usageAvailable':True,'finishReason':'stop','rawUsage':{'inputTokens':100,
            'outputTokens':250000,'reasoningTokens':249000}}})
    assert result['action']=='release'
    row=runtime.runs[run]['budget'].records[0]
    assert row['observed_answer_tokens']==1000 and row['observed_reasoning_tokens']==249000


def test_future_review_input_is_protected_before_subscription_reference_reservation():
    configured=replace(model('answer-and-reasoning-total',context=20000,output=1000,price=1),billing_mode='subscription')
    budget=PlanningBudget({'CNY':0},reference_limit=5)
    with pytest.raises(ValueError,match='reference-CNY'):
        budget.reserve(configured,[],label='未来复审',future_input_bound=6000)
    assert budget.records==[] and budget.reference_snapshot()['occupied']==0


def test_unknown_settlement_stops_all_currency_ledgers_without_releasing_dispatched_reserve():
    budget=PlanningBudget({'CNY':1000,'AFP':1000})
    reserved=budget.reserve(model(),[],label='未知CNY')
    budget.dispatch(reserved)
    with pytest.raises(ValueError):budget.settle(reserved,receipt(known=False))
    assert budget.stopped
    with pytest.raises(ValueError,match='已停止'):
        budget.reserve(replace(model(),billing_unit='AFP'),[],label='禁止后续AFP')
    assert reserved.row['charged']==reserved.row['reserved']==460.8
