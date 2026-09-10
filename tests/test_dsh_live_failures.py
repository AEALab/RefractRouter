"""离线重放真实宿主任务失败，验证容量与语义闸门不被总分或成功进程掩盖。"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from refractrouter.manifest import load_model_manifest
from refractrouter.openai_compatible import ChatResponse
from refractrouter.task_runtime import run_task

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'reports/dag-decomposition/issue-32-dsh-live-20260907'


@pytest.mark.parametrize('version,status,count', [
    ('v4', 'no-feasible-route', 1),
    ('v5', 'quality-failed', 5),
])
def test_recorded_dsh_failure_is_not_promoted_to_success(version, status, count):
    directory = REPORT / f'dsh-live-{version}' / 'runner/output'
    recorded = json.loads((directory / 'task-result.json').read_text())
    calls = {row['label']: row for row in recorded['calls']}

    class RecordedClient:
        max_retries = 0

        def complete(self, model, messages, *, json_mode=False):
            payload = json.loads(messages[-1]['content'])
            label = 'final-judge' if model.role == 'judge' else payload.get('node_id', 'planner')
            row = calls[label]
            return ChatResponse(row['response_output'], row['input_tokens'], row['output_tokens'],
                                0, 0, row['latency_ms'], 1, row['finish_reason'], row['request_id'])

    with patch('socket.socket', side_effect=AssertionError('禁止网络')):
        result = run_task(json.loads((directory / 'request.json').read_text()),
                          load_model_manifest(directory / 'manifest.json'),
                          json.loads((directory / 'profile.json').read_text()),
                          client=RecordedClient(), production_limit=100, evaluation_limit=200)
    assert result['status'] == status
    assert len(result['calls']) == count
    assert all(row['status'] == 'billed' for row in result['calls'])
    if version == 'v4':
        # 新运行时提前检查全图容量；原归档仍然是 failed，不修改历史产物。
        assert recorded['status'] == 'failed'
        assert result['plan_admission']['cost_analysis']['reason'] == 'input-or-output-capacity'
        assert result['nodes'] == [] and result['evaluation'] is None
    else:
        assert result['evaluation']['score'] == 82
        assert result['evaluation']['passed'] is False
        assert all(row['status'] == 'ok' for row in result['nodes'])
        assert len(result['nodes']) == 3
        assert result['charged']['production'] > 0 and result['charged']['evaluation'] > 0
