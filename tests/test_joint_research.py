"""正式研究的独立分母、冻结边界和无网络执行验证。"""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import pytest
from experiments.prepare_joint_research import prepare
from experiments.rehearse_research_execution import DevelopmentClient
from refractrouter.joint_research import preflight, run, historical_materials
from refractrouter.manifest import load_model_manifest

ROOT=Path(__file__).resolve().parents[1]


def test_frozen_coverage_and_historical_exclusion():
    p=prepare(); m=load_model_manifest(ROOT/'data/model-manifests/volcengine-agent-plan.json')
    preview=preflight(p,m,excluded_materials=historical_materials(ROOT,ROOT/'data/research/joint-39-40-v1.json'))
    assert len(preview['runs'])==104 and preview['required_under_assumed_sd']==8
    assert preview['maximum_calls']==808
    assert preview['historical_materials_checked']>0
    with pytest.raises(ValueError,match='historical'):
        preflight(p,m,excluded_materials=[p['tasks'][0]['material_sha256']])
    p['tasks'][0]['task']+=' changed'
    with pytest.raises(ValueError,match='changed'):
        preflight(p,m)


def test_joint_offline_execution_freezes_before_test_and_keeps_denominators(tmp_path):
    p=prepare();p['execution_policy']['providerMinIntervalMs']['ark-plan']=0
    m=load_model_manifest(ROOT/'data/model-manifests/volcengine-agent-plan.json')
    with patch('socket.socket',side_effect=AssertionError('禁止网络')):
        result=run(p,m,tmp_path/'run',DevelopmentClient(p['tasks']),simulated=True)
    assert result['status']=='simulated'
    assert len([r for r in result['runs'] if r['split']=='test'])==104
    assert result['calibration_frozen_sha256'] and result['node_profile']['candidates']
    assert all(o['task_id'].startswith('cal_') for o in result['observations']['observations'])
    handoffs=[r for r in result['runs'] if r['arm']=='handoff']
    assert len(handoffs)==6 and all(len(set(r['assignments'].values()))==3 for r in handoffs)
    assert len(result['calls'])<=result['preflight']['maximum_calls']
    assert all(c['status']=='billed' for c in result['calls'])
    assert all(not a['benefit_verified'] for a in result['analysis']['issues'].values())
    assert not result['analysis']['human_review_complete']
    assert len(result['plan_setups'])==16
    for issue,arms in (('39',9),('40',8)):
        assert sum(a['planned'] for a in result['analysis']['issues'][issue]['groups']['overall']['arms'].values())==8*arms


def test_rejected_material_stops_before_candidate_calls(tmp_path):
    from dataclasses import replace
    import json
    class Reject(DevelopmentClient):
        def complete(self,model,messages,**kwargs):
            assert model.role=='judge'
            reply=super().complete(model,messages,**kwargs)
            raw=json.loads(reply.content);raw['passed']=False;raw['score']=20
            return replace(reply,content=json.dumps(raw))
    p=prepare();m=load_model_manifest(ROOT/'data/model-manifests/volcengine-agent-plan.json')
    with patch('socket.socket',side_effect=AssertionError('禁止网络')):
        result=run(p,m,tmp_path/'rejected',Reject(p['tasks']),simulated=True)
    assert result['status']=='material-review-rejected' and len(result['calls'])==1
    assert not result['runs'] and result['charged']['evaluation']>0
    assert result['analysis']['issues']['39']['groups']['overall']['arms']['dag-node-a']['planned']==8
