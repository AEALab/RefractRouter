"""无需网络即可区分响应前超时、响应体超时与 HTTP 408。"""
import io
import json
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

import pytest

from refractrouter.openai_compatible import (
    ModelInvocationError, OpenAICompatibleClient, UrllibTransport,
)
from tests.test_openai_compatible import real_model, success_response


@pytest.mark.parametrize('scenario,origin,phase,status', [
    ('headers', 'transport', 'connect-or-response-headers', None),
    ('wrapped', 'transport', 'connect-or-response-headers', None),
    ('connection', 'transport', 'connect-or-response-headers', None),
    ('body', 'transport', 'response-body', 200),
    ('http408', 'http', 'complete', 408),
    ('http408-body', 'transport', 'response-body', 408),
    ('invalid-body', 'response-validation', 'complete', 200),
])
def test_timeout_origin_survives_client_and_progress(tmp_path, scenario, origin, phase, status):
    response = Mock(status=200, headers={'X-Tt-Logid': 'provider-test', 'Set-Cookie': 'secret-cookie'})
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.side_effect = TimeoutError('secret-body')
    http_error = HTTPError('https://example.invalid', 408, 'secret-error',
                           {'X-Request-ID': 'provider-test'}, io.BytesIO(b'{}'))
    if scenario == 'http408-body':
        http_error.read = Mock(side_effect=TimeoutError('secret-body'))
    if scenario == 'invalid-body':
        response.read.side_effect = None
        response.read.return_value = b'not json'
    effects = {
        'headers': TimeoutError('secret-error'),
        'wrapped': URLError(TimeoutError('secret-error')),
        'connection': URLError(ConnectionResetError('secret-error')),
        'body': None, 'invalid-body': None,
        'http408': http_error, 'http408-body': http_error,
    }
    progress = tmp_path / 'progress.ndjson'
    client = OpenAICompatibleClient(transport=UrllibTransport(), timeout_seconds=600,
        max_retries=0, environment={'TEST_API_KEY': 'secret-key',
                                   'REFRACTROUTER_MODEL_PROGRESS': str(progress)})
    with patch('refractrouter.openai_compatible.urlopen', return_value=response,
               side_effect=effects[scenario]) as opened:
        with pytest.raises(ModelInvocationError) as caught:
            client.complete(real_model(), [{'role': 'user', 'content': 'secret-prompt'}])
    exc = caught.value
    assert opened.call_count == exc.attempts == 1
    assert opened.call_args.kwargs['timeout'] == 600
    expected_failure = ('transport-error' if scenario == 'connection' else
                        'invalid-response' if scenario == 'invalid-body' else 'timeout')
    assert exc.failure_type == expected_failure
    assert exc.diagnostics['failure_origin'] == origin
    assert exc.diagnostics['phase'] == phase
    assert exc.diagnostics.get('http_status') == status
    if status is not None:
        assert exc.diagnostics['provider_request_id'] == 'provider-test'
        assert exc.diagnostics['time_to_headers_ms'] >= 0
    else:
        assert 'provider_request_id' not in exc.diagnostics
    events = [json.loads(row) for row in progress.read_text().splitlines()]
    assert [row['event'] for row in events] == ['request-start', 'request-finish']
    assert events[-1]['diagnostics'] == exc.diagnostics
    assert 'secret-' not in progress.read_text()


def test_success_retains_usage_and_transport_timing(tmp_path):
    saved = success_response()
    response = Mock(status=200, headers=saved.headers)
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.return_value = saved.body
    progress = tmp_path / 'progress.ndjson'
    client = OpenAICompatibleClient(max_retries=0, environment={'TEST_API_KEY': 'mock',
        'REFRACTROUTER_MODEL_PROGRESS': str(progress)})
    with patch('refractrouter.openai_compatible.urlopen', return_value=response):
        result = client.complete(real_model(), [])
    assert result.input_tokens == 100 and result.output_tokens == 25
    event = json.loads(progress.read_text().splitlines()[-1])
    assert event['diagnostics']['phase'] == 'complete'
    assert event['diagnostics']['time_to_headers_ms'] >= 0
