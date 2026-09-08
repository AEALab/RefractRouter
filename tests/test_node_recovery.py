"""失败节点切换模型，保留全部尝试，禁止失败内容或未知费用扩散。"""
from collections import Counter
from copy import deepcopy
from dataclasses import replace
import json
from threading import Event
from unittest.mock import patch

import pytest

from refractrouter.task_runtime import run_task, validate_request
from tests.test_task_decomposition import example
from tests.test_text_tasks import Client, MANIFEST, PROFILE, REQUEST, live


class BrokenNode(Client):
    def __init__(self, *, failures=1, kind='structure', nid='cost'):
        super().__init__()
        self.failures, self.kind, self.nid = failures, kind, nid
        self.seen = []

    def complete(self, model, messages, *, json_mode=False):
        payload = json.loads(messages[-1]['content'])
        response = super().complete(model, messages, json_mode=json_mode)
        if payload.get('node_id') == self.nid:
            self.seen.append((model.model_id, deepcopy(messages)))
            if len(self.seen) <= self.failures:
                if self.kind == 'unknown':
                    return replace(response, usage_available=False, input_tokens=0, output_tokens=0)
                if self.kind == 'infrastructure':
                    raise RuntimeError('private provider diagnostic')
                return replace(response, content='{"result":"未完成',
                               finish_reason='length' if self.kind == 'truncated' else 'stop')
        return response


def run(client, **kwargs):
    with patch('socket.socket', side_effect=AssertionError('禁止网络')):
        return live(client, plan=example(), maxNodeFallbacks=1, **kwargs)


@pytest.mark.parametrize('method', ['A', 'B'])
@pytest.mark.parametrize('kind', ['structure', 'truncated'])
def test_replacement_keeps_input_and_valid_siblings_and_accounts_all_attempts(method, kind):
    client = BrokenNode(kind=kind)
    result = run(client, method=method, weights=None if method == 'A' else REQUEST['weights'])
    assert result['status'] == 'completed', result['issues']
    assert len(client.seen) == 2 and client.seen[0][0] != client.seen[1][0]
    assert client.seen[0][1] == client.seen[1][1]
    assert len(result['nodes']) == 3 and len(result['node_attempts']) == 4
    assert len(result['calls']) == 5 and len({c['label'] for c in result['calls']}) == 5
    assert all(c['status'] == 'billed' and c['charged'] > 0 for c in result['calls'])
    assert result['charged']['production'] == pytest.approx(sum(c['charged'] for c in result['calls'] if c['category']=='production'))
    assert result['assignments']['cost'] != result['initial_assignments']['cost']
    assert result['routing']['assignments'] == result['initial_assignments']
    assert Counter(json.loads(m[-1]['content']).get('node_id') for _,m in client.calls)['risk'] == 1
    final_request = next(json.loads(m[-1]['content']) for _,m in client.calls if json.loads(m[-1]['content']).get('node_id')=='answer')
    cost = next(r for r in result['nodes'] if r['node_id']=='cost')
    assert final_request['upstream']['cost'] == json.loads(cost['output'])
    assert next(c for c in result['calls'] if c['label']=='cost')['response_output'] == '{"result":"未完成'
    assert result['node_attempts'][0]['status'] in ('invalid-output','failed')


def test_fallback_is_opt_in_and_exhaustion_never_revisits_a_model():
    client = BrokenNode(failures=10)
    result = live(client, plan=example(), method='A', weights=None)
    assert result['status']=='failed' and len(client.seen)==1
    client = BrokenNode(failures=10)
    result = live(client, plan=example(), method='A', weights=None, maxNodeFallbacks=2)
    assert result['status']=='failed' and len(client.seen)==3
    assert len({mid for mid,_ in client.seen})==3
    assert result['evaluation'] is None and result['execution']['not_started']==['risk','answer']
    assert len(result['recovery']['events'])==2


@pytest.mark.parametrize('kind', ['unknown','infrastructure'])
def test_unknown_usage_or_infrastructure_does_not_switch(kind):
    client=BrokenNode(kind=kind)
    result=run(client,method='A',weights=None)
    assert result['status']=='failed' and len(client.seen)==1
    assert result['calls'][0]['status']=='unknown-usage'
    assert result['calls'][0]['charged']==result['calls'][0]['reserved']>0
    assert not result['recovery']['events'] and result['evaluation'] is None
    assert 'private' not in str(result)


def test_no_profile_above_floor_means_no_replacement():
    profile=deepcopy(PROFILE)
    profile['kind']='empirical'
    for p in profile['candidates']:
        p['quality']=90 if p['model_id']=='cheap' else 79
    client=BrokenNode()
    result=run_task({**REQUEST,'plan':example(),'maxNodeFallbacks':2},MANIFEST,profile,
                    client=client,production_limit=100,evaluation_limit=100)
    assert result['status']=='failed' and len(client.seen)==1
    assert result['nodes'][0]['recovery_status']=='no-feasible-replacement'


def test_recovery_can_run_while_other_branch_remains_inflight():
    replaced=Event()
    class Concurrent(BrokenNode):
        def complete(self,model,messages,*,json_mode=False):
            nid=json.loads(messages[-1]['content']).get('node_id')
            if nid=='risk':
                assert replaced.wait(2)
            response=super().complete(model,messages,json_mode=json_mode)
            if nid=='cost' and len(self.seen)==2:
                replaced.set()
            return response
    result=run(Concurrent(),maxConcurrency=2,method='A',weights=None)
    assert result['status']=='completed', result['issues']
    rows={r['node_id']:r for r in result['nodes']}
    assert rows['answer']['start_ms']>=max(rows[x]['end_ms'] for x in ('risk','cost'))
    assert result['execution']['peak_running_nodes']<=2


def test_final_semantic_failure_does_not_guess_which_node_to_repeat():
    result=run(Client(bad_judge=True))
    assert result['status']=='failed' and result['final_output']
    assert not result['recovery']['events'] and len(result['calls'])==4


@pytest.mark.parametrize('value', [-1,3,True,0.5,'1'])
def test_invalid_recovery_limit_rejected(value):
    with pytest.raises(ValueError,match='maxNodeFallbacks'):
        validate_request({**REQUEST,'maxNodeFallbacks':value})


def test_preflight_records_fallback_limit_without_calls():
    result=run_task({**REQUEST,'mode':'preflight','plan':example(),'maxNodeFallbacks':1},MANIFEST,PROFILE)
    assert result['status']=='preview' and result['calls']==[]
    assert result['recovery_policy']['max_node_fallbacks']==1


def test_historical_frozen_protocol_is_not_silently_rebound():
    from pathlib import Path
    from refractrouter.dag_study import load_study
    path=Path(__file__).resolve().parents[1]/'data/benchmarks/dag-routing-v6.json'
    with pytest.raises(ValueError,match='frozen implementation changed'):
        load_study(path)


@pytest.mark.parametrize('blocker', ['cost','latency','capacity'])
def test_replacement_respects_remaining_constraints(blocker):
    from refractrouter.node_recovery import NodeRecovery
    from refractrouter.node_routing import load_profile, route_nodes
    from refractrouter.task_plan import validate_plan
    from refractrouter.task_scheduling import ExecutionPolicy
    plan=validate_plan(example())
    profiles=load_profile(PROFILE,MANIFEST)
    candidates={m.model_id:m for m in MANIFEST.candidates}
    eligible={n.node_id:list(candidates) for n in plan.nodes}
    if blocker=='capacity':
        eligible['cost']=['cheap']
    policy=ExecutionPolicy()
    route=route_nodes(plan,profiles,method='A',quality_min=80,cost_max=10,latency_max_ms=300000,
                      eligible_models=eligible,execution_policy=policy,
                      model_providers={mid:m.provider for mid,m in candidates.items()})
    recovery=NodeRecovery(plan,profiles,candidates,route,policy,max_fallbacks=2)
    original=deepcopy(route)
    chosen=recovery.choose('cost',route['assignments'],{'cheap'},set(),{},spent=9.999 if blocker=='cost' else 0,
                           cost_limit=10,remaining_ms=1 if blocker=='latency' else 300000,input_bound=1000)
    assert chosen is None and route==original


def test_cancellation_at_failed_response_never_starts_replacement():
    cancel=Event()
    class Cancelled(BrokenNode):
        def complete(self,*args,**kwargs):
            response=super().complete(*args,**kwargs)
            cancel.set()
            return response
    client=Cancelled()
    result=run_task({**REQUEST,'plan':example(),'maxNodeFallbacks':2},MANIFEST,{**PROFILE,'kind':'empirical'},
                    client=client,production_limit=100,evaluation_limit=100,cancel_event=cancel)
    assert len(client.seen)==1 and not result['recovery']['events']
    assert result['status'] in ('failed','cancelled')


def test_fallback_production_cap_admission_is_atomic():
    from refractrouter.task_budget import TaskCallBudget
    model=MANIFEST.candidates[0]
    messages=[{'role':'user','content':'{}'}]
    budget=TaskCallBudget(Client(),100,100)
    first=budget.reserve(model,messages,label='first')
    with pytest.raises(ValueError,match='budget-exhausted'):
        budget.reserve(model,messages,label='second',category_limit=first.row['reserved']*1.5)
    assert len(budget.records)==1
