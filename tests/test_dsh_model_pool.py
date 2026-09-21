"""DSH 模型池只编译目录事实与用户声明；全程无网络、无模型调用。"""
import json
from io import StringIO
from pathlib import Path
import sys
import tomllib

import pytest

from refractrouter.dsh_model_pool import compile_dsh_model_pool, load_frozen_profiles
from refractrouter.agent import run_agent
from refractrouter.agent_cli import main


def snapshot(*models):
    return {'schemaVersion':'refractagent-dsh-catalog-v1','failures':[], 'routes':[
        {'provider':provider,'model':model,'contextWindow':context,'maxOutputTokens':output,
         'reasoningEfforts':['low','high']} for provider,model,context,output in models]}


def full_profiles():
    return {'schema_version':'refractrouter-model-profiles-v1','profiles':[
        {'provider':'cloud','model':'strong','pricing':{'unit':'USD','inputPer1k':.01,'cachedInputPer1k':.005,'outputPer1k':.02},
         'quality':95,'latencyMs':2000,'sources':[{'kind':'test'}]},
        {'provider':'local','model':'fast','pricing':{'unit':'USD','inputPer1k':.001,'outputPer1k':.002},
         'quality':82,'latencyMs':300,'sources':[{'kind':'test'}]},
    ]}


def pool():
    return {'schemaVersion':'refractagent-dsh-model-pool-v1','billingUnit':'USD',
        'security':{'dataMode':'synthetic','sensitiveTerms':[],'classifier':{'enabled':True}},'routes':[
        {'provider':'cloud','model':'strong','deployment':'trusted-cloud','trustPolicy':'team'},
        {'provider':'local','model':'fast','deployment':'local'},
    ],'trustPolicies':[{'id':'team','residency':'CN','auditLogging':True,'allowsSensitiveData':True}]}


def test_auto_roles_keep_judge_out_of_worker_pool_and_record_sources():
    config,provenance=compile_dsh_model_pool(pool(),snapshot(
        ('cloud','strong',262144,8192),('local','fast',131072,4096)),profiles=full_profiles())
    roles={model['model']:model['roles'] for model in config['models']}
    assert roles['strong']==['planner','judge','classifier']
    assert roles['fast']==['worker']
    assert provenance['cloud/strong']['profile']=='frozen-public-profile'
    assert provenance['cloud/strong']['samples']==0
    assert provenance['cloud/strong']['assigned_roles']==['planner','judge','classifier']
    assert provenance['cloud/strong']['independent_judge'] is True
    assert {(row['dshProvider'],row['deployment']) for row in config['providers']}=={
        ('cloud','trusted-cloud'),('local','local')}


def test_role_overrides_use_route_identity_and_worker_pool_selector():
    raw=pool();raw['roleOverrides']={
        'planner':'local/fast','judge':'cloud/strong','classifier':'local/fast','workers':['local/fast']}
    config,_=compile_dsh_model_pool(raw,snapshot(
        ('cloud','strong',262144,8192),('local','fast',131072,4096)),profiles=full_profiles())
    roles={model['model']:model['roles'] for model in config['models']}
    assert roles=={'strong':['judge'],'fast':['planner','worker','classifier']}


def test_single_user_declared_route_requires_explicit_shared_judge_opt_in():
    raw={'schemaVersion':'refractagent-dsh-model-pool-v1','billingUnit':'USD',
        'security':{'dataMode':'synthetic','sensitiveTerms':[],'classifier':{'enabled':True}},
        'routes':[{'provider':'deepseek-official','model':'deepseek-v4-flash','deployment':'local',
            'overrides':{'inputPer1k':.0003,'cachedInputPer1k':.000006,'outputPer1k':.0012,
                'quality':84,'latencyMs':1800,'note':'开发测试临时替代，未经项目校准'}}]}
    catalog=snapshot(('deepseek-official','deepseek-v4-flash',131072,8192))
    with pytest.raises(ValueError,match='allowSharedJudge'):
        compile_dsh_model_pool(raw,catalog,profiles=full_profiles())
    raw['allowSharedJudge']=True
    config,provenance=compile_dsh_model_pool(raw,catalog,profiles=full_profiles())
    assert config['models'][0]['roles']==['planner','worker','judge','classifier']
    route=provenance['deepseek-official/deepseek-v4-flash']
    assert route['profile']=='user-declared-uncalibrated'
    assert route['assigned_roles']==['planner','worker','judge','classifier']
    assert route['independent_judge'] is False


def test_unknown_route_requires_complete_manual_profile_and_is_marked_uncalibrated():
    raw=pool();raw['routes'][1]['model']='private-model'
    catalog=snapshot(('cloud','strong',262144,8192),('local','private-model',131072,4096))
    with pytest.raises(ValueError,match='complete manual overrides'):
        compile_dsh_model_pool(raw,catalog,profiles=full_profiles())
    raw['routes'][1]['overrides']={'inputPer1k':0,'cachedInputPer1k':0,'outputPer1k':0,
        'quality':80,'latencyMs':500,'note':'本地声明'}
    _,provenance=compile_dsh_model_pool(raw,catalog,profiles=full_profiles())
    assert provenance['local/private-model']['profile']=='user-declared-uncalibrated'
    assert provenance['local/private-model']['overrides']==[
        'cachedInputPer1k','inputPer1k','latencyMs','note','outputPer1k','quality']


def test_user_override_wins_without_mutating_frozen_profile_and_deleted_route_fails():
    profiles=full_profiles();raw=pool();raw['routes'][0]['overrides']={'quality':88,'latencyMs':99}
    config,provenance=compile_dsh_model_pool(raw,snapshot(
        ('cloud','strong',262144,8192),('local','fast',131072,4096)),profiles=profiles)
    strong=next(model for model in config['models'] if model['model']=='strong')
    assert strong['roles']==['planner','judge','classifier']
    assert provenance['cloud/strong']['overrides']==['latencyMs','quality']
    assert profiles['profiles'][0]['quality']==95
    with pytest.raises(ValueError,match='route is unavailable'):
        compile_dsh_model_pool(raw,snapshot(('local','fast',131072,4096)),profiles=profiles)


def test_repository_profile_freezes_all_current_dsh_prices_without_quality_claims():
    root=Path(__file__).resolve().parents[1]
    raw=load_frozen_profiles(root/'data/model-profiles-v2.json')
    assert raw['schema_version']=='refractrouter-model-profiles-v2'
    identities={(row['provider'],row['model']) for row in raw['profiles']}
    assert identities=={
        ('deepseek-official','deepseek-flash'),
        ('deepseek-official','deepseek-v4-flash'),
        ('deepseek-official','deepseek-v4-flash-vision-exp'),
        ('deepseek-official','deepseek-v4-pro'),
        ('ark','deepseek-v4-flash'),('ark','deepseek-v4-pro'),('ark','glm-5.3'),
        ('ark','kimi-k3'),('ark','minimax-m3')}
    assert all(row['quality'] is None and row['latencyMs'] is None
               for row in raw['profiles'])
    direct=next(row for row in raw['profiles']
                if (row['provider'],row['model'])==('deepseek-official','deepseek-v4-flash'))
    assert direct['effective_model']=='DeepSeek-V4.1-Flash'
    assert direct['pricing_basis']['equivalence']=='official-alias'
    assert direct['pricing']=={'unit':'USD','inputPer1k':.0003,
                               'cachedInputPer1k':.000006,'outputPer1k':.0012}
    ark=next(row for row in raw['profiles']
             if (row['provider'],row['model'])==('ark','deepseek-v4-flash'))
    assert ark['pricing_basis']['kind']=='manufacturer-reference'
    assert ark['pricing_basis']['equivalence']=='unverified'
    assert ark['pricing_basis']['actualProviderBilling'] is False
    kimi=next(row for row in raw['profiles']
              if (row['provider'],row['model'])==('ark','kimi-k3'))
    assert kimi['pricing']['inputPer1k']==.006
    assert kimi['pricing_schedule']['tiers'][0]['prices']['cacheWritePer1k']==.003
    minimax=next(row for row in raw['profiles']
                 if (row['provider'],row['model'])==('ark','minimax-m3'))
    assert minimax['pricing_materialization']['selectedTier']=='standard-over-512k'
    assert len(minimax['pricing_schedule']['tiers'])==4
    package=tomllib.loads((root/'pyproject.toml').read_text())
    assert 'data/model-profiles-v1.json' in package['tool']['setuptools']['data-files']['share/refractrouter']
    assert 'data/model-profiles-v2.json' in package['tool']['setuptools']['data-files']['share/refractrouter']


def test_v2_profile_supplies_prices_but_still_requires_quality_and_latency():
    profiles=load_frozen_profiles()
    raw={'schemaVersion':'refractagent-dsh-model-pool-v1','billingUnit':'USD',
        'security':{'dataMode':'synthetic','sensitiveTerms':[],'classifier':{'enabled':True}},
        'allowSharedJudge':True,
        'routes':[{'provider':'deepseek-official','model':'deepseek-v4-pro','deployment':'local',
                   'overrides':{'quality':91,'latencyMs':2200}}]}
    config,provenance=compile_dsh_model_pool(raw,snapshot(
        ('deepseek-official','deepseek-v4-pro',1048576,393216)),profiles=profiles)
    model=config['models'][0]
    assert model['pricing']=={'unit':'USD','inputPer1k':.00132,
                              'cachedInputPer1k':.000044,'outputPer1k':.00396}
    route=provenance['deepseek-official/deepseek-v4-pro']
    assert route['pricing_basis']['kind']=='direct-provider-public-price'
    assert route['pricing_materialization']['selectedTier']=='peak'
    assert route['overrides']==['latencyMs','quality']


def test_v2_profile_rejects_a_materialized_price_not_in_its_selected_tier(tmp_path):
    root=Path(__file__).resolve().parents[1]
    raw=json.loads((root/'data/model-profiles-v2.json').read_text())
    raw['profiles'][0]['pricing']['inputPer1k']=999
    path=tmp_path/'profiles.json'
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError,match='selected conservative tier'):
        load_frozen_profiles(path)


def test_run_evidence_contains_effective_profile_provenance(tmp_path):
    config,provenance=compile_dsh_model_pool(pool(),snapshot(
        ('cloud','strong',262144,8192),('local','fast',131072,4096)),profiles=full_profiles())
    result=run_agent({'task':'零调用预览','template':'auto'},mode='preflight',runs_dir=tmp_path,
        provider_config=config,model_profile_provenance=provenance)
    directory=Path(result['run_dir'])
    assert result['model_profile_provenance']==provenance
    assert json.loads((directory/'model-profile-provenance.json').read_text())==provenance
    assert json.loads((directory/'summary.json').read_text())['model_profile_provenance']==provenance


def test_cli_compiles_dsh_snapshot_with_packaged_frozen_profile(tmp_path,monkeypatch,capsys):
    request={'task':'目录合同预检','template':'auto','dshModelPool':{
        'schemaVersion':'refractagent-dsh-model-pool-v1','billingUnit':'USD',
        'security':{'dataMode':'synthetic'},
        'trustPolicies':[{'id':'team','residency':'CN','auditLogging':True,'allowsSensitiveData':True}],
        'routes':[
            {'provider':'deepseek','model':'deepseek-flash','deployment':'trusted-cloud','trustPolicy':'team',
             'overrides':{'quality':90,'latencyMs':600}},
            {'provider':'local','model':'private','deployment':'local','overrides':{
                'inputPer1k':0,'outputPer1k':0,'quality':80,'latencyMs':100}},
        ]},'dshCatalogSnapshot':snapshot(
            ('deepseek','deepseek-flash',131072,8192),('local','private',65536,4096))}
    monkeypatch.setattr(sys,'stdin',StringIO(json.dumps(request)))
    assert main(['run','--request-stdin','--mode','preflight','--runs-dir',str(tmp_path)])==0
    result=json.loads(capsys.readouterr().out)
    assert result['model_profile_provenance']['deepseek/deepseek-flash']['profile']=='frozen-public-profile'
    assert result['model_profile_provenance']['local/private']['profile']=='user-declared-uncalibrated'
