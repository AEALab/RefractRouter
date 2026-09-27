"""虚拟模型只声明可保证的交集，不修改冻结角色或宿主指令。"""
import importlib.util
from copy import deepcopy
import pytest
from tests.test_model_gateway import Caller, gateway, reply, request
from tests.test_planning_routing import configuration
from refractrouter.gateway_responses import to_chat


def test_reasoning_assertion_matches_without_changing_role(tmp_path):
    caller=Caller(reply());gw=gateway(tmp_path,caller)
    req=to_chat({'model':'refract/static','input':'你好','reasoning':{'effort':'low'}})
    gw.complete(req)
    assert caller.actions[0]['model']['reasoning_effort']=='low'
    assert gw.models()['data'][0]['refract']['acceptedReasoningEfforts']==['low']
    gw.close()


@pytest.mark.parametrize('effort',['high','rr:stage',None,False,{}])
def test_mismatched_effort_never_spends(tmp_path,effort):
    caller=Caller();gw=gateway(tmp_path,caller)
    with pytest.raises(ValueError,match='冻结'):
        gw.complete({**request(),'reasoning_effort':effort})
    assert not caller.actions and not gw.runtime.runs
    gw.close()


def test_candidate_intersection_excludes_judge(tmp_path):
    cfg=configuration();cfg['models'][1]['reasoningEffort']='high'
    cfg['models'][1]['contextWindow']=16000
    caller=Caller();gw=gateway(tmp_path,caller,cfg)
    assert gw.capabilities('static')['acceptedReasoningEfforts']==['low']
    assert gw.capabilities('stage')['acceptedReasoningEfforts']==[]
    assert gw.capabilities('stage')['contextWindow']==16000
    gw.close()


def test_codex_catalog_preserves_host_owned_instructions(tmp_path):
    spec=importlib.util.spec_from_file_location('catalog','validation/codex/model_catalog.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    gw=gateway(tmp_path,Caller())
    baseline={'models':[{'slug':'host','base_instructions':'宿主自己的规则',
        'model_messages':{'x':'宿主提示'},'auto_compact_token_limit':50000,'shell_type':'unified_exec'}]}
    saved=deepcopy(baseline)
    result=mod.catalog(baseline,'host',gw.models())
    entry=next(m for m in result['models'] if m['slug']=='refract/static')
    assert baseline==saved
    assert entry['base_instructions']=='宿主自己的规则'
    assert entry['model_messages']==baseline['models'][0]['model_messages']
    assert entry['auto_compact_token_limit']==32000-1024
    assert entry['supported_reasoning_levels'][0]['effort']=='low'
    assert entry['input_modalities']==['text']
    assert not entry['supports_search_tool']
    assert all('base_instructions' not in x for x in gw.models()['data'])
    gw.close()
