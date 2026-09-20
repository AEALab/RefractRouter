"""#112 安全约束基准协议与零调用排练。"""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from refractrouter.security_benchmark import preflight, validate_protocol

ROOT = Path(__file__).resolve().parents[1]


def protocol():
    return json.loads((ROOT / 'data/research/security-benchmark-v1.json').read_text())


def test_protocol_freezes_all_task_classes_and_separates_reference_from_frontier():
    result = preflight(protocol())
    assert result['real_model_calls'] == 0
    assert result['coverage']['task_count'] == 5
    assert len(result['runs']) == 20
    assert result['maximum_calls'] == 48
    assert result['maximum_calls'] <= protocol()['constraints']['maxCalls']
    references = [row for row in result['runs'] if row['arm'] == 'external-reference']
    deployable = [row for row in result['runs'] if row['deployable']]
    assert references and all(row['reference_only'] and not row['deployable'] for row in references)
    assert deployable and all(row['privacy_violations'] == 0 for row in deployable)
    assert all(row['quality_status'] == 'unmeasured' for row in result['runs'])


def test_sensitive_material_cannot_reach_an_external_deployable_route():
    raw = protocol()
    task = next(row for row in raw['tasks'] if row['originalGrade'] == 'S1')
    task['constrainedDirectModel'] = 'external-cheap'
    with pytest.raises(ValueError, match='trust boundary'):
        validate_protocol(raw)


def test_simulated_local_cannot_enter_the_deployable_frontier():
    raw = protocol()
    raw['tasks'][0]['fixedDag'][0]['modelId'] = 'simulated-local-worker'
    with pytest.raises(ValueError, match='unavailable deployable model'):
        validate_protocol(raw)


def test_sensitive_external_reference_requires_a_distinct_desensitized_view():
    raw = protocol()
    task = next(row for row in raw['tasks'] if row['originalGrade'] == 'S1')
    task['referenceView'] = task['task']
    with pytest.raises(ValueError, match='distinct desensitized view'):
        validate_protocol(raw)


def test_call_envelope_is_fail_closed():
    raw = deepcopy(protocol())
    raw['constraints']['maxCalls'] = 47
    with pytest.raises(ValueError, match='call envelope'):
        preflight(raw)
