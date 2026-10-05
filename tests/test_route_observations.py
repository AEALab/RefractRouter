"""路线时延只从真实调用账本积累，不创建额外模型请求。"""
from concurrent.futures import ThreadPoolExecutor
import json

from refractrouter.agent import resource, run_agent
from refractrouter.agent_cli import main
from refractrouter.route_observations import (RouteObservationStore, local_observation_path,
                                               route_value_observation)
from refractrouter.team_service import TaskStore
from tests.test_text_tasks import Client


def binding(provider='cloud', model='same-name', effective='Model-v1', effort='default'):
    return {'route-id': {'provider': provider, 'model': model,
                         'effective_model': effective, 'reasoning_effort': effort}}


def call(label, latency, *, status='billed', finish='stop'):
    return {'label': label, 'model_id': 'route-id', 'category': 'production',
            'status': status, 'latency_ms': latency, 'finish_reason': finish,
            'input_tokens': 100, 'output_tokens': 20, 'cached_input_tokens': 10}


def test_successful_calls_build_a_persistent_latest_50_p90_profile(tmp_path):
    path = tmp_path / 'observations.sqlite3'
    store = RouteObservationStore(path)
    calls = [call(f'node-{index}', latency) for index, latency in enumerate(range(1, 61), 1)]
    assert store.record_run('run-1', calls, binding()) == 60
    profile = RouteObservationStore(path).latency_profiles()['cloud/same-name\0Model-v1\0default']
    assert profile['samples'] == 50
    assert profile['prediction_ms'] == 55
    assert profile['window'] == 'latest-50-successful-p90'
    assert profile['effective_model'] == 'Model-v1'
    assert len(profile['snapshot_id']) == 64


def test_failures_cancellations_and_duplicates_do_not_become_success_latency(tmp_path):
    store = RouteObservationStore(tmp_path / 'observations.sqlite3')
    rows = [call('ok', 800), call('length', 900, finish='length'),
            call('failed', 1000, status='unknown-usage'),
            call('cancelled', None, status='cancelled-before-dispatch')]
    assert store.record_run('run-1', rows, binding()) == 3
    assert store.record_run('run-1', rows, binding()) == 0
    assert store.latency_profiles()['cloud/same-name\0Model-v1\0default']['samples'] == 1
    assert store.status_counts()['cloud/same-name'] == {'failed': 2, 'success': 1}


def test_provider_effective_model_and_effort_are_isolated_under_concurrent_writes(tmp_path):
    path = tmp_path / 'observations.sqlite3'
    cases = [
        ('run-a', binding('provider-a'), 100),
        ('run-b', binding('provider-b'), 900),
        ('run-c', binding('provider-a', effective='Model-v2'), 500),
        ('run-d', binding('provider-a', effort='high'), 700),
    ]
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda row: RouteObservationStore(path).record_run(
            row[0], [call('node', row[2])], row[1]), cases))
    profiles = RouteObservationStore(path).latency_profiles()
    assert profiles['provider-b/same-name\0Model-v1\0default']['prediction_ms'] == 900
    assert profiles['provider-a/same-name\0Model-v1\0default']['prediction_ms'] == 100
    assert profiles['provider-a/same-name\0Model-v2\0default']['prediction_ms'] == 500
    assert profiles['provider-a/same-name\0Model-v1\0high']['prediction_ms'] == 700


def test_team_task_database_can_share_the_observation_table(tmp_path):
    path = tmp_path / 'team.sqlite3'
    TaskStore(path)
    RouteObservationStore(path).record_run('run-1', [call('node', 321)], binding())
    assert RouteObservationStore(path).latency_profiles()[
        'cloud/same-name\0Model-v1\0default']['prediction_ms'] == 321
    assert TaskStore(path).list(project_ids=('none',), member_id=None, limit=10) == []


def test_project_scopes_do_not_share_route_latency(tmp_path):
    path = tmp_path / 'team.sqlite3'
    RouteObservationStore(path, scope='alpha').record_run(
        'run-alpha', [call('node', 111)], binding())
    RouteObservationStore(path, scope='beta').record_run(
        'run-beta', [call('node', 999)], binding())
    key = 'cloud/same-name\0Model-v1\0default'
    assert RouteObservationStore(path, scope='alpha').latency_profiles()[key]['prediction_ms'] == 111
    assert RouteObservationStore(path, scope='beta').latency_profiles()[key]['prediction_ms'] == 999


def test_preflight_and_demo_do_not_create_observation_samples(tmp_path):
    path = local_observation_path(tmp_path)
    for mode in ('preflight', 'demo'):
        run_agent({'task': f'{mode} 零调用', 'template': 'single'}, mode=mode,
                  runs_dir=tmp_path, route_observation_path=path)
    assert not path.exists()


def test_cli_exposes_a_zero_call_read_only_catalog(tmp_path, capsys):
    path = local_observation_path(tmp_path)
    RouteObservationStore(path).record_run('run-1', [call('node', 456)], binding())
    assert main(['route-profiles', '--runs-dir', str(tmp_path)]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value['schemaVersion'] == 'refractrouter-route-profiles-v1'
    assert value['modelCalls'] == 0
    assert value['profiles'][0]['prediction_ms'] == 456


def test_passive_value_observation_uses_only_selected_route_and_confirmed_calls(tmp_path):
    store = RouteObservationStore(tmp_path / 'observations.sqlite3')
    comparison = {'route': 'dag', 'direct': {'total_estimated_cost': .2},
                  'dag': {'total_estimated_cost': .1}}
    calls = [{'billing_unit': 'AFP', 'status': 'billed', 'charged': .12},
             {'billing_unit': 'AFP', 'status': 'reserved', 'charged': .03}]
    value = route_value_observation(comparison, 'model', calls, 'AFP', 'completed',
                                    {'passed': True, 'score': 90}, {'passed': False})
    assert value['predicted_costs_by_unit'] == {'AFP': .1}
    assert value['actual_costs_by_unit']['AFP'] == .12
    assert value['unconfirmed_costs_by_unit']['AFP'] == .03
    assert value['quality_source'] == 'model-review-unverified'
    assert value['tool_receipt_passed'] is False
    assert value['counterfactual_observed'] is False
    assert store.record_route_value('run-1', value) == 1
    assert store.record_route_value('run-1', value) == 0
    summary = store.value_summary()
    assert summary['byRoute']['dag']['runs'] == 1
    assert summary['byRoute']['dag']['modelReviewPassed'] == 1
    assert summary['byRoute']['dag']['toolReceiptFailed'] == 1
    assert summary['costRatioP90ByRouteAndUnit'] == {}
    assert summary['qualityVerified'] is False


def test_cost_forecast_ratio_excludes_failed_runs_and_keeps_units_separate(tmp_path):
    store = RouteObservationStore(tmp_path / 'observations.sqlite3')
    comparison = {'route': 'direct', 'direct': {'total_estimated_by_unit': {'AFP': 2, 'CNY': .1}}}
    for index, (status, actual) in enumerate((('completed', 1), ('completed', 3), ('failed', 100))):
        value = route_value_observation(comparison, 'direct-after-probe', [
            {'billing_unit': 'AFP', 'status': 'billed', 'charged': actual},
            {'billing_unit': 'CNY', 'status': 'billed', 'charged': .05}],
            'MIXED', status, None)
        store.record_route_value(f'run-{index}', value)
    ratios = store.value_summary()['costRatioP90ByRouteAndUnit']['direct']
    assert ratios['AFP'] == {'ratio': 1.5, 'samples': 2}
    assert ratios['CNY'] == {'ratio': .5, 'samples': 2}
    assert store.catalog()['modelCalls'] == 0


def test_live_run_reuses_call_ledger_to_record_observations_without_probe(tmp_path):
    manifest = json.loads(resource('agent-plan.json').read_text())
    provenance = {
        f"ark/{row['api_model']}": {
            'compiled_model_id': row['model_id'],
            'effective_model': row['api_model'],
            'reasoning_effort': 'default',
        }
        for row in manifest['models']
    }
    path = local_observation_path(tmp_path)
    result = run_agent(
        {'task': '确定性测试，不访问网络。'},
        preset='ark-agent-plan', mode='live', execute_paid_run=True,
        runs_dir=tmp_path, client=Client(), model_profile_provenance=provenance,
        route_observation_path=path,
    )
    assert result['status'] == 'completed'
    ledger = json.loads((tmp_path / result['run_id'] / 'result.json').read_text())['calls']
    assert result['route_observations']['recorded'] == len(ledger) == 2
    catalog = RouteObservationStore(path).catalog()
    assert catalog['modelCalls'] == 0
    assert {row['route'] for row in catalog['profiles']} == {
        'ark/minimax-m3', 'ark/kimi-k3',
    }
    assert all(row['samples'] == 1 for row in catalog['profiles'])
