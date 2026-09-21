import json
from pathlib import Path
from threading import Event, Thread
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from refractrouter.agent_server import (
    PROTOCOL_V2,
    ServerConfiguration,
    ThreadingHTTPServer,
    handler_factory,
)
from refractrouter.team_service import (
    IdempotencyConflict,
    ProjectCapacityExceeded,
    TaskStore,
    TeamConfiguration,
    TeamMember,
    TeamProject,
    load_team_configuration,
)


def project(tmp_path, *, identity='alpha', concurrency=2):
    return TeamProject(identity, tmp_path / identity, concurrency, 5, 6, 7000, 3000)


def team(tmp_path, monkeypatch):
    monkeypatch.setenv('ALICE_TOKEN', 'alice-secret')
    monkeypatch.setenv('BOB_TOKEN', 'bob-secret')
    monkeypatch.setenv('MAINTAINER_TOKEN', 'maintainer-secret')
    projects = {key: project(tmp_path, identity=key) for key in ('alpha', 'beta')}
    return TeamConfiguration(tmp_path / 'state.sqlite3', projects, (
        TeamMember('alice', 'member', 'ALICE_TOKEN', ('alpha',)),
        TeamMember('bob', 'member', 'BOB_TOKEN', ('alpha', 'beta')),
        TeamMember('maintainer', 'maintainer', 'MAINTAINER_TOKEN', ('alpha', 'beta')),
    ))


def v2_envelope(project_id='alpha', task='模拟任务'):
    return {
        'protocol': PROTOCOL_V2,
        'projectId': project_id,
        'request': {'task': task, 'strategy': 'balanced', 'template': 'single'},
        'execution': {'mode': 'demo'},
    }


def api(root, path, token, *, method='GET', body=None, headers=None):
    request_headers = {'Authorization': f'Bearer {token}', **(headers or {})}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        request_headers['Content-Type'] = 'application/json'
    response = urlopen(Request(root + path, method=method, data=data, headers=request_headers))
    return response, json.loads(response.read())


def wait_for_status(root, task_id, token, expected, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _, value = api(root, f'/v2/tasks/{task_id}', token)
        if value['status'] in expected:
            return value
        time.sleep(.01)
    raise AssertionError(f'task did not reach {expected}')


def test_load_team_configuration_uses_environment_references(monkeypatch, tmp_path):
    monkeypatch.setenv('TEAM_ALICE_TOKEN', 'not-in-the-file')
    config_path = tmp_path / 'service.json'
    config_path.write_text(json.dumps({
        'schemaVersion': 'refractrouter-service-v1',
        'statePath': 'state/router.sqlite3',
        'projects': [{'id': 'alpha', 'runsDir': 'runs/alpha', 'maxConcurrentTasks': 3,
                      'productionBudget': 4, 'evaluationBudget': 5,
                      'timeoutMs': 6000, 'maxOutputTokens': 2000}],
        'members': [{'id': 'alice', 'role': 'member', 'tokenEnv': 'TEAM_ALICE_TOKEN',
                     'projects': ['alpha']}],
    }))
    loaded = load_team_configuration(config_path, default_runs_dir=tmp_path / 'fallback')
    assert loaded.state_path == (tmp_path / 'state/router.sqlite3').resolve()
    assert loaded.projects['alpha'].runs_dir == tmp_path / 'runs/alpha'
    assert loaded.authenticate('Bearer not-in-the-file').id == 'alice'
    assert 'not-in-the-file' not in config_path.read_text()


def test_store_idempotency_capacity_and_restart_recovery(tmp_path):
    store = TaskStore(tmp_path / 'state.sqlite3')
    limited = project(tmp_path, concurrency=1)
    first, reused = store.submit(member_id='alice', project=limited,
                                 idempotency_key='same', envelope=v2_envelope())
    assert not reused and first['status'] == 'queued'
    same, reused = store.submit(member_id='alice', project=limited,
                                idempotency_key='same', envelope=v2_envelope())
    assert reused and same['taskId'] == first['taskId']
    with pytest.raises(IdempotencyConflict):
        store.submit(member_id='alice', project=limited, idempotency_key='same',
                     envelope=v2_envelope(task='不同任务'))
    with pytest.raises(ProjectCapacityExceeded):
        store.submit(member_id='alice', project=limited, idempotency_key='other',
                     envelope=v2_envelope(task='第二个任务'))
    assert store.claim(first['taskId'])
    restarted = TaskStore(tmp_path / 'state.sqlite3')
    assert restarted.get(first['taskId'])['status'] == 'recovery_required'
    events = restarted.events(first['taskId'], 0)
    assert events[-1]['value']['status'] == 'recovery_required'


def test_http_v2_projects_idempotency_events_and_access(monkeypatch, tmp_path):
    monkeypatch.setattr('refractrouter.agent_server.run_agent', lambda payload, **kwargs: {
        'schema_version': 'refractagent-result-v1', 'run_id': 'run-demo',
        'status': 'simulated', 'answer': '模拟完成',
    })
    configuration = team(tmp_path, monkeypatch)
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler_factory(
        ServerConfiguration(tmp_path / 'legacy', team=configuration)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = f'http://127.0.0.1:{server.server_port}'
    try:
        _, projects = api(root, '/v2/projects', 'alice-secret')
        assert [row['id'] for row in projects['projects']] == ['alpha']
        response, submitted = api(
            root, '/v2/tasks', 'alice-secret', method='POST', body=v2_envelope(),
            headers={'Idempotency-Key': 'request-1'},
        )
        assert response.status == 202 and submitted['reused'] is False
        task_id = submitted['taskId']
        completed = wait_for_status(root, task_id, 'alice-secret', {'completed'})
        assert completed['result']['answer'] == '模拟完成'
        response, replay = api(
            root, '/v2/tasks', 'alice-secret', method='POST', body=v2_envelope(),
            headers={'Idempotency-Key': 'request-1'},
        )
        assert response.status == 200 and replay['reused'] is True
        event_response = urlopen(Request(
            root + f'/v2/tasks/{task_id}/events?after=1',
            headers={'Authorization': 'Bearer alice-secret'},
        ))
        records = [json.loads(line) for line in event_response]
        assert records and all(row['sequence'] > 1 for row in records)
        assert records[-1]['value']['status'] == 'completed'
        with pytest.raises(HTTPError) as denied:
            api(root, f'/v2/tasks/{task_id}', 'bob-secret')
        assert denied.value.code == 403
        _, visible = api(root, f'/v2/tasks/{task_id}', 'maintainer-secret')
        assert visible['memberId'] == 'alice'
        _, member_tasks = api(root, '/v2/tasks?projectId=alpha', 'bob-secret')
        assert member_tasks['tasks'] == []
        _, maintained = api(root, '/v2/tasks?projectId=alpha', 'maintainer-secret')
        assert maintained['tasks'][0]['taskId'] == task_id
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_http_v2_cancel_is_idempotent_and_stops_core(monkeypatch, tmp_path):
    started = Event()

    def blocking(payload, **kwargs):
        started.set()
        assert kwargs['cancel_event'].wait(2)
        return {'status': 'failed', 'issues': ['cancelled']}

    monkeypatch.setattr('refractrouter.agent_server.run_agent', blocking)
    configuration = team(tmp_path, monkeypatch)
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler_factory(
        ServerConfiguration(tmp_path / 'legacy', team=configuration)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = f'http://127.0.0.1:{server.server_port}'
    try:
        _, submitted = api(
            root, '/v2/tasks', 'alice-secret', method='POST', body=v2_envelope(),
            headers={'Idempotency-Key': 'cancel-me'},
        )
        assert started.wait(1)
        task_id = submitted['taskId']
        _, first = api(root, f'/v2/tasks/{task_id}/cancel', 'alice-secret', method='POST')
        assert first['status'] in {'cancel_requested', 'cancelled'}
        cancelled = wait_for_status(root, task_id, 'alice-secret', {'cancelled'})
        _, repeated = api(root, f'/v2/tasks/{task_id}/cancel', 'alice-secret', method='POST')
        assert repeated['status'] == cancelled['status'] == 'cancelled'
    finally:
        server.shutdown()
        thread.join()
        server.server_close()

