"""紧凑规划的默认思考策略不影响节点执行与显式用户设置。"""
from dataclasses import replace
import pytest
from refractrouter.agent import run_agent
from refractrouter.ark_plan import application_configuration
from refractrouter.application_config import compile_configuration
from refractrouter.compact_planning import planner_model
from refractrouter.openai_compatible import ChatResponse
from tests.test_fast_dynamic_dag import Client


def test_ark_compact_planner_inherits_thinking_and_uses_model_capacity(tmp_path):
    client = Client()
    result = run_agent({'task':'分别分析后汇总', 'template':'auto'},
        provider_config=application_configuration(),client=client,mode='live',
        execute_paid_run=True,runs_dir=tmp_path)
    assert result['status'] == 'completed', result['issues']
    planner = client.calls[0][0]
    assert planner.api_model == 'doubao-seed-2.0-mini'
    assert 'thinking' not in planner.request_options
    assert planner.max_output_tokens == 128000
    assert result['planner']['timeout_ms'] is None
    assert 'model-capacity' in result['planner']['basis']
    nodes = [model for model, payload, _ in client.calls[1:] if 'node_id' in payload]
    assert nodes and all('thinking' not in model.request_options for model in nodes)


@pytest.mark.parametrize('options', [{'thinking':{'type':'enabled'}},
    {'thinking':{'type':'disabled'}}, {'reasoning_effort':'high'}])
def test_explicit_model_options_are_preserved(options):
    model=compile_configuration(application_configuration()).manifest.candidates[0]
    model=replace(model,request_options=options)
    selected,_=planner_model({model.model_id:model},compact=True)
    assert selected.request_options == options
    assert model.request_options == options


@pytest.mark.parametrize('change,compact', [({},False),
    ({'base_url':'https://example.com/v1'},True), ({'api_model':'another-model'},True)])
def test_no_policy_is_assumed_for_full_planning_or_other_routes(change,compact):
    model=compile_configuration(application_configuration()).manifest.candidates[0]
    model=replace(model,request_options={},**change)
    selected,_=planner_model({model.model_id:model},compact=compact)
    assert selected.request_options == {}


def test_truncated_planner_remains_failed_with_usage_diagnostics(tmp_path):
    class Truncated(Client):
        def complete(self, model, messages, **kwargs):
            return ChatResponse('',100,1200,0,1200,10,1,'length','mock')
    result=run_agent({'task':'测试截断','template':'auto'},provider_config=application_configuration(),
        client=Truncated(),mode='live',execute_paid_run=True,runs_dir=tmp_path)
    assert result['status']=='failed'
    assert 'finish_reason=length' in result['issues'][0]
    assert 'reasoning_tokens=1200' in result['issues'][0]
    assert result['plan'] is None
