"""开发流程的预算、计划复用与失败隔离验证；禁止网络调用。"""
from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from experiments.prepare_research_studies import prepare
from refractrouter.dag_study_execution import StudyDemoClient
from refractrouter.manifest import load_model_manifest
from refractrouter.openai_compatible import ChatResponse
from refractrouter.research_execution import ResearchSession, EvidenceFailure


class PlannerDemoClient(StudyDemoClient):
    def __init__(self, task, *, bad_plan=False, unknown=False, bad_node=False):
        self.task, self.bad_plan, self.unknown, self.bad_node = task, bad_plan, unknown, bad_node

    def complete(self, model, messages, *, json_mode=False):
        payload = json.loads(messages[-1]['content'])
        if 'acceptance_criteria' in payload:
            return ChatResponse('{}' if self.bad_plan else json.dumps(self.task['plan']), 100, 80, 0, 0, 10, 1, 'stop', None)
        result = super().complete(model, messages, json_mode=json_mode)
        if self.unknown:
            return replace(result, usage_available=False)
        if self.bad_node and model.role != 'judge':
            self.bad_node = False
            return replace(result, content='invalid JSON')
        return result


@pytest.fixture(autouse=True)
def no_network():
    with patch('socket.socket', side_effect=AssertionError('禁止真实网络')):
        yield


@pytest.fixture
def setup(tmp_path):
    config = prepare(40)
    config['execution_policy']['providerMinIntervalMs']['ark-plan'] = 0
    task = next(t for t in config['tasks'] if t['split'] == 'development')
    manifest = load_model_manifest(Path(__file__).resolve().parents[1] / 'data/model-manifests/volcengine-agent-plan.json')
    def session(client=None, max_calls=100):
        return ResearchSession(manifest, config, tmp_path / 'run', client or PlannerDemoClient(task),
            production_limit=1000, evaluation_limit=5000, max_calls=max_calls, simulated=True)
    return task, session


def test_full_development_paths_and_cached_setup_billed_once(setup):
    task, factory = setup
    session = factory()
    for mode in ('manual', 'direct', 'auto-cold'):
        row = session.run_trial(task, mode, mode=mode, fixed_model='strong')
        assert row['status'] == 'completed' and row['delivered']
        assert row['started_ms'] <= row['routing_finished_ms'] <= row['execution_finished_ms'] <= row['finished_ms']
    cached = session.cache_plan(task, 'warm')
    assert cached['deployment_cost'] > 0
    before = len(session.budget.records)
    for n in (1, 2):
        row = session.run_trial(task, f'warm{n}', mode='auto-reuse', cache_id='warm', fixed_model='strong')
        assert row['setup_cost'] == cached['deployment_cost']
        assert row['delivered']
    assert not any(':planner' in c['label'] or ':plan-review' in c['label'] for c in session.budget.records[before:])
    result = session.close()
    assert result['status'] == 'simulated'
    assert all(c['status'] == 'billed' for c in result['calls'])
    assert sum(result['charged'].values()) == pytest.approx(sum(r['deployment_cost'] for r in result['runs'] + result['plan_setups']))
    assert (session.out / 'artifact-index.json').exists()


def test_rejected_plan_archived_without_regeneration(setup):
    task, factory = setup
    session = factory(PlannerDemoClient(task, bad_plan=True))
    cached = session.cache_plan(task, 'bad')
    assert cached['status'] == 'planner-failed' and cached['planner_output'] == '{}'
    before = len(session.budget.records)
    row = session.run_trial(task, 'reuse', mode='auto-reuse', cache_id='bad', fixed_model='strong')
    assert row['status'] == 'planner-failed'
    assert len(session.budget.records) == before
    assert session.run_trial(task, 'next', mode='direct', fixed_model='strong')['delivered']


def test_settled_bad_node_does_not_reset_budget(setup):
    task, factory = setup
    session = factory(PlannerDemoClient(task, bad_node=True))
    identity = id(session.budget)
    first = session.run_trial(task, 'bad', mode='manual', fixed_model='strong')
    assert first['status'] == 'generation-failed' and not first['delivered']
    spent = dict(session.budget.charged)
    assert session.run_trial(task, 'next', mode='direct', fixed_model='strong')['delivered']
    assert id(session.budget) == identity
    assert session.budget.charged['production'] > spent['production']


def test_unknown_usage_stops_whole_session(setup):
    task, factory = setup
    session = factory(PlannerDemoClient(task, unknown=True))
    with pytest.raises(ValueError, match='usage'):
        session.run_trial(task, 'unknown', mode='direct', fixed_model='strong')
    assert session.result['status'] == 'stopped-on-infrastructure'
    assert session.result['runs'][0]['deployment_cost'] is None
    assert session.budget.records[0]['status'] == 'unknown-usage'
    with pytest.raises(RuntimeError, match='stopped'):
        session.run_trial(task, 'next', mode='direct', fixed_model='strong')


def test_evidence_failure_is_not_treated_as_bad_output(setup):
    task, factory = setup
    session = factory()
    with patch('refractrouter.research_execution.write_json', side_effect=ValueError('invalid judge response')):
        with pytest.raises(EvidenceFailure):
            session.run_trial(task, 'bad', mode='direct', fixed_model='strong')
    assert session.budget.stopped


def test_cache_mutation_and_no_profiles_fail_closed(setup):
    task, factory = setup
    session = factory()
    row = session.run_trial(task, 'no-profile', mode='manual')
    assert row['status'] == 'no-feasible-route' and not row['call_labels']
    session.cache_plan(task, 'warm')
    session.cache['warm']['plan']['acceptance_criteria'] = ['变更']
    with pytest.raises(RuntimeError, match='changed'):
        session.run_trial(task, 'bad', mode='auto-reuse', cache_id='warm', fixed_model='strong')


def test_call_limit_not_reset_between_trials(setup):
    task, factory = setup
    session = factory(max_calls=2)
    assert session.run_trial(task, 'first', mode='direct', fixed_model='strong')['delivered']
    with pytest.raises(ValueError, match='call-limit'):
        session.run_trial(task, 'second', mode='direct', fixed_model='strong')
    assert len(session.budget.records) == 2 and session.budget.stopped


def test_node_probes_have_independent_input_output_bound_evaluation(setup):
    task, factory = setup
    session = factory()
    session.probe_node(task, 'cost', 'cheap')
    obs = session.result['observations']['observations'][0]
    assert obs['evaluation']['method'] == 'independent-text-node-v1'
    assert obs['input_sha256'] == obs['evaluation']['input_sha256']
    assert obs['output_sha256'] == obs['evaluation']['output_sha256']
    assert 'node_input' in json.loads(session.budget.records[1]['request_messages'][-1]['content'])
    with pytest.raises(ValueError, match='duplicate'):
        session.probe_node(task, 'cost', 'cheap')


def test_invalid_probe_excluded_with_billed_usage(setup):
    task, factory = setup
    session = factory(PlannerDemoClient(task, bad_node=True))
    row = session.probe_node(task, 'cost', 'cheap')
    assert row['status'] == 'generation-failed' and row['deployment_cost'] > 0
    obs = session.result['observations']['observations'][0]
    assert obs['evaluation']['method'] == 'deterministic-rejection'
    assert len(session.budget.records) == 1
    session.probe_node(task, 'cost', 'mid')
    assert len(session.budget.records) == 3


def test_probe_cannot_use_test_task(setup):
    task, factory = setup
    session = factory()
    task['split'] = 'test'
    with pytest.raises(ValueError, match='held-out'):
        session.probe_node(task, 'cost', 'cheap')
    assert not session.budget.records


def test_complete_rehearsal_is_offline_and_bounded(tmp_path):
    from experiments.rehearse_research_execution import main
    assert main(['--output-dir', str(tmp_path / 'demo')]) == 0
    result = json.loads((tmp_path / 'demo/session.json').read_text())
    assert result['real_model_calls'] == 0 and result['simulated']
    assert len(result['calls']) == 100
    assert len(result['observations']['observations']) == 27
    assert result['node_profile']['kind'] == 'synthetic'
    assert set(result['node_profile']['calibration_task_ids']).isdisjoint(result['node_profile']['held_out_task_ids'])


@pytest.mark.parametrize('mode', ['direct', 'manual', 'probe'])
def test_all_execution_inputs_include_original_acceptance_criteria(setup, mode):
    task, factory = setup
    session = factory()
    if mode == 'probe':
        session.probe_node(task, 'cost', 'strong')
    else:
        session.run_trial(task, 'criteria', mode=mode, fixed_model='strong')
    for call in session.budget.records:
        if call['category'] == 'production':
            payload = json.loads(call['request_messages'][-1]['content'])
            assert all(criterion in payload['task'] for criterion in task['criteria'])


def test_unavailable_baseline_preserves_failure_without_call(setup):
    task,factory=setup;session=factory()
    row=session.run_trial(task,'unavailable',mode='direct',unavailable=True)
    assert not row['delivered'] and row['deployment_cost']==0
    assert not session.budget.records


def test_explicit_handoff_and_serial_policy(setup):
    task,factory=setup;session=factory()
    mids=list(session.models)
    assignments={n['node_id']:mids[i%len(mids)] for i,n in enumerate(task['plan']['nodes'])}
    from refractrouter.research_execution import execute_nodes
    with patch('refractrouter.research_execution.execute_nodes',wraps=execute_nodes) as execute:
        row=session.run_trial(task,'handoff',mode='manual',explicit_assignments=assignments,serial=True)
    assert row['delivered'] and row['assignments']==assignments
    assert execute.call_args.args[5].max_concurrency==1
    assert session.policy.max_concurrency==2
