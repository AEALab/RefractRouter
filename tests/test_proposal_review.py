"""审核不能用高分覆盖关键约束失败；不调用真实模型。"""
import json
from pathlib import Path
import time
import pytest
from refractrouter.task_evaluation import evaluation_messages, evaluate_text, PROPOSAL_CRITERION, REVIEW_CONTRACT
from refractrouter.openai_compatible import ChatResponse


def test_proposal_check_is_explicit_and_not_duplicated():
    criteria=['事实正确']
    p=json.loads(evaluation_messages('任务','答案',criteria)[1]['content'])
    assert p['criteria']==criteria+[PROPOSAL_CRITERION]
    assert criteria==['事实正确']
    twice=json.loads(evaluation_messages('任务','答案',p['criteria'])[1]['content'])
    assert twice['criteria']==p['criteria']
    assert p['review_contract']==REVIEW_CONTRACT


@pytest.mark.parametrize('overall,proposal,missing,raises',[(True,False,False,True),
    (False,False,False,False),(True,True,True,True),(True,True,False,False)])
def test_high_score_cannot_hide_failed_or_omitted_constraint(overall,proposal,missing,raises):
    class Budget:
        def complete(self, model, messages, **kwargs):
            p=json.loads(messages[-1]['content'])
            rows=[{'criterion':c,'passed':proposal if c==PROPOSAL_CRITERION else True,'rationale':'模拟证据'} for c in p['criteria']]
            if missing:rows.pop()
            return ChatResponse(json.dumps({'score':99,'passed':overall,'rationale':'模拟','criteria':rows}),100,80,0,0,1,1,'stop','mock')
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
@pytest.mark.parametrize('grounding', [False, True])
def test_finite_review_runner_uses_frozen_count_or_stops_unknown(tmp_path, monkeypatch, unknown, grounding):
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
    monkeypatch.setattr(runner,'hashes',lambda:{})
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
            if unknown:raise TimeoutError('mock')
            result={'score':95,'passed':True,'rationale':'模拟批准',
                'criteria':[{'criterion':c,'passed':True,'rationale':'模拟'} for c in p['criteria']]}
            return ChatResponse(json.dumps(result),100,80,0,0,1,1,'stop','mock')
    monkeypatch.setattr(runner.subprocess,'Popen',Process)
    monkeypatch.setattr(runner,'OpenAICompatibleClient',Client)
    frozen=runner.freeze(catalog,grounding_cases=grounding)
    count=2 if grounding else 4
    assert frozen['maximumCalls']==count
    if unknown:
        with pytest.raises(TimeoutError):runner.run(frozen,tmp_path/'run')
    else:
        rows=runner.run(frozen,tmp_path/'run');assert len(rows)==count
        assert sum(r['matched'] for r in rows)==count//2  # 错误模型不能被预期标签伪造成通过。
    ledger=json.loads((tmp_path/'run/result.json').read_text())
    assert len(ledger['calls'])==(1 if unknown else count)
    assert ledger['calls'][0]['status']==('unknown-usage' if unknown else 'billed')


@pytest.mark.parametrize('ids,valid', [(['c1','c2'],True),(['c2','c1'],False),
    (['c1','c1'],False),(['c1','unknown'],False)])
def test_review_ids_preserve_order_and_reject_missing_or_forged_coverage(ids,valid):
    class Budget:
        def complete(self, model, messages, **kwargs):
            payload=json.loads(messages[-1]['content'])
            assert payload['criterion_ids']==['c1','c2']
            rows=[{'criterion_id':i,'passed':True,'rationale':'已核对'} for i in ids]
            return ChatResponse(json.dumps({'score':95,'passed':True,'rationale':'已核对','criteria':rows}),100,80,0,0,1,1,'stop','mock')
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
