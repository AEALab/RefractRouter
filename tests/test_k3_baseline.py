from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from experiments.run_k3_baseline import main, read_bundle
from experiments.run_execution_modes import FixtureAdapter
from refractrouter.blind_review import import_reviews, FINAL_LIMITS
from refractrouter.cost_selection import select_cost_effective
from refractrouter.dataset import load_benchmark_dataset
from refractrouter.k3_experiment import chinese_task, prepare, compose, finalize, fixture_reviews
from refractrouter.manifest import load_model_manifest
from refractrouter.review_calibration import build_calibration, check_calibration

ROOT = Path(__file__).resolve().parents[1]


def setup():
    task = chinese_task(load_benchmark_dataset(ROOT/'data/benchmarks/v0.1.json',ROOT/'data/tasks',ROOT/'data/source_packs').all_tasks[0])
    manifest = load_model_manifest(ROOT/'data/model-manifests/volcengine-agent-plan.json')
    adapter = FixtureAdapter(manifest.candidate_registry())
    return task, manifest, adapter


@pytest.fixture
def prepared():
    task, manifest, adapter = setup()
    return task, manifest, adapter, prepare(task,manifest,adapter,simulation=True)


def test_k3_is_only_the_whole_task_baseline_and_generation_has_no_expected_answers(prepared):
    task, manifest, adapter, state = prepared
    assert not task.expected_claims and '执行摘要' in task.required_sections
    assert state['baseline_model']['api_model']=='kimi-k3'
    assert len(state['baseline']['node_results'])==1
    assert all(m['api_model']!='kimi-k3' for m in state['models'])
    assert adapter.calls==29 and len(state['rows'])==21
    payload=json.dumps(state['node_packet'])
    assert not any(k in payload for k in ['api_model','model_id','total_cost','expected_claims'])
    assert not any(m.api_model in payload for m in manifest.models)


def test_cost_policy_selects_cheaper_qualified_candidate_and_refuses_unqualified(prepared):
    task, _, adapter, state = prepared
    response=fixture_reviews(state['node_packet'])
    # best strong=94, cheap=90 lies inside the five-point band; mid=93 costs more.
    for row in response['reviews']:
        model=state['node_mapping']['sample_records'][row['sample_id']].split(':')[-1]
        row['scores']={'correctness':{'cheap':34,'mid':37,'strong':38}[model],
                       'grounding':28,'completeness':18,'downstream_utility':10}
    composed=compose(state,response,adapter)
    assert set(composed['selection']['assignments'].values())=={'cheap'}
    assert adapter.calls==36
    high=select_cost_effective(composed['rows'],task=task,model_ids=['cheap','mid','strong'],quality_floor=99)
    assert not high['route_executable'] and not high['assignments']
    near=select_cost_effective(composed['rows'],task=task,model_ids=['cheap','mid','strong'],max_quality_gap=0)
    assert set(near['assignments'].values())=={'strong'}
    bad=deepcopy(composed['rows']);bad.pop()
    assert not select_cost_effective(bad,task=task,model_ids=['cheap','mid','strong'])['route_executable']


@pytest.mark.parametrize('kind',['self-judge','nan','boolean','missing','duplicate','hash','quote','fixture'])
def test_review_import_rejects_invalid_or_nonindependent_evidence(prepared,kind):
    _,_,_,state=prepared
    public=state['node_packet']; response=fixture_reviews(public)
    response['reviewer']={'kind':'model','id':'external-reviewer'}
    row=response['reviews'][0]
    if kind=='self-judge': response['reviewer']['id']='provider/kimi-k3'
    elif kind=='nan': row['scores']['correctness']=float('nan')
    elif kind=='boolean': row['scores']['correctness']=True
    elif kind=='missing': response['reviews'].pop()
    elif kind=='duplicate': response['reviews'].append(deepcopy(row))
    elif kind=='hash': response['packet_sha256']='wrong'
    elif kind=='quote': row['evidence_quote']='这段原文并不存在'
    else: response['reviewer']['kind']='fixture'
    with pytest.raises(ValueError):import_reviews(public,response,forbidden_models=['kimi-k3'])


def test_missing_substantive_comparison_cannot_keep_a_perfect_effective_score():
    task,_,_=setup();bundle=build_calibration(task,ROOT)
    response=fixture_reviews(bundle['public']);response['reviewer']={'kind':'human','id':'reviewer-test'}
    assert not check_calibration(bundle,response,forbidden_models=['kimi-k3'])['passed']
    sid=next(s for s,k in bundle['private']['sample_records'].items() if k=='missing-comparison')
    row=next(r for r in response['reviews'] if r['sample_id']==sid)
    row['task_checks']['substantive_comparison']=False
    review=import_reviews(bundle['public'],response,forbidden_models=['kimi-k3'])[sid]
    assert review['scores']==FINAL_LIMITS and review['final_score']==50
    assert check_calibration(bundle,response,forbidden_models=['kimi-k3'])['passed']
    row['task_checks']=None
    with pytest.raises(ValueError):import_reviews(bundle['public'],response,forbidden_models=['kimi-k3'])


def test_costs_include_selection_and_no_single_repeat_go(prepared):
    _,_,adapter,state=prepared
    result=compose(state,fixture_reviews(state['node_packet']),adapter)
    summary=finalize(result,fixture_reviews(result['final_packet']),calibration_passed=True)
    assert summary['decision']=='Simulation-only'
    assert summary['routed_first_use_cost']>summary['routed_cost']
    assert summary['total_production_cost']==pytest.approx(state['prepare_cost']+result['routed_cost'])
    assert summary['external_review_cost'] is None
    assert summary['first_use_cost_reduction_percent'] < summary['cost_reduction_percent']
    assert not summary['candidate_signal']
    assert summary['first_use_latency_ms']>=summary['routed_latency_ms']
    assert finalize(result,fixture_reviews(result['final_packet']),calibration_passed=False)['quality_delta'] is None


def test_preflight_and_offline_never_construct_network_client(tmp_path):
    with patch('experiments.run_k3_baseline.OpenAICompatibleClient') as client:
        assert main(['--output-dir',str(tmp_path/'preflight')])==0
        assert main(['--mode','offline','--output-dir',str(tmp_path/'offline')])==0
    client.assert_not_called()
    p=json.loads((tmp_path/'preflight/preflight.json').read_text())
    assert p['call_plan']['production_model_calls']==29
    assert p['whole_experiment']['production_calls']==36
    assert p['whole_experiment']['production_estimate']==178.61
    assert p['minimum_production_limit']==131.68
    s=json.loads((tmp_path/'offline/benchmark-summary.json').read_text())
    assert s['fixture_production_calls']==36 and s['actual_paid_cost']==0
    assert not s['calibration_passed'] and s['decision']=='Simulation-only'
    read_bundle(tmp_path/'offline')
    with pytest.raises(SystemExit):main(['--output-dir',str(tmp_path/'offline')])
    (tmp_path/'offline/private/state.json').write_text('{}')
    with pytest.raises(ValueError):read_bundle(tmp_path/'offline')


def test_real_stages_require_calibration_and_preserve_two_separate_review_handoffs(tmp_path,monkeypatch):
    task,manifest,adapter=setup()
    initial=tmp_path/'initial'; main(['--output-dir',str(initial)])
    state=read_bundle(initial)
    calibration=fixture_reviews(state['calibration']['public'])
    calibration['reviewer']={'kind':'human','id':'offline-test-human'}
    sid=next(s for s,k in state['calibration']['private']['sample_records'].items() if k=='missing-comparison')
    next(r for r in calibration['reviews'] if r['sample_id']==sid)['task_checks']['substantive_comparison']=False
    reviews=tmp_path/'reviews.json';reviews.write_text(json.dumps({'calibration':calibration}))
    monkeypatch.setenv('REFRACTROUTER_K3_BASELINE_HOST','dsh-plugin')
    monkeypatch.setenv('CODEX_ARK_API_KEY','test-only')
    def run(stage,input_dir,output):
        return main(['--stage',stage,'--input-dir',str(input_dir),'--reviews',str(reviews),
                     '--output-dir',str(output),*(['--execute-paid-run','--max-production-cost','200',
                     '--max-evaluation-cost','0'] if stage!='finalize' else [])])
    with patch('experiments.run_k3_baseline.OpenAICompatibleClient'), patch('experiments.run_k3_baseline.OpenAICompatibleAdapter',return_value=adapter):
        assert run('prepare',initial,tmp_path/'prepared')==0
        state=read_bundle(tmp_path/'prepared');assert state['stage']=='node-review-ready'
        assert len((tmp_path/'prepared/production-results.ndjson').read_text().splitlines())==29
        nodes=fixture_reviews(state['node_packet']);nodes['reviewer']=calibration['reviewer']
        changed=deepcopy(calibration);changed['reviewer']['id']='different-reviewer'
        reviews.write_text(json.dumps({'calibration':changed,'nodes':nodes}))
        with pytest.raises(SystemExit):run('compose',tmp_path/'prepared',tmp_path/'changed-reviewer')
        assert adapter.calls==29
        reviews.write_text(json.dumps({'calibration':calibration,'nodes':nodes}))
        assert run('compose',tmp_path/'prepared',tmp_path/'composed')==0
        state=read_bundle(tmp_path/'composed');assert state['stage']=='final-review-ready'
        final=fixture_reviews(state['final_packet']);final['reviewer']=calibration['reviewer']
        reviews.write_text(json.dumps({'calibration':calibration,'final':final}))
        assert run('finalize',tmp_path/'composed',tmp_path/'final')==0
    assert adapter.calls==36
    summary=json.loads((tmp_path/'final/benchmark-summary.json').read_text())
    assert summary['decision']=='Insufficient-evidence'
    assert read_bundle(tmp_path/'final')['stage']=='complete'


def test_index_must_cover_state_even_if_other_artifacts_are_intact(tmp_path):
    main(['--output-dir',str(tmp_path)])
    index=json.loads((tmp_path/'evidence-index.json').read_text())
    del index['artifacts']['private/state.json']
    (tmp_path/'evidence-index.json').write_text(json.dumps(index))
    with pytest.raises(ValueError):read_bundle(tmp_path)


def test_quality_floor_failure_stops_before_composed_calls(prepared):
    _,_,adapter,state=prepared
    result=compose(state,fixture_reviews(state['node_packet']),adapter,quality_floor=99)
    assert result['stage']=='blocked' and adapter.calls==29


def test_paid_without_review_is_blocked_before_client(tmp_path):
    with patch('experiments.run_k3_baseline.OpenAICompatibleClient') as client:
        with pytest.raises(SystemExit):main(['--execute-paid-run','--output-dir',str(tmp_path)])
    client.assert_not_called()
