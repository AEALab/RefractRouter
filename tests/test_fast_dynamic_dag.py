"""快速规划、动态子图与确定性依赖复核；所有模型均为无网络模拟。"""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from threading import Event, Lock
import time

import pytest

from refractrouter.agent import run_agent
from refractrouter.compact_planning import COMPACT_PLANNER_SYSTEM, compile_compact
from refractrouter.dependency_guard import DependencyGuard
from refractrouter.dynamic_decomposition import graft
from refractrouter.openai_compatible import ChatResponse
from refractrouter.task_runtime import validate_request
from tests.test_automatic_dag import config
from tests.test_text_tasks import REQUEST

ROOT = Path(__file__).resolve().parents[1]
EXHIBITION = json.loads((ROOT/'data/research/automatic-dag-acceptance-v3.json').read_text())['tasks'][-1]['task']


def compact(*jobs):
    return {'reason':'独立分析并行，最后汇总。', 'nodes':[
        {'id':nid, 'type':'generation', 'job':nid+' 完成职责', 'parents':parents,
         'difficulty':'medium','risk':'medium'} for nid,parents in jobs]}


class Client:
    max_retries = 0
    def __init__(self, *, failure=None, fail_node='left', subplan=None, plan=None, output='完成职责'):
        self.plan = plan or compact(('left',[]), ('right',[]), ('answer',['left','right']))
        self.subplan = subplan or compact(('facts',[]), ('check',[]), ('merge',['facts','check']))
        self.calls, self.failure, self.fail_node, self.output = [], failure, fail_node, output
        self.lock, self.failed = Lock(), False
    def complete(self, model, messages, **kwargs):
        payload = json.loads(messages[-1]['content'])
        with self.lock:
            self.calls.append((model, deepcopy(payload), time.monotonic()))
            fail = payload.get('node_id') == self.fail_node and not self.failed and self.failure
            if fail:
                self.failed = True
        if messages[0]['content'] == COMPACT_PLANNER_SYSTEM:
            output = json.dumps(self.subplan if 'failed_node' in payload else self.plan)
        elif model.role == 'judge':
            output = json.dumps({'passed':True,'score':100,'rationale':'模拟放行',
                'criteria':[{'criterion':c,'passed':True,'rationale':'模拟放行'} for c in payload['criteria']]})
        elif fail == 'unknown':
            raise RuntimeError('unknown usage')
        elif fail == 'request':
            output = json.dumps({'status':'needs-decomposition','reason':'分别计算及核对再合并'})
        elif fail == 'semantic':
            output = '原始 A→B→D→E；延误 A→C→D→E'
        else:
            output = self.output
        return ChatResponse(output,100,80,0,0,10,1,'length' if fail=='length' else 'stop','mock')


def run(tmp_path, client, **payload):
    result = run_agent({'task':'分别完成两个分析，再完整汇总','template':'auto',**payload},
        provider_config=config(), client=client, mode='live',execute_paid_run=True,runs_dir=tmp_path)
    raw = json.loads((Path(result['run_dir'])/'result.json').read_text())
    return result, raw


def test_default_small_planner_is_compact_and_production_remains_quality_routed(tmp_path):
    client=Client()
    result, raw = run(tmp_path,client)
    assert result['status']=='completed', result['issues']
    assert client.calls[0][0].model_id=='fast'
    assert client.calls[0][0].max_output_tokens==1200
    assert set(client.calls[0][1])=={'task','parallel_capacity','max_nodes'}
    assert len(raw['compact_planning']['attempts'])==1
    assert result['plan_ready_ms']>=0
    assert raw['execution']['policy']['max_concurrency']==4
    assert len(raw['plan']['nodes'])==3
    assert raw['plan_analysis']['parallel_opportunities']==[['left','right']]
    assert all(p['samples']==0 for p in raw['routing_profile']['candidates'])


def test_independent_branches_really_overlap_and_join_waits(tmp_path):
    class Concurrent(Client):
        def __init__(self):
            super().__init__()
            self.left, self.right = Event(), Event()
        def complete(self, model,messages,**kwargs):
            payload=json.loads(messages[-1]['content'])
            nid=payload.get('node_id')
            if nid=='left':
                self.left.set()
                assert self.right.wait(2)
            if nid=='right':
                self.right.set()
                assert self.left.wait(2)
            if nid=='answer':
                assert self.left.is_set() and self.right.is_set()
                assert set(payload['upstream'])=={'left','right'}
            return super().complete(model,messages,**kwargs)
    result,raw=run(tmp_path,Concurrent())
    assert result['status']=='completed'
    assert raw['execution']['peak_running_nodes']>=2
    rows={r['node_id']:r for r in raw['nodes']}
    assert rows['answer']['start_ms']>=max(rows[n]['end_ms'] for n in ('left','right'))


@pytest.mark.parametrize('failure',['request','length','semantic'])
def test_dynamic_split_keeps_completed_sibling_and_executes_new_branches(tmp_path,failure):
    good='原始 A→B→D→E；延误 C→D→E，总工期分别为 8 天和 9 天。'
    client=Client(failure=failure,output=good)
    result, raw=run(tmp_path,client,task=EXHIBITION)
    assert result['status']=='completed',result['issues']
    assert len(raw['initial_plan']['nodes'])==3 and len(raw['plan']['nodes'])==5
    event=raw['dynamic_decomposition']['events'][0]
    assert event['status']=='admitted' and 'right' in event['completed_nodes']
    executions=[p for _,p,_ in client.calls if 'node_id' in p]
    assert sum(p['node_id']=='right' for p in executions)==1
    assert {'left_split_0','left_split_1'}<=set(result['models'])
    assert raw['nodes'][0]['status']=='ok'
    assert result['cost_breakdown']['dynamic_planning']>0
    assert sum(result['cost_breakdown'].values())==pytest.approx(sum(result['costs'].values()))
    assert len([r for r in raw['node_attempts'] if r['node_id']=='left'])==2
    assert all(c['status']=='billed' and c['charged']<=c['reserved'] for c in raw['calls'])
    assert raw['execution']['peak_running_nodes']<=4


def test_dynamic_final_node_can_split_when_no_other_nodes_remain(tmp_path):
    client=Client(plan=compact(('answer',[])), fail_node='answer',failure='request')
    result,raw=run(tmp_path,client)
    assert result['status']=='completed',result['issues']
    assert len(raw['plan']['nodes'])==3 and raw['dynamic_decomposition']['events'][0]['node_id']=='answer'


def test_unknown_usage_never_triggers_dynamic_planner(tmp_path):
    client=Client(failure='unknown')
    result,raw=run(tmp_path,client)
    assert result['status']=='failed' and result['costs']['unconfirmed']>0
    assert not raw['dynamic_decomposition']['events']
    assert not any('failed_node' in p for _,p,_ in client.calls)


def test_repeated_difficulty_stops_after_single_level(tmp_path):
    class Always(Client):
        def complete(self,model,messages,**kwargs):
            response=super().complete(model,messages,**kwargs)
            if json.loads(messages[-1]['content']).get('node_id','').startswith('left'):
                return replace(response,content='{"status":"needs-decomposition","reason":"仍然困难"}')
            return response
    client=Always()
    result,raw=run(tmp_path,client)
    assert result['status']=='failed'
    assert len(raw['dynamic_decomposition']['events'])==1
    assert not any(p.get('node_id')=='answer' for _,p,_ in client.calls)
    assert raw['execution']['not_started']


def test_invalid_dynamic_plan_is_billed_but_never_dispatched(tmp_path):
    client=Client(failure='request',subplan=compact(('only',[])))
    result,raw=run(tmp_path,client)
    assert result['status']=='failed' and 'dynamic-plan-did-not-split' in result['issues']
    assert raw['dynamic_decomposition']['events'][0]['status']=='failed'
    assert not any('_split_' in p.get('node_id','') for _,p,_ in client.calls)


def test_dependency_guard_replays_historical_misjudged_output():
    guard=DependencyGuard(EXHIBITION)
    assert guard.status=='supported'
    assert guard.scenarios['original']['critical_paths']==[['A','B','D','E']]
    assert guard.scenarios['C']['critical_paths']==[['C','D','E']]
    rows=json.loads((ROOT/'reports/automatic-dag/v5-holdout-actual/results.json').read_text())
    for row in rows:
        if row['task_id']=='holdout_exhibition':
            check=guard.check(row['answer'],final=True)
            assert check['passed'] is False
            assert check['invalid_edges']
    assert guard.check('A→B→D→E，延误后 C→D→E',final=True)['passed']
    assert not guard.check('总工期九天',final=True)['passed']


def test_false_positive_judge_cannot_override_dependency_failure(tmp_path):
    client=Client(plan=compact(('answer',[])),output='原始 A→B→D→E，延误后 A→C→D→E')
    result,raw=run(tmp_path,client,task=EXHIBITION,maxDynamicSplits=0)
    assert result['status']=='content-verification-failed'
    assert result['quality'] is None
    assert not any(m.role=='judge' for m,_,_ in client.calls)
    assert result['answer'] and raw['nodes'][0]['content_validation']['passed'] is False


def test_unrecognized_material_is_not_reported_as_verified():
    assert DependencyGuard('写一首短诗').check('诗')['passed'] is None
    assert DependencyGuard('第 0 天开始，A 需要 2 天；B 需要 3 天，其依赖有待确认。').status=='unsupported-source'


@pytest.mark.parametrize('field,value', [('maxDynamicSplits',3),('maxDynamicSplits',True),
    ('plannerTimeoutMs',0),('plannerMaxOutputTokens',99999),('verifyDependencies',1)])
def test_recovery_envelope_validates_before_calls(field,value):
    with pytest.raises(ValueError):
        validate_request({**REQUEST,field:value})


def test_dynamic_preserves_original_upstream_fields_and_final_interface(tmp_path):
    from refractrouter.agent import plan_template
    raw=compile_compact(compact(('seed',[]),('hard',['seed']),('answer',['hard']))).to_dict()
    raw['nodes'][0]['contract']['output']={'format':'json','fields':{'facts':'原始事实','evidence':'依据'}}
    raw['nodes'][1]['contract']['inputs']={'seed':{'fields':['facts'],'reason':'使用原事实'}}
    class JsonUpstream(Client):
        def complete(self,model,messages,**kwargs):
            response=super().complete(model,messages,**kwargs)
            p=json.loads(messages[-1]['content'])
            if p.get('node_id')=='seed':
                return replace(response,content=json.dumps({'facts':'冻结事实','evidence':'仅留存不用交接'}))
            if p.get('node_id','').startswith('hard_split_') or (p.get('node_id')=='hard' and len(p['upstream'])>1):
                assert p['upstream']['seed']=={'facts':'冻结事实'}
            return response
    client=JsonUpstream(failure='request',fail_node='hard')
    result,record=run(tmp_path,client,plan=raw,maxDynamicSplits=1)
    assert result['status']=='completed',result['issues']
    event=record['dynamic_decomposition']['events'][0]
    assert event['upstream']=={'seed':{'facts':'冻结事实'}}
    assert sum(p.get('node_id')=='seed' for _,p,_ in client.calls)==1
    assert next(n for n in record['plan']['nodes'] if n['node_id']=='seed')==raw['nodes'][0]
    assert next(n for n in record['plan']['nodes'] if n['node_id']=='hard')['contract']['output']==raw['nodes'][1]['contract']['output']


def test_budget_exhaustion_during_split_never_starts_new_nodes(tmp_path):
    from refractrouter.task_budget import TaskCallBudget
    from unittest.mock import patch
    original=TaskCallBudget.reserve
    def reserve(self,model,messages,**kwargs):
        if kwargs.get('label','').startswith('dynamic-planner-'):
            self.limits['production']=self.snapshot()[0]['production']
        return original(self,model,messages,**kwargs)
    client=Client(failure='request')
    with patch.object(TaskCallBudget,'reserve',reserve):
        result,raw=run(tmp_path,client)
    assert result['status']=='failed'
    assert any('budget-exhausted' in e for e in result['issues'])
    assert not any('_split_' in p.get('node_id','') for _,p,_ in client.calls)
    assert result['costs']['unconfirmed']==0


def test_cancelled_failed_node_drains_sibling_without_replanning(tmp_path):
    cancelled=Event()
    class Cancel(Client):
        def complete(self,model,messages,**kwargs):
            response=super().complete(model,messages,**kwargs)
            if json.loads(messages[-1]['content']).get('node_id')=='left':
                cancelled.set()
            return response
    client=Cancel(failure='request')
    result=run_agent({'task':'分别分析后汇总','template':'auto'},provider_config=config(),client=client,
        mode='live',execute_paid_run=True,runs_dir=tmp_path,cancel_event=cancelled)
    assert result['status']=='cancelled',result['issues']
    assert not any('failed_node' in p for _,p,_ in client.calls)
    assert result['costs']['unconfirmed']==0


def test_compact_overlong_output_and_cycles_stop_before_execution(tmp_path):
    for plan in (compact(('a',['answer']),('answer',['a'])),
                 {'reason':'过长','nodes':[{**compact(('answer',[]))['nodes'][0],'job':'工'*181}]}):
        client=Client(plan=plan)
        result,raw=run(tmp_path,client)
        assert result['status']=='failed' and len(client.calls)==1
        assert not raw['nodes']


def test_planner_deadline_is_total_including_repairs(tmp_path):
    from unittest.mock import patch
    from refractrouter.task_budget import TaskCallBudget
    original=TaskCallBudget.complete
    def complete(self,*args,**kwargs):
        response=original(self,*args,**kwargs)
        if kwargs.get('label')=='planner':
            time.sleep(1.05)
        return response
    client=Client()
    with patch.object(TaskCallBudget,'complete',complete):
        result,raw=run(tmp_path,client,plannerTimeoutMs=1000,maxPlanRepairs=1)
    assert result['status']=='failed'
    assert len(client.calls)==1 and not raw['nodes']


def test_single_template_capacity_includes_verification_material_and_criteria(tmp_path):
    client=Client(output='原始 A→B→D→E；延误 C→D→E')
    result,raw=run(tmp_path,client,task=EXHIBITION,template='single',
        acceptanceCriteria=['完整保留原始及延误后的排程、依赖和费用。'])
    assert result['status']=='completed',result['issues']
    assert len(client.calls)==2 and result['content_validation']['passed']
    node_call=next(c for c in raw['calls'] if c['label']=='answer')
    size=len(json.dumps(node_call['request_messages'],ensure_ascii=False).encode())+256
    assert size <= raw['plan']['nodes'][0]['contract']['capability']['input_budget_tokens']


def test_dynamic_branches_share_original_concurrency_queue(tmp_path):
    class ConcurrentSplit(Client):
        def __init__(self):
            super().__init__(failure='request')
            self.first, self.second=Event(),Event()
        def complete(self,model,messages,**kwargs):
            p=json.loads(messages[-1]['content'])
            if p.get('node_id')=='left_split_0':
                self.first.set()
                assert self.second.wait(2)
            elif p.get('node_id')=='left_split_1':
                self.second.set()
                assert self.first.wait(2)
            return super().complete(model,messages,**kwargs)
    client=ConcurrentSplit()
    result,raw=run(tmp_path,client,maxConcurrency=2)
    assert result['status']=='completed',result['issues']
    assert client.first.is_set() and client.second.is_set()
    attempts={n['node_id']:n for n in raw['nodes']}
    first,second=attempts['left_split_0'],attempts['left_split_1']
    assert max(first['start_ms'],second['start_ms'])<min(first['end_ms'],second['end_ms'])
    assert raw['execution']['peak_running_nodes']<=2
    assert attempts['left']['start_ms']>=max(first['end_ms'],second['end_ms'])


def test_dynamic_addition_respects_total_node_ceiling():
    roots=[(f'n{i}',[]) for i in range(7)]
    initial=compile_compact(compact(*roots,('answer',[n for n,_ in roots])),max_nodes=8)
    subplan=compile_compact(compact(('part',[]),('merge',['part'])))
    with pytest.raises(ValueError,match='dynamic-node-limit-exhausted'):
        graft(initial,'n0',subplan)
