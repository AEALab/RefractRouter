"""构造资格只验证发布合同，不代表真实研究已合格；没有模型调用。"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from refractrouter.release_governance import (EVIDENCE, ReleaseStore, digest, frozen_release,
    qualification, validate_release, component_releases)
from tests.test_planning_routing import configuration

CORE = '0'*64


def release(*, label='old', tokens=1024, parameter='max_completion_tokens'):
    config={'schemaVersion':'refractrouter-gateway-config-v2','planningRouting':configuration('static'),
        'providers':{'fake':{'baseURL':'http://127.0.0.1:1/'+label,'tokenLimitParameter':parameter}}}
    for m in config['planningRouting']['models']:
        m['maxOutputTokens']=tokens
        m['contextWindow']=max(32000,tokens+32000)
    versions={'providers':{'fake':'fake-provider-v1'}, 'models':{m['id']:m['id']+'-v1'
        for m in config['planningRouting']['models']},'outputSemantics':{'fake':{
            'parameter':parameter,'scope':'answer-and-reasoning-total','sourceSha256':'a'*64}}}
    return frozen_release(config,versions,implementation=CORE)


def evidence(snapshot,n=100):
    return {'schemaVersion':EVIDENCE,'kind':'empirical-independent-holdout','strategy':snapshot['strategy'],
        'contextSha256':snapshot['contextSha256'],'sourceAuditSha256':'b'*64,'toolsSha256':'c'*64,
        'hostSha256':'d'*64,'deliverySha256':'e'*64,'independenceAudited':True,'hiddenIsolationAudited':True,
        'billingUnit':snapshot['billingUnit'],'costAuditSha256':'f'*64,
        'costScope':'all-execution-routing-online-review-attempts','researchScoringReportedSeparately':True,
        'criticalRegressions':0,'componentEvidence':{},'incrementalRows':{},'rows':[{'taskId':str(i),'half':i%2,
            'baselinePassed':True,'candidatePassed':True,'completedPair':True,'knownCost':True,
            'baselineCost':1,'candidateCost':.5} for i in range(n)]}


def expires(): return (datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()


def test_snapshot_binds_schema_prices_versions_and_rejects_tampering():
    snapshot=release()
    assert snapshot['nativeBudgetVerified']
    assert validate_release(snapshot,implementation=CORE)==snapshot
    changed=deepcopy(snapshot);changed['configuration']['planningRouting']['models'][0]['inputPer1k']=10
    with pytest.raises(ValueError): validate_release(changed)
    with pytest.raises(ValueError,match='漂移'): validate_release(snapshot,implementation='1'*64)


@pytest.mark.parametrize('tokens,parameter', [(131072,'max_tokens'),(131072,'max_completion_tokens'),(1024,'max_tokens')])
def test_native_capacity_unknown_is_rejected_without_lowering_limit(tmp_path,tokens,parameter):
    snapshot=release(tokens=tokens,parameter=parameter)
    assert not snapshot['nativeBudgetVerified']
    assert snapshot['configuration']['planningRouting']['models'][0]['maxOutputTokens']==tokens
    assert not qualification(snapshot,evidence(snapshot))['qualified']
    with pytest.raises(ValueError,match='#223'):
        ReleaseStore.create(tmp_path/'store',snapshot,actor='测试维护者',implementation=CORE)


def test_credentials_cannot_be_frozen():
    snapshot=release();config=deepcopy(snapshot['configuration']);config['providers']['fake']['apiKey']='不可保存'
    with pytest.raises(ValueError,match='密钥'): frozen_release(config,snapshot['versions'],implementation=CORE)


def test_missing_simulated_or_small_evidence_never_becomes_qualified():
    snapshot=release()
    assert not qualification(snapshot,None)['qualified']
    assert not qualification(snapshot,evidence(snapshot,24))['qualified']
    simulated=evidence(snapshot);simulated['kind']='simulation'
    assert not qualification(snapshot,simulated)['qualified']
    # 以下是构造数据验证算术正路径，不是本项目已有真实资格。
    assert qualification(snapshot,evidence(snapshot),implementation=CORE)['qualified']


def test_new_core_cannot_reuse_prior_implementation_evidence():
    old=release();proof=evidence(old)
    changed=frozen_release(old['configuration'],old['versions'],implementation='1'*64)
    assert not qualification(changed,proof,implementation='1'*64)['qualified']


def test_mixed_units_cannot_be_hidden_in_single_cost_column():
    old=release();config=deepcopy(old['configuration']);raw=config['planningRouting']
    raw.update(schemaVersion='refractagent-planning-v2',billingUnit='CNY',maxProductionCostByUnit={'CNY':10,'AFP':10})
    for model in raw['models']:model['billingUnit']='AFP' if model['id']=='large' else 'CNY'
    mixed=frozen_release(config,old['versions'],implementation=CORE)
    assert mixed['billingUnits']==['AFP','CNY']
    assert not qualification(mixed,evidence(mixed))['qualified']


def test_jev_non_model_judge_cost_is_included_in_release_units():
    from tests.test_jev_planning_integration import configuration as jev_configuration
    old=release();config=deepcopy(old['configuration']);raw=jev_configuration('task')
    raw['billingUnit']='AFP';raw['maxProductionCostByUnit']={'CNY':10,'AFP':1000}
    for model in raw['models']:model['billingUnit']='AFP'
    config['planningRouting']=raw
    versions=deepcopy(old['versions']);versions['models']={m['id']:m['id']+'-v1' for m in raw['models']}
    mixed=frozen_release(config,versions,implementation=CORE)
    assert mixed['billingUnits']==['AFP','CNY']
    assert not qualification(mixed,evidence(mixed))['qualified']


def composite_snapshot():
    from tests.test_planning_routing import composite_configuration
    base=release();config=deepcopy(base['configuration'])
    config['planningRouting']=composite_configuration()
    return frozen_release(config,base['versions'],implementation=CORE)


def composite_evidence(snapshot):
    proof=evidence(snapshot);effective=component_releases(snapshot)
    proof['componentEvidence']={'task':evidence(effective['task']),
        'stage':{initial:evidence(profile) for initial,profile in effective['stage'].items()}}
    for component in [proof['componentEvidence']['task'],*proof['componentEvidence']['stage'].values()]:
        for row in component['rows']:row['candidateCost']=.75
    proof['incrementalRows']={strategy:[{**r,'baselineCost':.75} for r in proof['rows']]
        for strategy in ('task','stage')}
    return proof


def test_composite_requires_actual_components_and_incremental_comparisons():
    snapshot=composite_snapshot()
    proof=composite_evidence(snapshot)
    assert qualification(snapshot,proof,implementation=CORE)['qualified']
    proof['incrementalRows']['task'][0]['candidateCost']=.4
    assert not qualification(snapshot,proof,implementation=CORE)['qualified']
    proof=composite_evidence(snapshot)
    for row in proof['componentEvidence']['task']['rows']:row['candidateCost']=.2
    assert not qualification(snapshot,proof,implementation=CORE)['qualified']
    proof=composite_evidence(snapshot)
    for row in proof['incrementalRows']['stage']:row['baselineCost']=row['candidateCost']
    assert not qualification(snapshot,proof,implementation=CORE)['qualified']
    proof=composite_evidence(snapshot);proof['componentEvidence']['stage']={}
    assert not qualification(snapshot,proof,implementation=CORE)['qualified']


def test_top_level_task_stage_evidence_cannot_approve_different_embedded_policies():
    snapshot=composite_snapshot();config=deepcopy(snapshot['configuration']);raw=config['planningRouting']
    raw['task']={**raw['composite'],'fallback':raw['composite']['takeover']}
    raw['task'].pop('takeover');raw['task'].pop('stage');raw['task']['threshold']=.8
    raw['parameters']={'threshold':.01}
    raw['composite']['threshold']=.93;raw['composite']['stage']['threshold']=.99
    snapshot=frozen_release(config,snapshot['versions'],implementation=CORE)
    proof=composite_evidence(snapshot)
    top_task=deepcopy(config);top_task['planningRouting']['defaultStrategy']='task'
    top_stage=deepcopy(config);top_stage['planningRouting']['defaultStrategy']='stage'
    proof['componentEvidence']['task']=evidence(frozen_release(top_task,snapshot['versions'],implementation=CORE))
    proof['componentEvidence']['stage']['small']=evidence(frozen_release(top_stage,snapshot['versions'],implementation=CORE))
    assert not qualification(snapshot,proof,implementation=CORE)['qualified']


@pytest.mark.parametrize('change', ['critical','unknown-cost','unknown-quality','wrong-context','wrong-kind','wrong-unit','partial-cost'])
def test_quality_cost_and_context_failures_block_release(change):
    snapshot=release();proof=evidence(snapshot)
    if change=='critical':proof['criticalRegressions']=1
    if change=='unknown-cost':proof['rows'][0]['knownCost']=False
    if change=='unknown-quality':proof['rows'][0]['candidatePassed']=None
    if change=='wrong-context':proof['contextSha256']='f'*64
    if change=='wrong-kind':proof['kind']='development'
    if change=='wrong-unit':proof['billingUnit']='AFP' if snapshot['billingUnit']!='AFP' else 'CNY'
    if change=='partial-cost':proof['costScope']='only-successful-generations'
    assert not qualification(snapshot,proof)['qualified']


def test_finite_trial_pins_old_tasks_and_restart_does_not_refund_slots(tmp_path):
    old,new=release(),release(label='new')
    store=ReleaseStore.create(tmp_path/'store',old,actor='维护者',implementation=CORE)
    assert store.add(new,evidence(new),actor='维护者')['qualified']
    trial=store.start_trial(new['releaseSha256'],max_tasks=1,expires=expires(),actor='维护者',explicit=True)
    first=store.assign(digest('one'),{'task':'one'})
    assert first['releaseSha256']==new['releaseSha256'] and first['trialId']==trial
    restarted=ReleaseStore(tmp_path/'store',implementation=CORE)
    assert restarted.assign(digest('one'),{'task':'one'})['existing']
    assert restarted.assign(digest('two'),{'task':'two'})['releaseSha256']==old['releaseSha256']
    assert restarted.history()['trials'][0]['used']==1
    restarted.stop_trial(actor='维护者',reason='显式停止')
    assert restarted.assign(digest('one'),{'task':'one'})['releaseSha256']==new['releaseSha256']
    assert restarted.assign(digest('three'),{'task':'three'})['releaseSha256']==old['releaseSha256']


def test_invalidated_qualification_cannot_restart_same_trial(tmp_path):
    old,new=release(),release(label='new')
    store=ReleaseStore.create(tmp_path/'store',old,actor='维护者',implementation=CORE)
    store.add(new,evidence(new),actor='维护者')
    store.start_trial(new['releaseSha256'],max_tasks=2,expires=expires(),actor='维护者',explicit=True)
    store.invalidate(new['releaseSha256'],actor='维护者',reason='provider版本漂移')
    with pytest.raises(ValueError,match='待复核'):
        store.start_trial(new['releaseSha256'],max_tasks=2,expires=expires(),actor='维护者',explicit=True)
    assert store.assign(digest('after-drift'),{'task':'after-drift'})['releaseSha256']==old['releaseSha256']


def test_database_loss_or_reinitialization_does_not_reset_history(tmp_path):
    snapshot=release();root=tmp_path/'store'
    store=ReleaseStore.create(root,snapshot,actor='维护者',implementation=CORE)
    with pytest.raises(FileExistsError):ReleaseStore.create(root,snapshot,actor='维护者',implementation=CORE)
    store.path.unlink()
    with pytest.raises(ValueError):ReleaseStore(root,implementation=CORE)
    with pytest.raises(FileExistsError):ReleaseStore.create(root,snapshot,actor='维护者',implementation=CORE)


def test_no_automatic_trial_and_no_invented_parent_budget(tmp_path):
    snapshot=release();store=ReleaseStore.create(tmp_path/'store',snapshot,actor='维护者',implementation=CORE)
    with pytest.raises(ValueError,match='明确开启'):
        store.start_trial(snapshot['releaseSha256'],max_tasks=1,expires=expires(),actor='维护者')
    history=store.history()
    assert not history['parentChildSharedBudgetEnforced']
    assert history['coverage']=='managed-agent-only'
