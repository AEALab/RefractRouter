"""六臂冻结、反泄露、评分类型及异构序列化的零付费验收。"""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from refractrouter.heterogeneous_study import (ARMS, MAX_OUTPUT, OfflineTransport, assignments,
    case_spec, compile_study_plan, inputs, models, prepare, score_delivery, select_prompts, validate)
from refractrouter.compact_planning import compile_compact
from refractrouter.openai_compatible import OpenAICompatibleClient
from dataclasses import replace


def delivery(task,ref):
    return {'answer':'正文仍需独立语义复核。','findings':[{'id':key,'value':item['value'],
        'sources':item['support_options'][0]} for key,item in ref['findings'].items()]}


def test_six_arm_matrix_and_total_call_envelope():
    frozen=prepare();validate(frozen)
    assert len(frozen['cases'])==288
    assert sum(c['phase']=='prompt-audit' for c in frozen['cases'])==72
    assert sum(c['phase']=='comparison' for c in frozen['cases'])==216
    assert len(frozen['sharedPlanSetups'])==36
    assert frozen['maxModelCalls']==974
    assert frozen['paidExecutionImplemented'] is False and frozen['paidApproval'] is None
    assert frozen['operationalCapGuaranteesCompletion'] is False
    assert frozen['fullCapacityAfpUpperBound']>frozen['suggestedOperationalAfpCap']
    assert sum(v['maxModelCalls'] for v in frozen['budgetBreakdown'].values())==974
    for arm in ARMS:
        assert sum(c['arm']==arm and c['phase']=='comparison' for c in frozen['cases'])==36


def test_private_reference_and_family_not_sent_to_execution():
    tasks,_=inputs()
    for task in tasks:
        for arm in ARMS:
            case=case_spec(task,arm,1)
            assert set(case['payload'])=={'instruction','materials','requested_findings','semantic_criteria','output_contract'}
            assert case['timeoutMs']==0
            assert 'family' not in case['payload'] and 'split' not in case['payload']
            assert all(m['maxOutputTokens']==MAX_OUTPUT for m in case['planningConfig']['models'])


def test_reference_fixtures_all_pending_and_wrong_values_fail():
    tasks,refs=inputs()
    for task in tasks:
        ref=refs[task['task_id']];obj=delivery(task,ref)
        assert score_delivery(task,ref,json.dumps(obj))['qualityStatus']=='pending'
        obj['findings'][0]['value']='明显错误'
        assert score_delivery(task,ref,json.dumps(obj))['qualityStatus']=='fail'


def test_alternative_source_set_and_boolean_type_are_respected():
    tasks,refs=inputs();task=next(t for t in tasks if t['task_id']=='approval-0');ref=refs[task['task_id']]
    obj=delivery(task,ref)
    next(x for x in obj['findings'] if x['id']=='old_rule_used')['sources']=['s4']
    assert score_delivery(task,ref,json.dumps(obj))['fieldStatus']=='pass'
    next(x for x in obj['findings'] if x['id']=='b_approved')['value']=0
    assert score_delivery(task,ref,json.dumps(obj))['fieldStatus']=='fail'


@pytest.mark.parametrize('change',['duplicate','missing','source','malformed','wrong-body'])
def test_contract_failures_and_body_semantics_are_not_hidden(change):
    tasks,refs=inputs();task=tasks[0];ref=refs[task['task_id']];obj=delivery(task,ref)
    if change=='duplicate':obj['findings'].append(deepcopy(obj['findings'][0]))
    if change=='missing':obj['findings'].pop()
    if change=='source':obj['findings'][0]['sources']=['不存在']
    if change=='wrong-body':obj['answer']='不论证书是否有效，所有供应商都已确认合格。'
    text='{' if change=='malformed' else json.dumps(obj)
    result=score_delivery(task,ref,text)
    assert result['qualityStatus']==('pending' if change=='wrong-body' else 'fail')


def test_same_graph_assignments_change_only_models():
    plan=compile_compact({'reason':'测试同图','nodes':[
        {'id':'extract','type':'extraction','job':'提取','parents':[],'difficulty':'low','risk':'low'},
        {'id':'answer','type':'generation','job':'交付','parents':['extract'],'difficulty':'high','risk':'high'}]})
    before=plan.to_dict()
    assert assignments(plan,False)=={'extract':'L','answer':'L'}
    assert assignments(plan,True)=={'extract':'L','answer':'H'}
    assert plan.to_dict()==before


def test_study_contract_removes_legacy_input_ceiling():
    plan=compile_study_plan({'reason':'研究输入一致性','nodes':[
        {'id':'answer','type':'generation','job':'交付','parents':[],'difficulty':'medium','risk':'medium'}]})
    assert plan.contracts['answer']['capability']['input_budget_tokens']==600000


def test_prompt_selection_is_complete_development_only():
    tasks,_=inputs();rows=[]
    for task in tasks:
        if task['split']!='development':continue
        for model in ('L','H'):
            for prompt in ('contract','verify'):
                for repeat in range(1,4):
                    rows.append({'phase':'prompt-audit','taskId':task['task_id'],'model':model,'promptId':prompt,
                        'repeat':repeat,'fieldStatus':'pass' if prompt=='verify' else 'fail',
                        'failedCheckCount':0 if prompt=='verify' else 1,'chargedAfp':1})
    assert select_prompts(rows)['selected']=={'L':'verify','H':'verify'}
    with pytest.raises(ValueError,match='不完整'):select_prompts(rows[:-1])
    rows.append({**rows[-1],'phase':'comparison'})
    with pytest.raises(ValueError,match='留出'):select_prompts(rows)


@pytest.mark.parametrize('alias',['L','H'])
def test_real_python_serialization_uses_model_full_capacity(tmp_path,monkeypatch,alias):
    monkeypatch.setenv('REFRACT_OFFLINE_KEY','not-a-real-key')
    transport=OfflineTransport(tmp_path/'wire')
    client=OpenAICompatibleClient(transport=transport,max_retries=0,timeout_seconds=None)
    model=replace(models()[alias],api_key_env='REFRACT_OFFLINE_KEY')
    response=client.complete(model,[{'role':'user','content':'只做离线序列化验收'}])
    assert response.content
    assert transport.calls[0]['max_output_tokens']==384000
    assert transport.calls[0]['model']==model.api_model
    assert transport.calls[0]['temperature']==0
