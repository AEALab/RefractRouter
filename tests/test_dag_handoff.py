"""六种显式跨模型排列仅证明交接；异常停止并保留已派发费用。"""
import json
import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

from refractrouter.handoff_validation import load_handoff, run_handoff
from refractrouter.task_contracts import decode_output
from refractrouter.task_plan import validate_plan

from tests.study_fixtures import current_handoff

ROOT = Path(__file__).resolve().parents[1]


def test_all_six_handoffs_consume_actual_parent_fields(tmp_path):
    loaded = current_handoff(ROOT/'data/benchmarks/dag-handoff-v3.json')
    assert loaded[-1]['maximum_calls'] == 24
    with patch('socket.socket', side_effect=AssertionError('禁止网络')):
        result = run_handoff(loaded, tmp_path/'demo')
    assert result['status'] == 'simulated' and len(result['runs']) == 6
    assert len(result['calls']) == 24 and result['routing_benefit'] is None
    for run in result['runs']:
        assert len(set(run['assignments'].values())) == 3
        label = f"handoff-{run['id']}:answer"
        call = next(c for c in result['calls'] if c['label'] == label)
        payload = json.loads(call['request_messages'][-1]['content'])
        assert payload['upstream'] == {n['node_id']: json.loads(n['output']) for n in run['nodes'][:2]}


def test_handoff_failure_does_not_start_later_combinations(tmp_path):
    class Failing:
        max_retries = 0
        def complete(self, *args, **kwargs):
            raise RuntimeError('private upstream error')
    loaded = current_handoff(ROOT/'data/benchmarks/dag-handoff-v3.json')
    limits = loaded[-1]
    result = run_handoff(loaded, tmp_path/'fail', simulated=False, client=Failing(),
        production_limit=limits['production_limit'], evaluation_limit=limits['evaluation_limit'])
    assert result['status'] == 'failed' and len(result['runs']) == 1
    assert result['issues'] == ['RuntimeError']
    assert result['runs'][0]['evaluation'] is None
    assert all(c['label'].startswith('handoff-1:') for c in result['calls'])
    assert result['charged']['production'] > 0


def test_real_handoff_partial_success_preserves_failure_and_exact_inputs():
    archive = ROOT/'reports/dag-decomposition/issue-32-fair-baselines-20260908/handoff'
    index = json.loads((archive/'artifact-index.json').read_text())
    assert all(hashlib.sha256((archive/name).read_bytes()).hexdigest() == digest
               for name, digest in index.items())
    result = json.loads((archive/'result.json').read_text())
    assert result['status'] == 'failed' and result['routing_benefit'] is None
    assert len(result['runs']) == 5 and len(result['calls']) == 18
    for run in result['runs'][:4]:
        assert run['status'] == 'completed' and run['evaluation']['passed']
        call = next(c for c in result['calls'] if c['label'] == f"handoff-{run['id']}:answer")
        payload = json.loads(call['request_messages'][-1]['content'])
        assert payload['upstream'] == {n['node_id']: json.loads(n['output']) for n in run['nodes'][:2]}
    failed = result['runs'][-1]
    risk = next(n for n in failed['nodes'] if n['node_id'] == 'risk')
    assert set(json.loads(risk['output'])) == {'result', 'evidence', 'assumptions', 'assumptions_note'}
    contract = validate_plan(json.loads((archive/'protocol.json').read_text())['plan']).contracts['risk']
    with pytest.raises(ValueError, match='exact nonempty string fields'):
        decode_output(risk['output'], contract)
    assert failed['execution']['not_started'] == ['answer'] and failed['evaluation'] is None
    assert all(c['status'] == 'billed' and not c['label'].startswith('handoff-6:') for c in result['calls'])
