"""Configured provider routing, accounting and credential boundaries; no paid calls."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from refractrouter.agent import run_agent
from refractrouter.agent_cli import example_configuration, main
from refractrouter.application_config import compile_configuration
from refractrouter.openai_compatible import OpenAICompatibleClient, TransportResponse
from refractrouter.task_runtime import run_task
from tests.test_text_tasks import Client


def configuration():
    raw = example_configuration('openai-compatible')
    raw['providers'] = [
        {'id':'first','type':'openai-compatible','baseUrl':'https://first.example/v1','credentialEnv':'FIRST_KEY'},
        {'id':'second','type':'openai-compatible','baseUrl':'https://second.example/v1','credentialEnv':'SECOND_KEY','maxTokensParameter':'max_tokens'},
    ]
    candidate, judge = raw['models']
    candidate.update(id='fast', provider='first', model='shared-name')
    candidate['routing'] = {'quality':85,'latencyMs':1000}
    stronger = deepcopy(candidate)
    stronger.update(id='better', provider='second')
    stronger['routing'] = {'quality':95,'latencyMs':3000}
    stronger['pricing'] = {'unit':'USD','inputPer1k':.01,'outputPer1k':.02}
    judge.update(provider='second', model='independent-review')
    raw['models'] = [candidate,stronger,judge]
    return raw


@pytest.mark.parametrize(('strategy','provider'), [('economy','first'),('quality','second')])
def test_routes_across_providers_even_when_api_model_names_collide(tmp_path,strategy,provider):
    client=Client()
    result=run_agent({'task':'比较两种方案','strategy':strategy},provider_config=configuration(),
                     mode='live',execute_paid_run=True,runs_dir=tmp_path,client=client)
    assert result['status']=='completed',result['issues']
    assert result['model_routes']=={'answer':{'id':'fast' if strategy=='economy' else 'better',
        'provider':provider,'model':'shared-name','reasoning_effort':None}}
    assert result['evaluation_model']=={'id':'review','provider':'second',
        'model':'independent-review','reasoning_effort':None}
    assert len(client.calls)==2 and client.calls[-1][0].provider=='second'
    assert result['configuration_source']=='user' and result['billing_unit']=='USD'
    profile=json.loads((Path(result['run_dir'])/'profile.json').read_text())
    assert profile['kind']=='configured' and all(row['samples']==0 for row in profile['candidates'])


def test_one_candidate_with_32k_context_can_complete_short_task(tmp_path):
    result=run_agent({'task':'简短回答'},provider_config=example_configuration('openai-compatible'),
                     mode='live',execute_paid_run=True,runs_dir=tmp_path,client=Client())
    assert result['status']=='completed',result['issues']
    request=json.loads((Path(result['run_dir'])/'request.json').read_text())
    cap=request['runtime_request']['plan']['nodes'][0]['contract']['capability']['input_budget_tokens']
    assert 256<=cap<32768


def test_configured_compare_uses_core_dag_and_preserves_upstream(tmp_path):
    client=Client()
    raw=configuration()
    for model in raw['models']: model['contextWindow']=131072
    result=run_agent({'task':'比较 A/B 成本与风险','template':'compare'},provider_config=raw,
                     mode='live',execute_paid_run=True,runs_dir=tmp_path,client=client)
    assert result['status']=='completed',result['issues']
    assert len(client.calls)==4
    assert set(json.loads(client.calls[2][1][-1]['content'])['upstream'])=={'cost','risk'}


@pytest.mark.parametrize('mutate', [
    lambda c:c['models'][0]['pricing'].update(unit='AFP'),
    lambda c:c['models'][0].update(provider='missing'),
    lambda c:c['models'].append(deepcopy(c['models'][0])),
    lambda c:c['models'].pop(),
    lambda c:c['models'][0]['routing'].update(quality=float('nan')),
    lambda c:c['models'][0]['pricing'].update(outputPer1k=-1),
    lambda c:c['models'][0]['pricing'].update(cachedInputPer1k=99),
    lambda c:c['models'][0].update(requestOptions={'messages':[]}),
    lambda c:c['providers'][0].update(apiKey='never-a-config-value'),
    lambda c:c['providers'][0].update(baseUrl='https://user:secret@example.com/v1'),
    lambda c:c['providers'][0].update(baseUrl='https://example.com/v1?api_key=value'),
    lambda c:c['providers'][0].update(type='anthropic-native'),
    lambda c:c['providers'][0].update(type='ark-agent-plan'),
])
def test_invalid_configuration_fails_before_dispatch_or_artifacts(tmp_path,mutate):
    config=configuration();mutate(config)
    client=Client()
    with pytest.raises(ValueError):
        run_agent({'task':'拒绝无效配置'},provider_config=config,mode='live',execute_paid_run=True,runs_dir=tmp_path,client=client)
    assert not client.calls and not list(tmp_path.iterdir())


def test_explicit_ark_provider_can_have_any_user_id_and_accounting_unit(tmp_path):
    config=example_configuration('ark-agent-plan')
    config['providers'][0]['id']='my-subscription'
    for model in config['models']: model['provider']='my-subscription'
    result=run_agent({'task':'验证可选 Ark provider'},provider_config=config,mode='demo',runs_dir=tmp_path)
    assert result['status']=='simulated'
    assert result['model_routes']['answer']['provider']=='my-subscription'
    assert result['billing_unit']=='AFP'


def test_no_implicit_ark_live_or_custom_profile_borrowing(tmp_path):
    with pytest.raises(ValueError,match='configure providers'):
        run_agent({'task':'不隐式使用 Ark'},mode='live',execute_paid_run=True,runs_dir=tmp_path)
    with pytest.raises(ValueError,match='cannot be combined'):
        run_agent({'task':'不能借用旧模型 profile'},provider_config=configuration(),preset='ark-agent-plan',runs_dir=tmp_path)


def test_configured_predictions_do_not_pass_legacy_empirical_gate(tmp_path):
    config=configuration()
    result=run_agent({'task':'生成配置预测'},provider_config=config,mode='demo',runs_dir=tmp_path)
    folder=Path(result['run_dir'])
    request=json.loads((folder/'request.json').read_text())['runtime_request']
    request['mode']='run'
    profile=json.loads((folder/'profile.json').read_text())
    with pytest.raises(ValueError,match='empirical'):
        run_task(request,replace(compile_configuration(config).manifest, models=tuple(
            replace(m, request_options={**m.request_options, 'temperature': 0}) if m.role=='candidate' else m
            for m in compile_configuration(config).manifest.models)),profile,client=Client())


def test_http_clients_use_each_provider_key_url_and_token_field(tmp_path):
    config=configuration()
    model=compile_configuration(config).manifest.judge
    captured=[]
    class Transport:
        def post(self,url,headers,body,timeout_seconds):
            captured.append((url,headers,json.loads(body)))
            return TransportResponse(200,{},json.dumps({'choices':[{'message':{'content':'ok'},'finish_reason':'stop'}],
                'usage':{'prompt_tokens':10,'completion_tokens':2}}).encode())
    client=OpenAICompatibleClient(transport=Transport(),environment={'FIRST_KEY':'first-secret','SECOND_KEY':'second-secret'},max_retries=0)
    client.complete(model,[{'role':'user','content':'test'}])
    assert captured[0][0]=='https://second.example/v1/chat/completions'
    assert captured[0][1]['Authorization']=='Bearer second-secret'
    assert captured[0][2]['max_tokens']==2048 and 'max_completion_tokens' not in captured[0][2]
    assert 'first-secret' not in json.dumps(captured)


def test_local_http_provider_can_explicitly_omit_authentication():
    config=example_configuration('openai-compatible')
    config['providers'][0].pop('credentialEnv')
    config['providers'][0]['baseUrl']='http://127.0.0.1:9000/v1'
    model=compile_configuration(config).manifest.candidates[0]
    class Transport:
        def post(self,url,headers,body,timeout_seconds):
            assert 'Authorization' not in headers
            return TransportResponse(200,{},b'{"choices":[{"message":{"content":"ok"},"finish_reason":"stop"}],"usage":{"prompt_tokens":10,"completion_tokens":2}}')
    assert OpenAICompatibleClient(transport=Transport(),environment={},max_retries=0).complete(model,[{'role':'user','content':'test'}]).content=='ok'


def test_dsh_configuration_never_requires_ark_credentials_and_rejects_recursion(tmp_path):
    config=example_configuration('dsh')
    compiled=compile_configuration(config)
    assert all(m.wire_api=='dsh-llm' and m.api_key_env is None for m in compiled.manifest.models)
    with patch.dict('os.environ',{},clear=True):
        with pytest.raises(ValueError,match='through the DSH plugin'):
            run_agent({'task':'CLI 不能绕过宿主'},provider_config=config,mode='live',execute_paid_run=True,runs_dir=tmp_path)
    config['providers'][0]['dshProvider']='refractagent'
    with pytest.raises(ValueError,match='recursively'):compile_configuration(config)


def test_cli_compiles_user_configuration_into_dsh_overlay(tmp_path,capsys):
    source=tmp_path/'providers.json'
    target=tmp_path/'plugin.json'
    assert main(['config-example','--output',str(source)])==0
    assert main(['models','--provider-config',str(source)])==0
    assert main(['dsh-config','--provider-config',str(source),'--mode','live','--runs-dir',str(tmp_path/'runs'),'--output',str(target)])==0
    config=json.loads(target.read_text())[0]['config']
    assert config['providerConfig']==json.loads(source.read_text())
    assert config['allowPaidRuns'] is False and 'preset' not in config and 'credentialEnv' not in config
    assert main(['dsh-config','--mode','live','--runs-dir',str(tmp_path/'runs'),'--output',str(tmp_path/'missing.json')])==1


def test_effective_snapshot_preserves_output_and_temperature_overrides(tmp_path):
    config=example_configuration('openai-compatible')
    result=run_agent({'task':'检查调用配置','temperature':0.5},provider_config=config,
        mode='live',execute_paid_run=True,runs_dir=tmp_path,max_output_tokens=1000,client=Client())
    manifest=json.loads((Path(result['run_dir'])/'manifest.json').read_text())
    assert all(m['max_output_tokens']==1000 for m in manifest['models'])
    assert manifest['models'][0]['request_options']['temperature']==0.5
    assert json.loads((Path(result['run_dir'])/'provider-config.json').read_text())==config


def test_cli_default_runs_directory_and_custom_currency(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    config=example_configuration('openai-compatible')
    config['billingUnit']='CNY'
    for m in config['models']:m['pricing']['unit']='CNY'
    source=tmp_path/'providers.json';source.write_text(json.dumps(config))
    output=tmp_path/'dsh.json'
    assert main(['dsh-config','--provider-config',str(source),'--output',str(output),'--mode','live'])==0
    plugin=json.loads(output.read_text())[0]['config']
    assert plugin['runsDir']==str(tmp_path/'.refractagent/runs')
    assert plugin['providerConfig']['billingUnit']=='CNY'


def test_default_reasoning_effort_applies_only_to_a_selected_strategy():
    config = example_configuration('openai-responses')
    for model in config['models']:
        model.pop('requestOptions', None)
    config['defaultReasoningEffort'] = 'medium'
    unscoped = compile_configuration(config)
    assert all('reasoning' not in m.request_options for m in unscoped.manifest.models)
    scoped = compile_configuration(config, strategy='balanced')
    assert all(m.request_options['reasoning']['effort'] == 'medium' for m in scoped.manifest.models)


def test_strategy_scoped_pools_and_default_efforts_reach_each_mode(tmp_path):
    client = Client()
    raw = configuration()
    raw['strategies'] = {
        'economy': {'reasoningEffort': 'low', 'models': ['fast']},
        'quality': {'reasoningEffort': 'high', 'models': ['fast']},
    }
    runs = {}
    for strategy in ('economy', 'quality'):
        runs[strategy] = run_agent({'task': '按模式选模', 'strategy': strategy}, provider_config=raw,
            mode='live', execute_paid_run=True, runs_dir=tmp_path/strategy, client=client)
        assert runs[strategy]['status'] == 'completed', runs[strategy]['issues']
        assert runs[strategy]['model_routes']['answer']['id'] == 'fast'
    assert runs['economy']['model_routes']['answer']['reasoning_effort'] == 'low'
    assert runs['quality']['model_routes']['answer']['reasoning_effort'] == 'high'
    assert runs['economy']['evaluation_model']['reasoning_effort'] == 'low'
    assert runs['quality']['evaluation_model']['reasoning_effort'] == 'high'


def test_model_level_effort_wins_over_strategy_defaults(tmp_path):
    raw = configuration()
    raw['strategies'] = {'quality': {'reasoningEffort': 'high', 'models': ['better']}}
    raw['models'][1]['reasoningEffort'] = 'medium'
    result = run_agent({'task': '显式档位优先', 'strategy': 'quality'}, provider_config=raw,
        mode='live', execute_paid_run=True, runs_dir=tmp_path, client=Client())
    assert result['status'] == 'completed', result['issues']
    assert result['model_routes']['answer']['reasoning_effort'] == 'medium'
    assert result['evaluation_model']['reasoning_effort'] == 'high'


@pytest.mark.parametrize('mutate', [
    lambda c: c.update(strategies={'turbo': {'models': ['fast']}}),
    lambda c: c.update(strategies={'economy': {'models': []}}),
    lambda c: c.update(strategies={'economy': {'models': ['review']}}),
    lambda c: c.update(strategies={'economy': {'models': ['fast', 'fast']}}),
    lambda c: c.update(strategies={'economy': {'reasoningEffort': ''}}),
    lambda c: c.update(defaultReasoningEffort=17),
])
def test_invalid_strategy_configuration_fails_before_dispatch(tmp_path, mutate):
    config = configuration()
    mutate(config)
    client = Client()
    with pytest.raises(ValueError):
        run_agent({'task': '拒绝无效模式配置', 'strategy': 'economy'}, provider_config=config,
                  mode='live', execute_paid_run=True, runs_dir=tmp_path, client=client)
    assert not client.calls and not list(tmp_path.iterdir())


@pytest.mark.parametrize('limits', [{'relaxBudget': 'yes'}, {'unexpected': True}, True])
def test_limit_toggles_are_validated_before_any_artifact(tmp_path, limits):
    with pytest.raises(ValueError):
        run_agent({'task': '非法限制字段', 'limits': limits}, provider_config=configuration(),
                  mode='demo', runs_dir=tmp_path)
    assert not list(tmp_path.iterdir())


def test_relaxed_budget_unblocks_dispatch_and_keeps_the_ledger(tmp_path):
    client = Client()
    result = run_agent({'task': '预算外任务', 'limits': {'relaxBudget': True}},
        provider_config=configuration(), mode='live', execute_paid_run=True, runs_dir=tmp_path,
        production_budget=1e-9, evaluation_budget=1e-9, client=client)
    assert result['status'] == 'completed', result['issues']
    assert result['limits'] == {'relaxBudget': True, 'relaxContext': False}
    assert result['costs']['production'] > 0 and result['costs']['evaluation'] > 0
    blocked = run_agent({'task': '预算内任务'}, provider_config=configuration(), mode='live',
        execute_paid_run=True, runs_dir=tmp_path/'blocked',
        production_budget=1e-9, evaluation_budget=1e-9, client=client)
    assert blocked['status'] != 'completed'


def test_relaxed_context_accepts_long_conversations_within_model_windows(tmp_path):
    raw = configuration()
    for model in raw['models']:
        model['contextWindow'] = 262144
    client = Client()
    result = run_agent({'task': '长上下文任务', 'context': 'x' * 130000, 'limits': {'relaxContext': True}},
        provider_config=raw, mode='live', execute_paid_run=True, runs_dir=tmp_path, client=client)
    assert result['status'] == 'completed', result['issues']
    with pytest.raises(ValueError, match='context'):
        run_agent({'task': '长上下文任务', 'context': 'x' * 130000}, provider_config=raw,
                  mode='demo', runs_dir=tmp_path/'rejected')


def test_dsh_config_can_emit_limit_toggles(tmp_path):
    source = tmp_path/'providers.json'
    assert main(['config-example', '--output', str(source)]) == 0
    target = tmp_path/'relaxed.json'
    assert main(['dsh-config', '--provider-config', str(source), '--output', str(target),
                 '--mode', 'live', '--relax-budget']) == 0
    config = json.loads(target.read_text())[0]['config']
    assert config['limits'] == {'relaxBudget': True, 'relaxContext': False}


def test_models_command_echoes_the_strategy_mapping(tmp_path, capsys):
    config = configuration()
    config['defaultReasoningEffort'] = 'medium'
    config['strategies'] = {'economy': {'reasoningEffort': 'low', 'models': ['fast']}}
    source = tmp_path/'providers.json'
    source.write_text(json.dumps(config))
    assert main(['models', '--provider-config', str(source)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['defaultReasoningEffort'] == 'medium'
    assert result['strategies'] == config['strategies']
