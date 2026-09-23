"""自动容量预估不把尚未生成的父输出当作实际超限；全程无网络。"""
from dataclasses import replace
import pytest

from refractrouter.compact_planning import compile_compact
from refractrouter.planning_support import compile_generated_capacity
from refractrouter.task_execution import node_messages
from refractrouter.task_budget import request_input_bound
from tests.test_native_tool_runtime import real_model, SCHEMAS


def fixture():
    plan=compile_compact({'reason':'先获取，再整理并交付','nodes':[
        {'id':'fetch','type':'extraction','job':'取得资料','parents':[],'difficulty':'low','risk':'low'},
        {'id':'organize_data','type':'generation','job':'整理资料并交付','parents':['fetch'],'difficulty':'low','risk':'low'}]})
    model=replace(real_model(), max_output_tokens=8192, context_window=262144)
    return plan,{model.model_id:model}


def test_worst_case_parent_allowance_defers_to_actual_request_without_relaxing_limit():
    plan,candidates=fixture();task='x'*71000
    compiled,estimates=compile_generated_capacity(plan,task,candidates,tools=SCHEMAS)
    row=estimates['organize_data']
    assert row['base_input_bound'] < 131072 < row['estimated_input_bound']
    assert row['upstream_capacity_check']=='at-dispatch'
    assert compiled.contracts['organize_data']['capability']['input_budget_tokens']==131072
    node=compiled.nodes[1];contract=compiled.contracts[node.node_id]
    messages=node_messages(task,node,contract,{'fetch':{'text':'模拟资料'}},tools=SCHEMAS)
    assert request_input_bound(messages,SCHEMAS)<131072
    with pytest.raises(ValueError,match='node-input-budget-exceeded'):
        node_messages(task,node,contract,{'fetch':{'text':'x'*70000}},tools=SCHEMAS)
    # 输入计划不被原地修改，节点职责、依赖与输出上限不变。
    assert plan.contracts[node.node_id]['capability']['input_budget_tokens']==65536
    assert compiled.nodes[1].parents==plan.nodes[1].parents
    assert compiled.contracts[node.node_id]['output']==plan.contracts[node.node_id]['output']


def test_known_material_over_limit_still_rejected_before_dispatch():
    plan,candidates=fixture()
    with pytest.raises(ValueError,match='known_input=.*input_cap=131072'):
        compile_generated_capacity(plan,'x'*131072,candidates)


def test_tool_schema_and_instruction_are_included_in_compiled_capacity():
    plan,candidates=fixture()
    compiled,rows=compile_generated_capacity(plan,'模拟任务',candidates,tools=SCHEMAS)
    _,without=compile_generated_capacity(plan,'模拟任务',candidates)
    assert rows['fetch']['base_input_bound']>without['fetch']['base_input_bound']
    messages=node_messages('模拟任务',compiled.nodes[0],compiled.contracts['fetch'],{},tools=SCHEMAS)
    assert request_input_bound(messages,SCHEMAS)<=compiled.contracts['fetch']['capability']['input_budget_tokens']
    large=[{'name':'tool','description':'x'*131072,'parameters':{}}]
    with pytest.raises(ValueError,match='automatic-plan-input-capacity-exceeded'):
        compile_generated_capacity(plan,'短任务',candidates,tools=large)


def test_custom_capacity_stays_authoritative():
    plan,candidates=fixture()
    compiled,rows=compile_generated_capacity(plan,'x'*10000,candidates,input_cap=20000)
    assert compiled.contracts['organize_data']['capability']['input_budget_tokens']==20000
    assert rows['organize_data']['upstream_capacity_check']=='at-dispatch'


def test_automatic_agent_compiles_generated_capacity_after_output_cap(tmp_path):
    import json
    from refractrouter.agent import run_agent
    from refractrouter.agent_cli import example_configuration
    from refractrouter.compact_planning import COMPACT_PLANNER_SYSTEM
    from tests.test_native_tool_runtime import StdioToolRuntime, Host, reply
    config=example_configuration('openai-compatible')
    # DSH 目录可报告远高于本轮请求的输出上限。容量编译必须先应用本轮
    # 2K 上限，不能把 128K 当成每个父节点都会交接的实际文本量。
    for model in config['models']:
        model.update(contextWindow=262144,maxOutputTokens=128000)
    class Client:
        max_retries=0
        def complete(self,model,messages,**kwargs):
            if messages[0]['content']==COMPACT_PLANNER_SYSTEM:
                assert not kwargs.get('tools')
                return reply(json.dumps({'reason':'获取然后整理','nodes':[
                    {'id':'fetch','type':'extraction','job':'提取资料','parents':[],'difficulty':'low','risk':'low'},
                    {'id':'organize_data','type':'generation','job':'整理交付','parents':['fetch'],'difficulty':'low','risk':'low'}]}))
            if model.role=='judge':
                criteria=json.loads(messages[-1]['content'])['criteria']
                return reply(json.dumps({'score':95,'passed':True,'rationale':'模拟验证',
                    'criteria':[{'criterion':c,'passed':True,'rationale':'模拟'} for c in criteria]}))
            assert kwargs['tools']==SCHEMAS
            return reply('模拟的简短资料')
    result=run_agent({'task':'根据已有材料提取并整理','context':'x'*71000,'template':'auto'},
        mode='live',runs_dir=tmp_path,execute_paid_run=True,provider_config=config,client=Client(),
        max_output_tokens=2048,tool_runtime=StdioToolRuntime(SCHEMAS,Host()))
    assert result['status']=='completed',result['issues']
    saved=json.loads(__import__('pathlib').Path(result['result_path']).read_text())
    row=saved['compiled_input_estimates']['organize_data']
    assert row['upstream_allowance']==2048*8
    assert row['upstream_capacity_check'] in {'compiled','reserved'}
    assert saved['plan']['nodes'][1]['contract']['capability']['input_budget_tokens']<131072
