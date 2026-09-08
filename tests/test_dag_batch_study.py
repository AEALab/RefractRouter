"""失败是独立样本结果；样本间不共享停止状态，未知用量停止整批。"""
from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from refractrouter.dag_study import load_study, study_preflight
from refractrouter.dag_study_execution import StudyDemoClient, run_study
from refractrouter.dag_batch_study import compare_batch

from tests.study_fixtures import current_study

ROOT = Path(__file__).resolve().parents[1]


def protocol():
    p,m = current_study(ROOT/'data/benchmarks/dag-routing-v6.json')
    p.pop('calibration_source')
    p['execution_policy']['providerMinIntervalMs']['ark-plan'] = 0
    return p,m


def run_mock(p,m,path,client):
    limits = study_preflight(p,m)['budget']
    with patch('socket.socket', side_effect=AssertionError('禁止网络')):
        return run_study(p,m,path,simulated=False,client=client,
                         production_limit=limits['production'],evaluation_limit=limits['evaluation'])


def test_failed_model_contract_isolated_in_handoff_calibration_and_holdouts(tmp_path):
    class InvalidRisk(StudyDemoClient):
        def complete(self, model, messages, *, json_mode=False):
            answer = super().complete(model,messages,json_mode=json_mode)
            payload = json.loads(messages[-1]['content'])
            if model.model_id=='mid' and payload.get('node_id')=='risk':
                return replace(answer, content='{"result":"值","evidence":"值","assumptions":"值","extra":"多余"}')
            return answer
    p,m=protocol()
    assert study_preflight(p,m)['maximum_calls']==540
    result=run_mock(p,m,tmp_path/'run',InvalidRisk())
    assert result['status']=='completed', result['issues']
    assert len(result['runs'])==114
    assert len([r for r in result['runs'] if r['split']=='handoff'])==6
    assert len([r for r in result['runs'] if r['split']=='test'])==72
    first=json.loads((tmp_path/'run'/result['runs'][0]['result_path']).read_text())
    assert first['status']=='failed' and 'answer' in first['execution']['not_started']
    assert result['comparison']['complete']
    assert all(c['status']=='billed' for c in result['calls'])
    profile=json.loads((tmp_path/'run/profile.json').read_text())
    assert any(e['model_id']=='mid' and e['reason']=='known-contract-rejection' for e in profile['exclusions'])
    obs=json.loads((tmp_path/'run/observations.json').read_text())['observations']
    assert len(obs)==84
    assert any(o['evaluation']['method']=='deterministic-rejection' for o in obs)
    # 无评分的失败保留为缺失，而非混入平均质量。
    assert all(r['score'] is None for r in result['runs'] if r['status']=='failed')
    partial=compare_batch(result['runs'][:-1],p,simulated=False)
    assert not partial['complete'] and all(c['exploratory_signal'] is None for c in partial['comparisons'])


def test_unavailable_node_judges_exclude_profiles_without_aborting_controls(tmp_path):
    class BrokenNodeJudge(StudyDemoClient):
        def complete(self, model, messages, *, json_mode=False):
            response=super().complete(model,messages,json_mode=json_mode)
            if model.role=='judge' and 'node_input' in json.loads(messages[-1]['content']):
                return replace(response,content='{"broken')
            return response
    p,m=protocol()
    result=run_mock(p,m,tmp_path/'run',BrokenNodeJudge())
    assert result['status']=='completed' and result['comparison']['complete']
    profile=json.loads((tmp_path/'run/profile.json').read_text())
    assert profile['candidates']==[]
    assert {r['reason'] for r in profile['exclusions']}=={'missing-independent-evaluation'}
    tests=[r for r in result['runs'] if r['split']=='test']
    assert len(tests)==72
    assert all(r['status']=='no-feasible-route' and r['score'] is None for r in tests if r['method'].endswith(('-a','-b')))
    assert all(r['delivered'] for r in tests if r['method']=='direct-strong')
    assert all(not c['exploratory_signal'] for c in result['comparison']['comparisons'] if c['candidate'].startswith('dag-node'))


def test_infrastructure_failure_keeps_latest_ledger_after_calibration(tmp_path):
    p,m=protocol()
    heldout=next(t['task'] for t in p['tasks'] if t['split']=='test')
    class FailHoldout(StudyDemoClient):
        def complete(self,model,messages,*,json_mode=False):
            if json.loads(messages[-1]['content'])['task']==heldout:
                raise RuntimeError('不得泄露的连接诊断')
            return super().complete(model,messages,json_mode=json_mode)
    result=run_mock(p,m,tmp_path/'run',FailHoldout())
    assert result['status']=='failed' and result['issues']==['RuntimeError']
    assert not result['comparison']['complete']
    assert any(c['status']=='unknown-usage' and 'holdout' in c['label'] for c in result['calls'])
    assert len([r for r in result['runs'] if r['split']=='test'])==1
    for category in ('production','evaluation'):
        assert result['charged'][category]==pytest.approx(sum(c['charged'] for c in result['calls'] if c['category']==category))


def test_real_batch_keeps_failed_baseline_in_outcomes_but_not_quality_pairs():
    archive=ROOT/'reports/dag-decomposition/issue-32-independent-samples-20260908/study'
    result=json.loads((archive/'study-result.json').read_text())
    assert result['status']=='completed' and result['comparison']['complete']
    tests=[r for r in result['runs'] if r['split']=='test']
    assert len(tests)==72
    failed=next(r for r in tests if (r['task_id'],r['repeat'],r['method'])==('cash_holdout_v4',2,'dag-single-b'))
    assert failed['status']=='failed' and failed['score'] is None and not failed['delivered']
    raw=json.loads((archive/failed['result_path']).read_text())
    assert raw['execution']['not_started']==['risk','answer']
    assert len(raw['calls'])==1 and raw['calls'][0]['status']=='billed'
    # 原始 v5 解析将异常零用量记作已结算；原文保留，审计必须单独标为未确认。
    assert failed['deployment_cost']==0 and raw['calls'][0]['input_tokens']==0
    assert raw['calls'][0]['finish_reason']==''
    comparison=next(c for c in result['comparison']['comparisons'] if (c['candidate'],c['baseline'])==('dag-node-b','dag-single-b'))
    assert len(comparison['outcome_pairs'])==9
    assert any(p['task_id']=='cash_holdout_v4' and p['repeat']==2 and not p['baseline_delivered'] for p in comparison['outcome_pairs'])
    assert all((p['task_id'],p['repeat'])!=('cash_holdout_v4',2) for p in comparison['joint_graded_pairs'])
    assert comparison['exploratory_signal'] is False
    # 后续独立任务真实完成，不能将此失败解释为整批提前停止。
    assert len([r for r in tests if r['task_id']=='rewrite_holdout_v4'])==24


def test_reuse_verified_calibration_only_calls_new_handoffs_and_holdouts(tmp_path):
    p,m=current_study(ROOT/'data/benchmarks/dag-routing-v6.json')
    p['execution_policy']['providerMinIntervalMs']['ark-plan']=0
    assert study_preflight(p,m)['maximum_calls']==252
    result=run_mock(p,m,tmp_path/'reuse',StudyDemoClient())
    assert result['status']=='completed' and result['comparison']['complete']
    assert len(result['calls'])==252 and len(result['runs'])==78
    assert not any(c['label'].startswith('probe:') or '--calibration--' in c['label'] for c in result['calls'])
    assert len(json.loads((tmp_path/'reuse/calibration-source-runs.json').read_text()))==36
    assert len(json.loads((tmp_path/'reuse/profile.json').read_text())['candidates'])==8
