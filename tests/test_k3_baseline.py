from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from refractrouter.schemas import NodeResult

from experiments.run_k3_baseline import main, read_bundle, save_bundle, bind_input
from experiments.run_execution_modes import FixtureAdapter
from refractrouter.blind_review import import_reviews, FINAL_LIMITS, digest
from refractrouter.cost_selection import select_cost_effective
from refractrouter.dataset import load_benchmark_dataset
from refractrouter.k3_experiment import chinese_task, prepare, resume_baseline, compose, finalize, fixture_reviews
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


@pytest.mark.parametrize('split_baseline', [False, True])
def test_real_stages_require_calibration_and_preserve_two_separate_review_handoffs(tmp_path,monkeypatch,split_baseline):
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
        if split_baseline:
            assert run('baseline',initial,tmp_path/'baseline')==0
            baseline_state=read_bundle(tmp_path/'baseline')
            assert adapter.calls==1
            with patch.object(adapter,'invoke',wraps=adapter.invoke) as calls:
                assert run('resume',tmp_path/'baseline',tmp_path/'prepared')==0
            assert len(calls.call_args_list)==28
            assert all(c.args[-1].api_model!='kimi-k3' for c in calls.call_args_list)
            resumed=read_bundle(tmp_path/'prepared')
            assert resumed['baseline']==baseline_state['baseline']
            summary=json.loads((tmp_path/'prepared/benchmark-summary.json').read_text())
            assert summary['imported_production_cost']==baseline_state['prepare_cost']
            assert summary['cumulative_prepare_cost']==pytest.approx(
                summary['imported_production_cost']+summary['stage_production_cost'])
        else:
            assert run('prepare',initial,tmp_path/'prepared')==0
        state=read_bundle(tmp_path/'prepared');assert state['stage']=='node-review-ready'
        assert len((tmp_path/'prepared/production-results.ndjson').read_text().splitlines())==(28 if split_baseline else 29)
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


def test_baseline_only_never_runs_reference_or_probes(tmp_path):
    task, manifest, adapter=setup()
    state=prepare(task,manifest,adapter,simulation=True,baseline_only=True)
    assert state['stage']=='baseline-ready' and adapter.calls==1
    assert state['reference'] is None and state['rows']==[] and state['node_packet'] is None
    with patch('experiments.run_k3_baseline.OpenAICompatibleClient') as client:
        assert main(['--stage','baseline','--mode','offline','--output-dir',str(tmp_path)])==0
    client.assert_not_called()
    summary=json.loads((tmp_path/'benchmark-summary.json').read_text())
    preflight=json.loads((tmp_path/'preflight.json').read_text())
    assert summary['fixture_production_calls']==1 and summary['actual_paid_cost']==0
    assert preflight['call_plan']['total_model_calls']==1
    assert preflight['request_timeout_seconds']==300


def test_paid_without_review_is_blocked_before_client(tmp_path):
    with patch('experiments.run_k3_baseline.OpenAICompatibleClient') as client:
        with pytest.raises(SystemExit):main(['--execute-paid-run','--output-dir',str(tmp_path)])
    client.assert_not_called()


@pytest.mark.parametrize('failure', ['timeout', 'invalid-html'])
def test_baseline_failure_stops_before_any_reference_or_probe(failure):
    task, manifest, _ = setup()
    calls = []
    class FailedBaseline:
        def invoke(self, task, node, prompt, context, model):
            calls.append(model.api_model)
            return NodeResult(node.node_id,node.node_type,model.model_id,'',
                0 if failure=='timeout' else 100, 0 if failure=='timeout' else 50,
                0 if failure=='timeout' else .15,120000,status='failed',failure_type=failure,attempts=1)
    state=prepare(task,manifest,FailedBaseline(),simulation=False)
    assert calls==['kimi-k3']
    assert state['stage']=='blocked' and state['reason']=='baseline-failed'
    assert state['rows']==[] and state['reference'] is None and state['node_packet'] is None
    assert state['prepare_cost']==(None if failure=='timeout' else .15)


@pytest.mark.parametrize('stage,timeout', [('prepare',120),('baseline',300)])
def test_timeout_cli_saves_unknown_cost_and_blocked_checkpoint(tmp_path, monkeypatch,stage,timeout):
    initial=tmp_path/'initial';main(['--output-dir',str(initial)])
    state=read_bundle(initial)
    calibration=fixture_reviews(state['calibration']['public'])
    calibration['reviewer']={'kind':'human','id':'test-fixture'}
    sid=next(s for s,k in state['calibration']['private']['sample_records'].items() if k=='missing-comparison')
    next(r for r in calibration['reviews'] if r['sample_id']==sid)['task_checks']['substantive_comparison']=False
    reviews=tmp_path/'reviews.json';reviews.write_text(json.dumps({'calibration':calibration}))
    monkeypatch.setenv('REFRACTROUTER_K3_BASELINE_HOST','dsh-plugin')
    monkeypatch.setenv('CODEX_ARK_API_KEY','test-only')
    class Timeout:
        calls=0
        def invoke(self, task, node, prompt, context, model):
            self.calls+=1
            return NodeResult(node.node_id,node.node_type,model.model_id,'',0,0,0,120000,
                              status='failed',failure_type='timeout',attempts=1)
    adapter=Timeout()
    with patch('experiments.run_k3_baseline.OpenAICompatibleClient') as client, patch(
            'experiments.run_k3_baseline.OpenAICompatibleAdapter',return_value=adapter):
        assert main(['--stage',stage,'--output-dir',str(tmp_path/'output'),'--input-dir',str(initial),
            '--reviews',str(reviews),'--execute-paid-run','--max-production-cost','132',
            '--max-evaluation-cost','0'])==1
    assert client.call_args.kwargs['timeout_seconds']==timeout
    saved=read_bundle(tmp_path/'output')
    summary=json.loads((tmp_path/'output/benchmark-summary.json').read_text())
    assert saved['stage']=='blocked' and saved['reason']=='baseline-failed' and adapter.calls==1
    assert summary['stage_production_cost'] is None
    assert summary['known_stage_production_cost']==0 and len(summary['unknown_usage_requests'])==1


@pytest.mark.parametrize('damage', ['stage','simulation','model','cost','output','contract','task','unknown-cost'])
def test_resume_rejects_invalid_checkpoint_before_model_calls(damage):
    task, manifest, adapter=setup()
    state=prepare(task,manifest,adapter,simulation=True,baseline_only=True)
    if damage=='stage': state['stage']='node-review-ready'
    elif damage=='simulation': state['simulation']=False
    elif damage=='model': state['baseline']['node_results'][0]['model_id']='cheap'
    elif damage=='cost': state['baseline']['total_cost']+=1
    elif damage=='output': state['baseline']['final_output']=''
    elif damage=='contract':
        state['baseline']['final_output']='not HTML'
        state['baseline']['node_results'][0]['output']='not HTML'
    elif damage=='task': state['task']['task_id']='another-task'
    else: state['unknown_usage_requests']=[{'request_id':'unresolved'}]
    with pytest.raises(ValueError): resume_baseline(state,manifest,adapter,simulation=True)
    assert adapter.calls==1


def test_resume_migration_requires_exact_source_target_and_index(tmp_path,monkeypatch):
    import hashlib
    import experiments.run_k3_baseline as runner
    initial=tmp_path/'initial';main(['--stage','baseline','--output-dir',str(initial)])
    state=read_bundle(initial)
    current=json.loads((initial/'preflight.json').read_text())['config']
    old=deepcopy(current);old['code']['experiments/run_k3_baseline.py']='old-reviewed-code'
    state['config_sha256']=digest(old)
    state['baseline']={'total_cost':1}
    p=json.loads((initial/'preflight.json').read_text());p['config']=old
    (initial/'preflight.json').write_text(json.dumps(p));save_bundle(initial,state)
    entry={'source_config_sha256':digest(old),'target_config_sha256':digest(current),
        'source_index_sha256':hashlib.sha256((initial/'evidence-index.json').read_bytes()).hexdigest()}
    policy=tmp_path/'compatibility.json';monkeypatch.setattr(runner,'BASELINE_COMPATIBILITY',policy)
    with pytest.raises(ValueError): bind_input(initial,state,current,'resume')
    policy.write_text(json.dumps({'entries':[entry]}))
    assert bind_input(initial,state,current,'resume')['compatibility_record']==entry
    with pytest.raises(ValueError): bind_input(initial,state,current,'prepare')
    changed=deepcopy(current);changed['quality_floor']=84
    with pytest.raises(ValueError): bind_input(initial,state,changed,'resume')
    changed=deepcopy(current);changed['code']['src/refractrouter/adapters.py']='unexpected-new-code'
    with pytest.raises(ValueError): bind_input(initial,state,changed,'resume')
    (initial/'evidence-index.json').write_text((initial/'evidence-index.json').read_text()+'\n')
    with pytest.raises(ValueError): bind_input(initial,state,current,'resume')


def test_unknown_probe_usage_stays_unknown_after_resume_and_finalize():
    task,manifest,adapter=setup()
    state=prepare(task,manifest,adapter,simulation=True,baseline_only=True)
    class TimeoutProbe:
        def __init__(self): self.calls=0
        def invoke(self,task,node,prompt,context,model):
            self.calls+=1
            if self.calls==8:
                return NodeResult(node.node_id,node.node_type,model.model_id,'',0,0,0,120000,
                    status='failed',failure_type='timeout',attempts=1)
            return adapter.invoke(task,node,prompt,context,model)
    resumed=resume_baseline(state,manifest,TimeoutProbe(),simulation=True)
    assert resumed['prepare_cost'] is None and resumed['known_prepare_cost']>state['prepare_cost']
    result=compose(resumed,fixture_reviews(resumed['node_packet']),adapter)
    assert result['stage']=='blocked'
    ready=prepare(task,manifest,adapter,simulation=True)
    result=compose(ready,fixture_reviews(ready['node_packet']),adapter)
    result['prepare_cost']=None
    summary=finalize(result,fixture_reviews(result['final_packet']),calibration_passed=True)
    assert summary['total_production_cost'] is None
    assert summary['first_use_cost_reduction_percent'] is None
    assert not summary['candidate_signal']


def test_historical_k3_usage_keeps_content_tokens_and_cost_after_client_merge():
    from refractrouter.k3_experiment import roles
    from refractrouter.openai_compatible import OpenAICompatibleClient, TransportResponse, model_response_cost

    original = read_bundle(ROOT/'reports/v0.5-k3-baseline-retry/output')
    saved = original['baseline']['node_results'][0]
    _, manifest, _ = setup()
    model, _ = roles(manifest)
    # 使用归档结果构造响应，只验证解析与计费兼容性，不宣称重放原始 HTTP 响应。
    usage = {'prompt_tokens': saved['input_tokens'], 'completion_tokens': saved['output_tokens'],
        'prompt_tokens_details': {'cached_tokens': saved['cached_input_tokens']},
        'completion_tokens_details': {'reasoning_tokens': saved['reasoning_tokens']}}
    body = {'choices': [{'message': {'content': saved['output']}, 'finish_reason': saved['finish_reason']}],
        'usage': usage}
    with patch('refractrouter.openai_compatible.UrllibTransport.post', return_value=TransportResponse(
            200, {'X-Request-ID': saved['request_id']}, json.dumps(body).encode())) as post:
        response = OpenAICompatibleClient(environment={model.api_key_env: 'test-only'}, max_retries=0).complete(
            model, ({'role': 'user', 'content': '离线解析兼容验证'},), json_mode=False)
    post.assert_called_once()
    assert response.usage_available and response.raw_usage == usage
    assert response.content == saved['output']
    for field in ('input_tokens', 'output_tokens', 'cached_input_tokens', 'reasoning_tokens',
                  'finish_reason', 'request_id', 'attempts'):
        assert getattr(response, field) == saved[field]
    assert model_response_cost(model, response) == saved['cost'] == 9.154


def test_historical_baseline_preflight_migrates_without_network_or_source_edits(tmp_path):
    import hashlib
    original=ROOT/'reports/v0.5-k3-baseline-retry/output'
    before={str(p.relative_to(original)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in original.rglob('*') if p.is_file()}
    with patch('experiments.run_k3_baseline.OpenAICompatibleClient') as client:
        assert main(['--stage','resume','--input-dir',str(original),'--output-dir',str(tmp_path/'preflight')])==0
        assert main(['--stage','resume','--input-dir',str(tmp_path/'preflight'),
                     '--output-dir',str(tmp_path/'next-preflight')])==0
    client.assert_not_called()
    state=read_bundle(tmp_path/'preflight')
    assert state['baseline']==read_bundle(original)['baseline']
    p=json.loads((tmp_path/'preflight/preflight.json').read_text())
    assert p['model_calls']==0 and p['call_plan']['production_model_calls']==28
    assert p['minimum_production_limit']==119.49
    assert p['baseline_reuse']['imported_production_cost']==9.154
    assert p['baseline_reuse']['compatibility_record']
    assert before=={str(p.relative_to(original)):hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in original.rglob('*') if p.is_file()}


def test_main_integration_does_not_migrate_completed_node_reviews(tmp_path, capsys):
    original = ROOT/'reports/v0.5-k3-resume-admission-2/output'
    state = read_bundle(original)
    assert state['stage'] == 'node-review-ready'
    with patch('experiments.run_k3_baseline.OpenAICompatibleClient') as client:
        with pytest.raises(SystemExit) as error:
            main(['--stage', 'compose', '--input-dir', str(original),
                  '--output-dir', str(tmp_path/'compose')])
    assert error.value.code == 2
    assert '输入材料与当前冻结配置或代码不一致' in capsys.readouterr().err
    client.assert_not_called()
    assert not (tmp_path/'compose').exists()
