"""审核不能用高分覆盖关键约束失败；不调用真实模型。"""
import json
from pathlib import Path
import time
import pytest
from refractrouter.task_evaluation import evaluation_messages, evaluate_text, PROPOSAL_CRITERION, REVIEW_CONTRACT
from refractrouter.openai_compatible import ChatResponse
from tests.review_fixtures import mock_grounding_checks


def test_proposal_check_is_explicit_and_not_duplicated():
    criteria=['事实正确']
    p=json.loads(evaluation_messages('任务','答案',criteria)[1]['content'])
    assert p['criteria']==criteria+[PROPOSAL_CRITERION]
    assert criteria==['事实正确']
    twice=json.loads(evaluation_messages('任务','答案',p['criteria'])[1]['content'])
    assert twice['criteria']==p['criteria']
    assert p['review_contract']==REVIEW_CONTRACT


def test_each_grounding_item_has_an_explicit_output_shape():
    from refractrouter.task_evaluation import GROUNDING_FIELDS, CLAIM_KINDS
    p=json.loads(evaluation_messages('材料未提供测试状态','系统未经测试。仅说明我未执行测试。',[])[1]['content'])
    assert [row['check_id'] for row in p['grounding_check_shapes']]==p['grounding_check_ids']
    for i,row in enumerate(p['grounding_check_shapes']):
        assert row['required_fields']==[*GROUNDING_FIELDS,*(['claim_kind'] if i>=2 else [])]
        if i>=2:assert row['claim_kind_values']==list(CLAIM_KINDS)
    node=json.loads(evaluation_messages('任务','节点答案',[],node_input='节点输入')[1]['content'])
    assert 'grounding_check_shapes' not in node


@pytest.mark.parametrize('overall,proposal,missing,raises',[(True,False,False,True),
    (False,False,False,False),(True,True,True,True),(True,True,False,False)])
def test_high_score_cannot_hide_failed_or_omitted_constraint(overall,proposal,missing,raises):
    class Budget:
        def complete(self, model, messages, **kwargs):
            p=json.loads(messages[-1]['content'])
            rows=[{'criterion':c,'passed':proposal if c==PROPOSAL_CRITERION else True,'rationale':'模拟证据'} for c in p['criteria']]
            if missing:rows.pop()
            return ChatResponse(json.dumps({'score':99,'passed':overall,'rationale':'模拟','criteria':rows,
                'grounding_checks':mock_grounding_checks(p)}),100,80,0,0,1,1,'stop','mock')
    def run():return evaluate_text(Budget(),None,'任务','答案',criteria=['事实正确'],label='review',deadline=time.monotonic()+10)
    if raises:
        with pytest.raises(ValueError):run()
    else:
        result=run();assert result['passed']==overall and result['review_contract']==REVIEW_CONTRACT


def test_fixed_cases_preserve_numeric_answers_and_separate_labels():
    from hashlib import sha256
    fixture=json.loads(Path('data/research/proposal-constraint-recheck-v1.json').read_text())
    cases=fixture['cases'];assert [c['expectedPassed'] for c in cases]==[False,True,False,True]
    answers=[json.loads(c['answer'])['answers'] for c in cases]
    assert all(a==answers[0] for a in answers)
    for case in cases:
        assert sha256(case['answer'].encode()).hexdigest()==case['answerSha256']
        payload=json.loads(evaluation_messages(fixture['task'],case['answer'],fixture['criteria'])[1]['content'])
        assert 'expectedPassed' not in payload and 'basis' not in payload
    assert cases[0]['answerSha256']==fixture['originalCandidateSha256']


@pytest.mark.parametrize('unknown', [False, True])
@pytest.mark.parametrize('case_set', ['proposal','grounding','native'])
def test_finite_review_runner_uses_frozen_count_or_stops_unknown(tmp_path, monkeypatch, unknown, case_set):
    import io
    import experiments.run_proposal_review_recheck as runner
    from tests.test_live_execution import config
    raw=config();raw['billingUnit']='CNY'
    raw['providers'].append({'id':'paid-judge','type':'openai-compatible','baseUrl':'https://judge.example/v1','deployment':'trusted-cloud','trustPolicy':'mock'})
    raw['trustPolicies']=[{'id':'mock','residency':'CN','auditLogging':True,'allowsSensitiveData':True}]
    next(m for m in raw['models'] if 'judge' in m['roles'])['provider']='paid-judge'
    for model in raw['models']:
        model['pricing'].update(unit='CNY',inputPer1k=.001,outputPer1k=.002)
    catalog={'pool':{},'routes':[]}
    monkeypatch.setattr(runner,'compile_dsh_model_pool',lambda *args:(raw,{}))
    monkeypatch.setattr(runner,'hashes',lambda *args:{})
    monkeypatch.setattr(runner,'historical_protection',lambda roots:{'cashProtectedCny':.5})
    class Process:
        def __init__(self,*args,**kwargs):
            self.stdin=io.StringIO();self.stdout=io.StringIO(json.dumps(catalog)+'\n')
        def wait(self,**kwargs):return 0
    class Client:
        def __init__(self,**kwargs):
            assert kwargs['max_retries']==0
            assert kwargs['timeout_seconds']==180
        def for_task_call(self, seconds):
            assert 175 < seconds <= 180
            return self
        def complete(self,model,messages,**kwargs):
            p=json.loads(messages[-1]['content']);assert 'expectedPassed' not in p
            if case_set=='native':assert p['tool_evidence']=={'records':[],'available':True}
            if unknown:raise TimeoutError('mock')
            result={'score':95,'passed':True,'rationale':'模拟批准',
                'criteria':[{'criterion':c,'passed':True,'rationale':'模拟'} for c in p['criteria']],
                'grounding_checks':mock_grounding_checks(p)}
            return ChatResponse(json.dumps(result),100,80,0,0,1,1,'stop','mock')
    monkeypatch.setattr(runner.subprocess,'Popen',Process)
    monkeypatch.setattr(runner,'OpenAICompatibleClient',Client)
    native_file=None
    if case_set=='native':
        fixture=json.loads(runner.GROUNDING_CASES.read_text())
        fixture.update(schemaVersion='automatic-grounding-native-recheck-v1',baselineInputSha256='a'*64,
            toolEvidence={'records':[],'available':True})
        native_file=tmp_path/'cases.json';native_file.write_text(json.dumps(fixture))
        monkeypatch.setattr(runner,'ROOT',tmp_path)
    frozen=runner.freeze(catalog,grounding_cases=case_set=='grounding',native_case_file=native_file)
    count=4 if case_set=='proposal' else 2
    assert frozen['maximumCalls']==count
    if unknown:
        with pytest.raises(TimeoutError):runner.run(frozen,tmp_path/'run')
    else:
        rows=runner.run(frozen,tmp_path/'run');assert len(rows)==count
        assert sum(r['matched'] for r in rows)==count//2  # 错误模型不能被预期标签伪造成通过。
    ledger=json.loads((tmp_path/'run/result.json').read_text())
    assert len(ledger['calls'])==(1 if unknown else count)
    assert ledger['calls'][0]['status']==('unknown-usage' if unknown else 'billed')
    with pytest.raises(ValueError,match='冻结预检内容被修改'):
        runner.run({**frozen,'maximumCalls':100},tmp_path/'tampered')
    assert not (tmp_path/'tampered').exists()


@pytest.mark.parametrize('ids,valid', [(['c1','c2'],True),(['c2','c1'],False),
    (['c1','c1'],False),(['c1','unknown'],False)])
def test_review_ids_preserve_order_and_reject_missing_or_forged_coverage(ids,valid):
    class Budget:
        def complete(self, model, messages, **kwargs):
            payload=json.loads(messages[-1]['content'])
            assert payload['criterion_ids']==['c1','c2']
            rows=[{'criterion_id':i,'passed':True,'rationale':'已核对'} for i in ids]
            return ChatResponse(json.dumps({'score':95,'passed':True,'rationale':'已核对','criteria':rows,
                'grounding_checks':mock_grounding_checks(payload)}),100,80,0,0,1,1,'stop','mock')
    def run():return evaluate_text(Budget(),None,'任务','答案',criteria=['完整性'],label='test',deadline=time.monotonic()+5)
    if valid:
        assert [r['criterion'] for r in run()['criteria']]==['完整性',PROPOSAL_CRITERION]
    else:
        with pytest.raises(ValueError,match='criterion id'):run()


def test_longer_review_window_preserves_frozen_cases():
    from experiments.run_proposal_review_recheck import CASES
    old=json.loads(Path('data/research/proposal-constraint-recheck-v1.json').read_text())
    current=json.loads(CASES.read_text())
    assert old.pop('timeoutMs')==60000
    assert current.pop('timeoutMs')==180000
    assert old.pop('schemaVersion')=='proposal-constraint-recheck-v1'
    assert current.pop('schemaVersion')=='proposal-constraint-recheck-v2'
    assert old==current


def grounding_response(task, answer, *, passed=False, status='FAIL'):
    p=json.loads(evaluation_messages(task,answer,['材料准确'])[1]['content'])
    return {'score':99,'passed':passed,'rationale':'来源核对优先于总分',
        'criteria':[{'criterion_id':key,'passed':True,'rationale':'模拟覆盖'} for key in p['criterion_ids']],
        'grounding_checks':[
            {'check_id':'source-state','status':status,'answer_quote':'未经实测','source_quote':None,
             'rationale':'材料未说明历史验证情况，不能断言未验证'},
            {'check_id':'time-causality','status':'NOT_APPLICABLE','answer_quote':None,'source_quote':None,
             'rationale':'此候选没有时间关系'},
            *[{'check_id':r['check_id'],'status':status,'answer_quote':r['quote'],
               'claim_kind':'FACT','source_quote':None,'rationale':'逐句覆盖合成回执'}
              for r in p['source_state_claims']]]}


def review_with_response(response, *, task='回滚需保留证据', answer='回滚未经实测', tool_evidence=None):
    class Budget:
        calls=0
        def complete(self,*args,**kwargs):
            self.calls+=1
            return ChatResponse(json.dumps(response),100,80,0,0,1,1,'stop','mock')
    budget=Budget()
    result=evaluate_text(budget,None,task,answer,criteria=['材料准确'],label='test',
        deadline=time.monotonic()+10,tool_evidence=tool_evidence)
    assert budget.calls==1  # 核对项不能引入二次 Judge 或修复调用。
    return result


@pytest.mark.parametrize('status', ['FAIL','UNCERTAIN'])
def test_grounding_failure_or_uncertainty_cannot_be_overridden_by_99_score(status):
    response=grounding_response('回滚需保留证据','回滚未经实测',status=status)
    assert review_with_response(response)['passed'] is False
    response['passed']=True
    with pytest.raises(ValueError,match='inconsistent final judge grounding'):
        review_with_response(response)


@pytest.mark.parametrize('change', ['missing','duplicate','forged-id','invented-answer','invented-source','candidate-as-source','inapplicable-quote'])
def test_grounding_contract_rejects_missing_checks_or_fabricated_citations(change):
    response=grounding_response('回滚需保留证据','回滚未经实测')
    rows=response['grounding_checks']
    if change=='missing':response.pop('grounding_checks')
    elif change=='duplicate':rows[1]=rows[0].copy()
    elif change=='forged-id':rows[0]['check_id']='all-good'
    elif change=='invented-answer':rows[0]['answer_quote']='根本没出现的候选句'
    elif change=='invented-source':rows[0]['source_quote']='提供了验证结果'
    elif change=='candidate-as-source':rows[0]['source_quote']='回滚未经实测'
    else:rows[1]['answer_quote']='未经实测'
    with pytest.raises(ValueError,match='grounding'):
        review_with_response(response)


def test_grounding_source_can_quote_actual_structured_tool_evidence():
    response=grounding_response('回滚需保留证据','回滚未经实测',passed=True,status='PASS')
    response['grounding_checks'][0]['source_quote']='检查结果：回滚未经实测'
    for row in response['grounding_checks'][2:]:row['source_quote']='检查结果：回滚未经实测'
    evidence={'records':[{'result':'检查结果：回滚未经实测'}]}
    assert review_with_response(response,tool_evidence=evidence)['passed'] is True
    with pytest.raises(ValueError,match='task evidence'):
        review_with_response(response)


def test_corrected_claims_are_not_rejected_by_a_keyword_filter():
    answer='如果未经实测，应先核对；材料没有说明是否测试，不能认定未测试。'
    response=grounding_response('回滚需保留证据',answer,passed=True,status='PASS')
    response['grounding_checks'][0].update(answer_quote=answer,source_quote='回滚需保留证据',
        rationale='明确条件与材料信息缺口，不断言实际验证不存在')
    for row in response['grounding_checks'][2:]:row['claim_kind']='CONDITIONAL'
    assert review_with_response(response,answer=answer)['passed'] is True


def test_state_attention_covers_disclaimer_and_table_claim_separately_without_labels():
    from refractrouter.review_claims import state_claims
    answer='我未执行测试。\n| 回滚 | 未经验证（未执行测试） | 若未经验证，应核对 |'
    rows=state_claims(answer)
    assert [r['quote'] for r in rows]==['我未执行测试','未经验证（未执行测试）','若未经验证，应核对']
    assert all(set(r)=={'check_id','quote'} for r in rows)
    assert all(r['quote'] in answer for r in rows)
    payload=json.loads(evaluation_messages('任务',answer,['完整性'])[1]['content'])
    assert payload['grounding_check_ids']==['source-state','time-causality',*(r['check_id'] for r in rows)]


@pytest.mark.parametrize('change', ['missing-claim','rewritten-quote','factual-pass-no-source','unknown-kind','not-applicable','summary-hides-failure'])
def test_every_selected_claim_requires_an_independent_consistent_result(change):
    response=grounding_response('回滚需保留证据','回滚未经实测')
    rows=response['grounding_checks']
    if change=='missing-claim':rows.pop()
    elif change=='rewritten-quote':rows[2]['answer_quote']='未经实测'
    elif change=='factual-pass-no-source':rows[2]['status']='PASS'
    elif change=='unknown-kind':rows[2]['claim_kind']='probably-good'
    elif change=='not-applicable':rows[2]['status']='NOT_APPLICABLE'
    else:rows[0]['status']='PASS'
    with pytest.raises(ValueError,match='grounding|claim|coverage'):
        review_with_response(response)


def test_english_conditional_warning_and_negative_claims_remain_separate():
    from refractrouter.review_claims import state_claims
    answer='If unverified, verify it first.\nRollback has not been tested.\nThis report says it is untested.'
    rows=state_claims(answer)
    assert len(rows)==3  # 覆盖提示不枚举所有表达；无命中不等于没有状态断言。
    assert rows[0]['quote'].startswith('If unverified')
    assert rows[1]['quote'].endswith('not been tested.')
    assert rows[2]['quote'].endswith('untested.')


@pytest.mark.parametrize('answer', ['未经验证'+('x'*1001),'\n'.join(['未经验证']*129)])
def test_attention_capacity_stops_without_truncating_or_calling_judge(answer):
    with pytest.raises(ValueError,match='review-source-claim-'):
        evaluation_messages('任务',answer,['完整性'])
