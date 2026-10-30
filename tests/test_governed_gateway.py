"""治理入口复用真实路由核心；上游是内存回执，不调用模型。"""
from copy import deepcopy
from dataclasses import replace

import pytest

from refractrouter.governed_gateway import GovernedGateway,CONFIG,ALIAS
from refractrouter.release_governance import ReleaseStore,frozen_release
from tests.test_release_governance import release,evidence,expires,CORE
from tests.test_model_gateway import Caller,reply,call,TOOLS,follow

INSTANCES=[]


@pytest.fixture(autouse=True)
def close_services():
    yield
    while INSTANCES:INSTANCES.pop().close()


def snapshot(label):
    value=release(label=label)
    config=deepcopy(value['configuration'])
    for model in config['planningRouting']['models']:
        model['capabilities']={'toolCalling':'verified','requestFeatures':{
            name:'verified' for name in ('jsonObject','jsonSchema','strictTools','toolChoice','parallelToolCalls','promptCacheKey')}}
    config['planningRouting']['schemaVersion']='refractagent-planning-v8'
    config['planningRouting'].update(billingUnit='CNY',maxProductionCostByUnit={'CNY':10})
    for model in config['planningRouting']['models']:model['billingUnit']='CNY'
    return frozen_release(config,value['versions'],implementation=CORE)


def setup(tmp_path, old_caller, new_caller=None, *, identity_known=True):
    old,new=snapshot('old'),snapshot('new')
    root=tmp_path/'registry';store=ReleaseStore.create(root,old,actor='测试维护者',implementation=CORE)
    callers={old['releaseSha256']:old_caller}
    if new_caller is not None:
        store.add(new,evidence(new),actor='测试维护者')
        store.start_trial(new['releaseSha256'],max_tasks=1,expires=expires(),actor='测试维护者',explicit=True)
        callers[new['releaseSha256']]=new_caller
    config={'schemaVersion':CONFIG,'releaseRegistry':str(root)}
    def factory(value):
        delegate=callers[value['releaseSha256']]
        def caller(action,options):
            response=delegate(action,options)
            if not identity_known:return response
            return replace(response,actual_model=response.actual_model or value['versions']['models'][action['model']['id']],
                provider_revision=response.provider_revision or value['versions']['providers'][action['model']['provider']])
        return caller
    gateway=GovernedGateway(config,tmp_path/'runs',caller_factory=factory,implementation=CORE)
    INSTANCES.append(gateway)
    return gateway,store,old,new,config,callers


def req(task='one', *, tools=False):
    return {'model':ALIAS,'messages':[{'role':'user','content':'请核对资料并回答。'}],
        'metadata':{'refract_session':'session','refract_task':task},**({'tools':TOOLS} if tools else {})}


def test_discovery_and_preflight_have_no_model_calls(tmp_path):
    caller=Caller(reply('完成'))
    gateway,store,_,_,_,_=setup(tmp_path,caller)
    assert gateway.models()['data'][0]['id']==ALIAS
    assert gateway.service_info()['modelCalls']==0
    assert caller.actions==[] and store.history()['assignments']==[]
    with pytest.raises(ValueError,match='refract/release'):gateway.complete({**req(),'model':'refract/composite'})


def test_pending_baseline_is_not_advertised_as_ready_and_keeps_history(tmp_path):
    caller=Caller(reply('完成'))
    gateway,store,old,_,_,_=setup(tmp_path,caller)
    runs=[];gateway.complete(req(),scope='alice',on_outcome=runs.append)
    store.invalidate(old['releaseSha256'],actor='维护者',reason='版本待复核')
    assert gateway.service_info()['status']=='not-ready'
    assert gateway.models()['data']==[]
    assert gateway.outcome({'runId':runs[0]},scope='alice')['calls']
    assert len(caller.actions)==1


def test_finite_trial_rollback_pins_tool_continuation_and_new_task_uses_baseline(tmp_path):
    old_caller=Caller(reply('基线答复'))
    new_caller=Caller(reply('先读取',calls=[call()]),reply('原版本继续完成'))
    gateway,store,old,new,_,_=setup(tmp_path,old_caller,new_caller)
    request=req(tools=True)
    first=gateway.complete(request,scope='alice')
    assert first['model']==ALIAS
    store.rollback(actor='维护者',reason='停止试用')
    continuation=follow(request,first)
    second=gateway.complete(continuation,scope='alice')
    assert second['choices'][0]['message']['content']=='原版本继续完成'
    assert len(new_caller.actions)==2 and not old_caller.actions
    third=gateway.complete(req('second'),scope='alice')
    assert third['choices'][0]['message']['content']=='基线答复'
    assert len(old_caller.actions)==1
    history=store.history()
    assert history['trials'][0]['used']==1
    assert history['assignments'][0]['release_id']==new['releaseSha256']
    assert history['assignments'][1]['release_id']==old['releaseSha256']


def test_restart_keeps_trial_count_and_cannot_redispatch_existing_evidence(tmp_path):
    caller=Caller(reply('已完成'))
    gateway,store,old,new,config,callers=setup(tmp_path,Caller(reply('基线')),caller)
    gateway.complete(req(),scope='alice')
    gateway.close()
    restarted=GovernedGateway(config,tmp_path/'runs',caller_factory=lambda value:callers[value['releaseSha256']],implementation=CORE)
    INSTANCES.append(restarted)
    with pytest.raises(ValueError,match='不得自动重新派发'):restarted.complete(req(),scope='alice')
    assert len(caller.actions)==1
    assert store.history()['trials'][0]['used']==1


def test_unknown_usage_and_rollback_do_not_release_original_reservation(tmp_path):
    caller=Caller(reply('有内容但没有用量',usage=False))
    gateway,store,_,_,_,_=setup(tmp_path,Caller(reply('基线')),caller)
    outcomes=[]
    with pytest.raises(ValueError,match='reservation retained'):
        gateway.complete(req(),scope='alice',on_outcome=outcomes.append)
    before=gateway.outcome({'runId':outcomes[0]},scope='alice')
    store.rollback(actor='维护者',reason='未知用量停试用')
    after=gateway.outcome({'runId':outcomes[0]},scope='alice')
    assert before['calls']==after['calls']
    assert len(caller.actions)==1
    assert any(c['status']=='unknown-usage' for c in after['calls'])
    with pytest.raises(ValueError,match='访问域'):
        gateway.outcome({'runId':outcomes[0]},scope='bob')


def test_identical_request_cannot_charge_again_even_with_stream_flag_changed(tmp_path):
    caller=Caller(reply('一次完成'),reply('不得调用第二次'))
    gateway,store,_,_,_,_=setup(tmp_path,caller)
    gateway.complete(req(),scope='alice')
    with pytest.raises(ValueError,match='不得自动重新派发'):
        gateway.complete({**req(),'stream':True},scope='alice')
    assert len(caller.actions)==1


def test_anonymous_prefix_still_checked_and_final_reply_finishes_task(tmp_path):
    caller=Caller(reply('先读取',calls=[call()]),reply('完成'))
    gateway,_,_,_,_,_=setup(tmp_path,caller)
    request=req(tools=True);request.pop('metadata')
    initial=gateway.complete(request,scope='alice')
    continuation=follow(request,initial)
    changed=deepcopy(continuation);changed['messages'][0]['content']='被篡改的历史'
    with pytest.raises(ValueError,match='历史'):gateway.complete(changed,scope='alice')
    assert len(caller.actions)==1
    outcomes=[]
    gateway.complete(continuation,scope='alice',on_outcome=outcomes.append)
    result=gateway.outcome({'runId':outcomes[0]},scope='alice')
    assert result['status']=='completed'
    gateway.outcome({'runId':outcomes[0],'operation':'outcome-delete','expectedHead':result['eventHead']},scope='alice')


def test_second_dispatcher_and_empty_execution_root_cannot_replay(tmp_path):
    caller=Caller(reply('未知',usage=False))
    gateway,_,_,_,config,callers=setup(tmp_path,caller)
    with pytest.raises(ValueError,match='第二个派发者'):
        GovernedGateway(config,tmp_path/'runs',caller_factory=lambda value:caller,implementation=CORE)
    with pytest.raises(ValueError):gateway.complete(req(),scope='alice')
    gateway.close()
    with pytest.raises(ValueError,match='目录'):
        GovernedGateway(config,tmp_path/'empty-runs',caller_factory=lambda value:caller,implementation=CORE)
    restarted=GovernedGateway(config,tmp_path/'runs',caller_factory=lambda value:caller,implementation=CORE)
    INSTANCES.append(restarted)
    with pytest.raises(ValueError,match='不得自动重新派发'):restarted.complete(req(),scope='alice')
    assert len(caller.actions)==1


@pytest.mark.parametrize('missing', [False,True])
def test_observed_model_drift_or_missing_identity_retains_price_reserve_and_stops_trial(tmp_path,missing):
    response=reply('不可交付的版本') if missing else replace(reply('不可交付的版本'),actual_model='other-version')
    caller=Caller(response)
    gateway,store,_,new,_,_=setup(tmp_path,Caller(reply('基线')),caller,identity_known=not missing)
    outcomes=[]
    with pytest.raises(ValueError,match='price binding unconfirmed'):
        gateway.complete(req(),scope='alice',on_outcome=outcomes.append)
    result=gateway.outcome({'runId':outcomes[0]},scope='alice')
    assert result['calls'][0]['status']=='unknown-usage'
    assert result['calls'][0]['charged']==result['calls'][0]['reserved']
    assert result['calls'][0]['price_binding_confirmed'] is False
    assert len(caller.actions)==1
    version=next(v for v in store.history()['versions'] if v['id']==new['releaseSha256'])
    assert version['qualification']=='pending-revalidation'
    assert not store.history()['trials'][0]['active']


def test_unknown_discovered_during_core_settlement_stops_trial(tmp_path,monkeypatch):
    original=snapshot
    def cache_priced(label):
        frozen=original(label);config=deepcopy(frozen['configuration'])
        for model in config['planningRouting']['models']:model['cacheWritePer1k']=.004
        return frozen_release(config,frozen['versions'],implementation=CORE)
    monkeypatch.setattr('tests.test_governed_gateway.snapshot',cache_priced)
    caller=Caller(reply('身份和总用量已知，缓存写入细分未知'))
    gateway,store,_,new,_,_=setup(tmp_path,Caller(reply('基线')),caller)
    store.stop_trial(actor='维护者',reason='扩大构造测试的试用包络')
    store.start_trial(new['releaseSha256'],max_tasks=2,expires=expires(),actor='维护者',explicit=True)
    with pytest.raises(ValueError,match='cache write usage'):
        gateway.complete(req(),scope='alice')
    version=next(v for v in store.history()['versions'] if v['id']==new['releaseSha256'])
    assert version['qualification']=='pending-revalidation'
    assert all(not trial['active'] for trial in store.history()['trials'])
    assert len(caller.actions)==1


def test_history_and_execution_share_one_cache_after_restart(tmp_path):
    from refractrouter.host_evidence import EVIDENCE_VERSION
    gateway,_,old,_,config,_=setup(tmp_path,Caller(reply('旧工具',calls=[call()])))
    gateway.complete(req(tools=True),scope='alice');gateway.close()
    response=replace(reply('新任务'),actual_model='small-v1',provider_revision='fake-provider-v1')
    restarted=GovernedGateway(config,tmp_path/'runs',caller_factory=lambda _:Caller(response),implementation=CORE)
    INSTANCES.append(restarted)
    history=restarted.history_gateway(old['releaseSha256'])
    assert restarted.gateway(old['releaseSha256']) is history
    runs=[];restarted.complete(req('new'),scope='alice',on_outcome=runs.append)
    history.record_host_evidence({'version':EVIDENCE_VERSION,'callId':'call-1','status':'completed',
        'kind':'observe','fingerprint':'a'*64},scope='alice')
    restarted.close()
    final=GovernedGateway(config,tmp_path/'runs',caller_factory=lambda _:Caller(),implementation=CORE)
    INSTANCES.append(final)
    assert final.outcome({'runId':runs[0]},scope='alice')['candidates']
