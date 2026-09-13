"""模型失败诊断须可定位，同时保留未知用量且不暴露供应商文本。"""
import json

from refractrouter.openai_compatible import ModelInvocationError
from tests.test_text_tasks import Client, live


class FailingClient(Client):
    def complete(self, model, messages, *, json_mode=False):
        raise ModelInvocationError('request-error', 'secret-provider-body', 1, 10,
            diagnostics={'http_status': 400, 'authorization': 'secret-token',
                         'provider_request_id': 'secret-id'})


def test_planner_failure_preserves_safe_diagnostics_and_reservation():
    result = live(FailingClient())
    assert result['status'] == 'failed'
    assert result['issues'] == ['ModelInvocationError: request-error (HTTP 400)']
    call = result['calls'][0]
    assert call['failure'] == {'failure_type': 'request-error', 'http_status': 400, 'attempts': 1}
    assert call['status'] == 'unknown-usage'
    assert call['charged'] == call['reserved'] > 0
    assert 'secret' not in json.dumps(result)


def test_untrusted_diagnostic_values_are_not_exposed():
    error = ModelInvocationError('secret-type', 'secret-message', True, 0,
        diagnostics={'http_status': 'secret-status'})
    assert error.public_details() == {'failure_type': 'model-invocation-error'}


def test_task_deadline_reports_distinct_limit_and_preserves_partial_evidence():
    from unittest.mock import patch
    with patch('refractrouter.task_runtime.execute_nodes',side_effect=ValueError('task-deadline-exhausted')):
        result=live(Client())
    assert result['status']=='failed'
    assert result['issues'][0].startswith('task-deadline-exhausted (任务执行期限')
    assert result['deadline_failure']['limit_ms']>0
    assert result['deadline_failure']['unfinished_nodes']
    assert result['calls']
