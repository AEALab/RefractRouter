import json
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from refractrouter.agent_server import (
    PROTOCOL,
    ServerConfiguration,
    ThreadingHTTPServer,
    execute_http_request,
    handler_factory,
    serve,
)


def envelope(**execution):
    return {
        'protocol': PROTOCOL,
        'request': {'task': '仅进行模拟', 'strategy': 'balanced', 'template': 'single'},
        'execution': {'mode': 'demo', **execution},
    }


def test_execute_http_request_enforces_server_limits(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr('refractrouter.agent_server.run_agent',
                        lambda payload, **kwargs: seen.update(payload=payload, **kwargs) or {'ok': True})
    config = ServerConfiguration(tmp_path, production_budget=5, evaluation_budget=6,
                                 timeout_ms=7000, max_output_tokens=3000)
    assert execute_http_request(envelope(productionBudget=4, evaluationBudget=5,
                                         timeoutMs=6000, maxOutputTokens=2000), config) == {'ok': True}
    assert seen['mode'] == 'demo'
    assert seen['production_budget'] == 4
    assert seen['evaluation_budget'] == 5
    assert seen['timeout_ms'] == 6000
    assert seen['max_output_tokens'] == 2000
    assert seen['execute_paid_run'] is False

    with pytest.raises(ValueError, match='productionBudget'):
        execute_http_request(envelope(productionBudget=6), config)
    with pytest.raises(ValueError, match='only permits'):
        execute_http_request({**envelope(), 'execution': {'mode': 'live'}}, config)


def test_execute_http_request_rejects_remote_host_tools(tmp_path):
    request = envelope()
    request['request']['hostTools'] = []
    with pytest.raises(ValueError, match='host tools'):
        execute_http_request(request, ServerConfiguration(tmp_path))


def test_http_health_auth_and_ndjson_result(monkeypatch, tmp_path):
    monkeypatch.setenv('ROUTER_TEST_TOKEN', 'private-value')
    monkeypatch.setattr('refractrouter.agent_server.run_agent', lambda payload, **kwargs: {
        'schema_version': 'refractagent-result-v1', 'answer': '模拟完成'
    })
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler_factory(
        ServerConfiguration(tmp_path, auth_token_env='ROUTER_TEST_TOKEN')))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = f'http://127.0.0.1:{server.server_port}'
    try:
        with pytest.raises(HTTPError) as unauthorized:
            urlopen(root + '/healthz')
        assert unauthorized.value.code == 401
        health = json.loads(urlopen(Request(root + '/healthz', headers={
            'Authorization': 'Bearer private-value'})).read())
        assert health == {'protocol': PROTOCOL, 'status': 'ok', 'paid_execution': False}
        response = urlopen(Request(root + '/v1/run', method='POST',
                                   data=json.dumps(envelope()).encode(), headers={
                                       'Content-Type': 'application/json',
                                       'Authorization': 'Bearer private-value'}))
        records = [json.loads(line) for line in response]
        assert records == [{'protocol': PROTOCOL, 'type': 'result', 'value': {
            'schema_version': 'refractagent-result-v1', 'answer': '模拟完成'}}]
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_non_loopback_service_requires_auth(tmp_path):
    with pytest.raises(ValueError, match='requires --auth-token-env'):
        serve(host='0.0.0.0', port=8787, config=ServerConfiguration(Path(tmp_path)))
