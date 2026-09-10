"""自动应用必须经过真实运行时；使用模拟供应商，不发起网络调用。"""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

from refractrouter.agent import run_agent
from refractrouter.agent_cli import main
from refractrouter.task_runtime import run_task
from tests.test_provider_configuration import configuration
from tests.test_text_tasks import Client, MANIFEST, PROFILE, REQUEST


def config():
    raw = configuration()
    for model in raw['models']:
        model['contextWindow'] = 131072
    return raw


def test_automatic_application_plans_executes_and_saves_compiled_profile(tmp_path):
    client = Client()
    original = deepcopy(client.plan)
    result = run_agent({'task': '分别分析新方案成本、风险并汇总。', 'template': 'auto'},
        provider_config=config(), client=client, mode='live', execute_paid_run=True, runs_dir=tmp_path)
    assert result['status'] == 'completed', result['issues']
    assert result['plan_origin'] == 'model'
    assert len(client.calls) == 5
    assert client.calls[0][0].model_id == 'better'
    assert set(result['models']) == {'cost', 'risk', 'answer'}
    payload = json.loads(client.calls[0][1][-1]['content'])
    support = payload['execution_support']
    assert support['profile_kind'] == 'configured' and 'forecasts' in support
    assert set(support['forecasts']) == {'fast', 'better'}
    assert 'FIRST_KEY' not in json.dumps(support) and 'baseUrl' not in json.dumps(support)
    directory = Path(result['run_dir'])
    raw = json.loads((directory/'result.json').read_text())
    assert raw['generated_plan'] == original
    actual = json.loads((directory/'plan.json').read_text())
    for a, b in zip(original['nodes'], actual['nodes']):
        assert a['node_type'] == b['node_type']
        for key in ('difficulty', 'risk', 'expected_output_tokens'):
            assert a['contract']['capability'][key] == b['contract']['capability'][key]
    profile = json.loads((directory/'profile.json').read_text())
    assert profile == raw['routing_profile']
    assert profile['kind'] == 'configured'
    assert all(p['samples'] == 0 for p in profile['candidates'])
    basis = profile['forecast_basis']['answer']['better']
    assert basis['input_tokens'] < basis['input_capacity']
    assert basis['input_forecast_source'] == 'serialized-input-and-planned-parent-output'
    assert result['cost_breakdown']['planning'] > 0
    assert abs(sum(result['cost_breakdown'].values()) - sum(result['costs'].values())) < 1e-8
    assert result['wall_time_ms'] >= 0 and result['answer']


def test_empirical_auto_never_relabels_task_to_manufacture_coverage():
    client = Client()
    profile = deepcopy(PROFILE)
    profile.update(kind='empirical', schema_version='node-routing-profile-v2')
    for row in profile['candidates']:
        row.update(difficulty='high', risk='high', input_min_tokens=256, input_max_tokens=131073)
    before = deepcopy(profile)
    result = run_task(REQUEST, MANIFEST, profile, client=client, production_limit=100, evaluation_limit=100)
    assert result['status'] == 'no-feasible-route'
    assert result['generated_plan'] == client.plan == result['plan']
    assert profile == before
    assert len(client.calls) == 1 and not result['nodes']
    assert any(r['reason']=='missing-quality-profile' for r in result['plan_admission'].values())
    assert result['planning_support']['observations'][0]['risk'] == 'high'


def test_whole_plan_admission_stops_before_spending_on_valid_roots(tmp_path):
    raw = config()
    for model in raw['models']:
        model['contextWindow'] = 16000
    result = run_agent({'task': '两部分分析后汇总', 'template':'auto'}, provider_config=raw,
        client=Client(), mode='live', execute_paid_run=True, runs_dir=tmp_path)
    assert result['status'] == 'no-feasible-route'
    runtime = json.loads((Path(result['run_dir'])/'result.json').read_text())
    assert len(runtime['calls']) == 1 and not runtime['nodes']
    assert result['plan_admission']['answer']['reason'] == 'input-or-output-capacity'


def test_final_grade_must_meet_numeric_quality_floor(tmp_path):
    class LowScore(Client):
        def complete(self, model, messages, **kwargs):
            response = super().complete(model, messages, **kwargs)
            if model.role == 'judge':
                grade = json.loads(response.content)
                grade['score'] = 60
                return replace(response, content=json.dumps(grade))
            return response
    raw = config()
    raw['qualityMin'] = 80
    result = run_agent({'task':'完成分析','template':'auto'},provider_config=raw, client=LowScore(),
        mode='live',execute_paid_run=True,runs_dir=tmp_path)
    assert result['status'] == 'quality-failed'
    assert result['answer'] and result['quality']['passed']


def test_auto_zero_call_preview_and_cli_config(tmp_path):
    client = Client()
    result = run_agent({'task':'预检','template':'auto'},provider_config=config(), client=client,runs_dir=tmp_path)
    assert not client.calls and result['quality'] is None
    assert result['plan_origin'] == 'template-preview'
    output = tmp_path/'dsh.json'
    assert main(['dsh-config','--output',str(output),'--template','auto']) == 0
    assert json.loads(output.read_text())[0]['config']['template'] == 'auto'


def test_original_criteria_reach_every_execution_request(tmp_path):
    client = Client()
    criteria = client.plan['acceptance_criteria']
    result = run_agent({'task':'完成分析','template':'auto','acceptanceCriteria':criteria},
        provider_config=config(),client=client,mode='live',execute_paid_run=True,runs_dir=tmp_path)
    assert result['status']=='completed'
    for _, messages in client.calls[1:-1]:
        payload = json.loads(messages[-1]['content'])
        assert all(c in payload['task'] for c in criteria)


def test_one_structural_plan_repair_is_billed_and_preserves_both_outputs(tmp_path):
    class WrongTypeOnce(Client):
        def complete(self, model, messages, **kwargs):
            response = super().complete(model, messages, **kwargs)
            if len(self.calls)==1:
                raw = json.loads(response.content)
                raw['nodes'][0]['node_type']='analysis'
                return replace(response,content=json.dumps(raw))
            return response
    client=WrongTypeOnce()
    result=run_agent({'task':'完整分析','template':'auto'},provider_config=config(),client=client,
        mode='live',execute_paid_run=True,runs_dir=tmp_path)
    assert result['status']=='completed',result['issues']
    raw=json.loads((Path(result['run_dir'])/'result.json').read_text())
    assert len(client.calls)==6 and len(raw['planning_attempts'])==2
    assert raw['planning_attempts'][0]['error']=='unsupported text node_type'
    assert raw['planning_attempts'][1]['error'] is None
    assert json.loads(raw['planner_output'])['nodes'][0]['node_type']=='analysis'
    assert raw['plan']['nodes'][0]['node_type']=='synthesis'
    assert [c['label'] for c in raw['calls'][:2]]==['planner','planner-repair']
    assert abs(result['cost_breakdown']['planning']-sum(c['charged'] for c in raw['calls'][:2]))<1e-8


def test_repair_is_bounded_and_can_be_disabled(tmp_path):
    for limit in (0,1):
        client=Client()
        client.plan['nodes'][0]['node_type']='analysis'
        result=run_agent({'task':'不能无限修正','template':'auto','maxPlanRepairs':limit},
            provider_config=config(),client=client,mode='live',execute_paid_run=True,runs_dir=tmp_path)
        assert result['status']=='failed' and len(client.calls)==1+limit
        assert not result['models'] and result['costs']['production']>0


def test_capacity_ceiling_is_not_charged_as_predicted_input(tmp_path):
    raw=config()
    raw['qualityMin']=90  # 只允许 better，避免便宜候选掩盖原始费用拒绝问题。
    for model in raw['models']:
        model['maxOutputTokens']=4096
    raw['models'][1]['pricing'].update(inputPer1k=.55,outputPer1k=.55)
    result=run_agent({'task':'分别核算成本和风险再汇总','template':'auto'},provider_config=raw,
        client=Client(),mode='live',execute_paid_run=True,runs_dir=tmp_path,max_output_tokens=4096,
        production_budget=40)
    assert result['status']=='completed',result['issues']
    profile=json.loads((Path(result['run_dir'])/'profile.json').read_text())
    basis=[row['better'] for row in profile['forecast_basis'].values()]
    old=sum((b['input_capacity']+b['output_tokens'])*.55/1000 for b in basis)
    expected=sum((b['input_tokens']+b['output_tokens'])*.55/1000 for b in basis)
    assert old > 40 > expected
    runtime=json.loads((Path(result['run_dir'])/'result.json').read_text())
    assert all(c['charged']<=c['reserved'] and c.get('category_limit',40)==40
               for c in runtime['calls'] if c['category']=='production')
