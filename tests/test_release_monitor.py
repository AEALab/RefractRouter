"""发布监控复用原账本，不把无标签、未结束或范围不符当作零错误。"""
from copy import deepcopy
import hashlib

import pytest

from refractrouter.release_monitor import monitor,prediction_error
from tests.test_governed_gateway import setup,req,INSTANCES
from tests.test_model_gateway import Caller,reply


@pytest.fixture(autouse=True)
def cleanup():
    yield
    while INSTANCES:INSTANCES.pop().close()


def test_monitoring_preserves_raw_fees_and_unknown_quality_without_model_calls(tmp_path):
    caller=Caller(reply('完成'))
    gateway,store,_,_,_,_=setup(tmp_path,caller)
    request=req();request.pop('metadata')
    gateway.complete(request,scope='alice')
    files=list((tmp_path/'runs').glob('releases/*/planning/*.json'))
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    report=monitor(store)
    assert report['taskCount']==1 and report['completeDelivery']=={'PASS':0,'FAIL':0,'UNKNOWN':1}
    assert report['feeLanes'][0]['unit']=='CNY'
    assert report['tasks'][0]['costObservation']['pricedCallAmountsComplete']
    assert report['tasks'][0]['predictionError']['status']=='unknown'
    assert report['modelCalls']==0 and not report['financialLedgerChanged'] and not report['modelPoolChanged']
    assert all(hashlib.sha256(p.read_bytes()).hexdigest()==before[str(p)] for p in files)
    assert len(caller.actions)==1


def test_monitor_does_not_hide_unknown_reserves_after_rollback(tmp_path):
    caller=Caller(reply('缺用量',usage=False))
    gateway,store,_,_,_,_=setup(tmp_path,Caller(reply('基线')),caller)
    with pytest.raises(ValueError):gateway.complete(req(),scope='alice')
    before=monitor(store)
    store.rollback(actor='维护者',reason='停止未知用量试用')
    after=monitor(store)
    assert before['feeLanes']==after['feeLanes']
    assert float(after['feeLanes'][0]['unknownProtected'])>0
    assert after['tasks'][0]['feeAnomalies']
    assert after['completeDelivery']['UNKNOWN']==1


def test_independent_final_label_must_match_candidate_and_original_feedback_event(tmp_path):
    from refractrouter.task_results import event,scope_for
    from refractrouter.task_outcomes import digest
    caller=Caller(reply('完整答复'))
    gateway,store,_,_,_,_=setup(tmp_path,caller)
    request=req();request.pop('metadata');runs=[]
    gateway.complete(request,scope='alice',on_outcome=runs.append)
    view=gateway.outcome({'runId':runs[0]},scope='alice');candidate=view['candidates'][-1]
    label={'candidateId':candidate['candidateId'],'candidateSha256':candidate['candidateSha256'],
        'criteriaSha256':'a'*64,'scope':'complete-delivery-and-requirements','independent':True,
        'verdict':'PASS','method':'human-decision','recordSha256':'b'*64}
    annotations={runs[0]:{'criteriaSha256':'a'*64,'annotations':[label],'upgradeAssessments':[]}}
    missing=monitor(store,annotations)
    assert missing['completeDelivery']['UNKNOWN']==1
    assert missing['tasks'][0]['labelBindingValid'] is False
    inner=next(iter(gateway.gateways.values()));record=inner.runtime.runs[runs[0]]
    inner.runtime.task_results.journal.append(scope_for(record),runs[0],event('offline-label','feedback',
        candidate=(candidate['candidateId'],candidate['candidateSha256']),source='hidden-evaluation',actor='offline',
        status='accepted',criteria='a'*64,artifacts=[digest(label)]))
    checked=monitor(store,annotations)
    assert checked['completeDelivery']['PASS']==1
    assert checked['tasks'][0]['transportDelivery']=='unknown'
    assert len(caller.actions)==1


def test_full_cost_prediction_error_needs_actual_candidate_same_unit_and_complete_flow():
    view={'costContext':{'冻结上下文':'用于此算术测试'},'calls':[{'call_id':'a','purpose':'execute',
        'host_request_id':'one-flow','model_id':'small'}],
        'taskShadow':{'costBasis':'empirical-full-managed-task','corpusKind':'empirical','actualCandidateId':'small',
            'rows':[{'modelId':'small','estimate':{'mean':2,'dimension':['metered-budget','CNY'],
                'includesAllManagedCalls':True}}]}}
    costs={'pricedCallAmountsComplete':True,'cacheUsageComplete':True,'referenceCostCny':None,
        'costs':[{'lane':'metered-budget','unit':'CNY','knownCalculated':'3','unknownProtected':'0'}]}
    result=prediction_error(view,costs)
    assert result['signedError']=='1' and result['absoluteError']=='1'
    wrong=deepcopy(view);wrong['taskShadow']['actualCandidateId']='another'
    assert prediction_error(wrong,costs)['status']=='unknown'
    wrong=deepcopy(view);wrong['taskShadow']['predictionStale']=True
    assert prediction_error(wrong,costs)['status']=='unknown'
    missing=deepcopy(costs);missing['pricedCallAmountsComplete']=False
    assert prediction_error(view,missing)['status']=='unknown'


def test_missing_original_unknown_reservation_cannot_be_reported_as_zero(tmp_path):
    caller=Caller(reply('已知费用'),reply('未知费用',usage=False))
    gateway,store,_,_,_,_=setup(tmp_path,caller)
    gateway.complete(req('known'),scope='alice');unknown=[]
    with pytest.raises(ValueError):gateway.complete(req('unknown'),scope='alice',on_outcome=unknown.append)
    assert float(monitor(store)['feeLanes'][0]['unknownProtected'])>0
    record=next((tmp_path/'runs').glob('releases/*/planning/'+unknown[0]+'.json'));record.unlink()
    result=monitor(store)
    assert result['feeSummaryComplete'] is False
    assert result['feeLanes'][0]['unknownProtected'] is None
    assert result['feeLanes'][0]['knownCalculated'] is None
    assert float(result['feeLanes'][0]['readableKnownCalculated'])>0


def test_earlier_pass_is_not_complete_delivery_after_later_tool_candidate(tmp_path):
    from refractrouter.task_results import event,scope_for
    from refractrouter.task_outcomes import digest
    from tests.test_model_gateway import call
    caller=Caller(reply('较早正文'),reply('随后工具',calls=[call()]))
    gateway,store,_,_,_,_=setup(tmp_path,caller);runs=[]
    gateway.complete(req(),scope='alice',on_outcome=runs.append)
    view=gateway.outcome({'runId':runs[0]},scope='alice');candidate=view['candidates'][-1]
    label={'candidateId':candidate['candidateId'],'candidateSha256':candidate['candidateSha256'],
        'criteriaSha256':'a'*64,'scope':'complete-delivery-and-requirements','independent':True,
        'verdict':'PASS','method':'human-decision','recordSha256':'b'*64}
    inner=next(iter(gateway.gateways.values()));record=inner.runtime.runs[runs[0]]
    inner.runtime.task_results.journal.append(scope_for(record),runs[0],event('offline-label','feedback',
        candidate=(candidate['candidateId'],candidate['candidateSha256']),source='hidden-evaluation',actor='offline',
        status='accepted',criteria='a'*64,artifacts=[digest(label)]))
    request=req(tools=True);request['messages'][0]['content']='接着调用工具'
    gateway.complete(request,scope='alice')
    inner.runtime.handle({'op':'end','runId':runs[0]})
    report=monitor(store,{runs[0]:{'criteriaSha256':'a'*64,'annotations':[label],'upgradeAssessments':[]}})
    assert report['completeDelivery']=={'PASS':0,'FAIL':0,'UNKNOWN':1}
