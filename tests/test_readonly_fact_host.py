"""固定清单、真实候选绑定、CLI与标准function的零调用宿主往返。"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from refractrouter.readonly_fact_host import HOST_VERSION, load_host, run, tool_schemas
from refractrouter.readonly_fact_host import execute, strict_json
from refractrouter.readonly_facts import sha, wire
from refractrouter.openai_compatible import ChatResponse
from tests.test_model_gateway import gateway, request, follow, Caller, reply

OWNER = {'session': 'host-session', 'agent': 'host-agent', 'turn': 1}


def manifest(tmp_path):
    source = 'def f():\n    return (1, 2)\n'
    (tmp_path / 'visible.py').write_text(source)
    config = {'schemaVersion': HOST_VERSION, 'root': '.', 'files': {
        'visible.py': hashlib.sha256(source.encode()).hexdigest()}}
    path = tmp_path / 'manifest.json'
    raw = wire(config);path.write_bytes(raw)
    return path, sha(raw)


def query(owner=OWNER):
    return {'op': 'query', 'identity': owner, 'operation': 'python-structure',
        'arguments': {'path': 'visible.py', 'symbol': 'f', 'definitionLine': None}}


def final_candidate(fact):
    content = json.dumps({'answer': {'arity': 2}, 'structuralAssertions': [
        {'factId': fact['factId'], 'field': 'fixedTupleArity', 'answerPointer': '/answer/arity'}]})
    return {'content': content, 'toolCalls': [], 'finishReason': 'stop'}


def test_pinned_manifest_and_receipt_reconstruction_bind_final_candidate(tmp_path):
    path, pin = manifest(tmp_path)
    first = run(path, pin, tmp_path, query())
    content = json.loads(first['modelText'])
    assert len(first['modelText'].encode()) == first['visibleUtf8Bytes']
    actual = final_candidate(content['facts'][0])
    result = run(path, pin, tmp_path, {'op': 'verify', 'identity': OWNER,
        'candidateId': 'actual-final-call', 'candidate': actual, 'receipts': [first['receipt']]})['verification']
    assert result['candidateSha256'] == sha(wire(actual))
    assert result['allBoundFieldsSupported'] and not result['wholeTaskQualityProven']
    assert 'receipt' not in first['modelText']
    assert not result['unboundTextSemanticsChecked']


def test_manifest_drift_and_root_escape_cannot_expand_host_scope(tmp_path):
    path, pin = manifest(tmp_path)
    config = json.loads(path.read_text())
    config['files']['hidden.py'] = 'a' * 64
    path.write_bytes(wire(config))
    with pytest.raises(ValueError, match='哈希不符'):
        run(path, pin, tmp_path, query())
    config['root'] = '..';path.write_bytes(wire(config))
    with pytest.raises(ValueError, match='实际工作区'):
        run(path, sha(path.read_bytes()), tmp_path, query())


@pytest.mark.parametrize('damage', ['identity', 'snapshot', 'fact-id', 'scope-fields'])
def test_wrong_receipts_cannot_create_trusted_fact_bank(tmp_path, damage):
    path, pin = manifest(tmp_path)
    first = run(path, pin, tmp_path, query())
    fact = json.loads(first['modelText'])['facts'][0]
    receipt = deepcopy(first['receipt'])
    if damage == 'identity':receipt['identity'] = {**OWNER, 'turn': 2}
    elif damage == 'snapshot':receipt['snapshotId'] = 'b' * 64
    elif damage == 'fact-id':receipt['returnedFactIds'] = ['a' * 64]
    else:receipt['root'] = '/'
    with pytest.raises(ValueError):
        run(path, pin, tmp_path, {'op': 'verify', 'identity': OWNER, 'candidateId': 'call',
            'candidate': final_candidate(fact), 'receipts': [receipt]})


def test_candidate_revision_forged_id_and_no_assertions_never_reuse_pass(tmp_path):
    path, pin = manifest(tmp_path)
    first = run(path, pin, tmp_path, query())
    fact = json.loads(first['modelText'])['facts'][0]
    actual = final_candidate(fact)
    body = json.loads(actual['content']);body['answer']['arity'] = 3
    changed = {**actual, 'content': json.dumps(body)}
    result = run(path, pin, tmp_path, {'op': 'verify', 'identity': OWNER, 'candidateId': 'changed',
        'candidate': changed, 'receipts': [first['receipt']]})['verification']
    assert result['rows'][0]['verdict'] == 'contradicted'
    no_claims = {**actual, 'content': '普通文本没有结构断言'}
    result = run(path, pin, tmp_path, {'op': 'verify', 'identity': OWNER, 'candidateId': 'unbound',
        'candidate': no_claims, 'receipts': [first['receipt']]})['verification']
    assert not result['allBoundFieldsSupported'] and result['rows'] == []


def test_cli_subprocess_uses_public_contract_without_model_calls(tmp_path):
    path, pin = manifest(tmp_path)
    marker = tmp_path / 'must-not-execute'
    (tmp_path / 'json.py').write_text(f'from pathlib import Path\nPath({str(marker)!r}).write_text("executed")\nraise RuntimeError("不应导入仓库代码")\n')
    result = subprocess.run([sys.executable, '-I', '-B', '-m', 'refractrouter.agent_cli', 'fact-tool',
        '--manifest', str(path), '--manifest-sha256', pin, '--workspace-root', str(tmp_path), '--request-stdin'],
        input=json.dumps(query()), cwd=tmp_path, text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data['schemaVersion'] == HOST_VERSION and data['modelCalls'] == 0
    assert json.loads(data['modelText'])['status'] == 'known'
    assert not marker.exists()


def test_standard_function_roundtrip_host_executes_tools_and_binds_actual_delivered_candidate(tmp_path):
    path, pin = manifest(tmp_path)
    host = load_host(path, pin, tmp_path)
    fact = host.structure('visible.py', 'f')[0];host.close()
    actual = final_candidate(fact)
    tool_call = {'id': 'fact-call', 'type': 'function', 'function': {'name': 'refract_python_structure',
        'arguments': json.dumps(query()['arguments'])}}
    caller = Caller(reply(calls=[tool_call]), reply(actual['content']))
    gw = gateway(tmp_path / 'runs', caller)
    req = {**request(), 'tools': [{'type': 'function', 'function': s} for s in tool_schemas()]}
    handles = []
    try:
        first = gw.complete(req, on_outcome=handles.append)
        owner = gw.outcome({'runId': handles[0]})['identity']
        tool_result = run(path, pin, tmp_path, query(owner))
        continued = follow(req, first)
        continued['messages'][-1]['content'] = tool_result['modelText']
        final = gw.complete(continued)
        view = gw.outcome({'runId': handles[0]})
        candidate = view['candidates'][-1]
        delivered = {'content': final['choices'][0]['message']['content'], 'toolCalls': [], 'finishReason': 'stop'}
        result = run(path, pin, tmp_path, {'op': 'verify', 'identity': owner,
            'candidateId': candidate['candidateId'], 'candidate': delivered,
            'receipts': [tool_result['receipt']]})['verification']
        assert result['candidateSha256'] == candidate['candidateSha256']
        assert result['allBoundFieldsSupported'] and not result['wholeTaskQualityProven']
        assert len(caller.actions) == 2
    finally:gw.close()


def test_dsh_tool_schema_is_generated_from_python_authority():
    path = Path(__file__).resolve().parents[1] / 'validation/dsh/plugin/src/readonly-facts-tools.json'
    assert json.loads(path.read_text()) == tool_schemas()


def test_reused_host_cannot_accept_another_task_cached_fact_without_its_receipts(tmp_path):
    path, pin = manifest(tmp_path)
    host = load_host(path, pin, tmp_path)
    try:
        first = execute(host, query())
        fact = json.loads(first['modelText'])['facts'][0]
        other = {**OWNER, 'turn': 2}
        result = execute(host, {'op': 'verify', 'identity': other, 'candidateId': 'actual-call',
            'candidate': final_candidate(fact), 'receipts': []})['verification']
        assert result['rows'][0]['verdict'] == 'unknown'
        assert not result['allBoundFieldsSupported']
    finally:host.close()


def test_candidate_capacity_is_checked_before_json_parse(tmp_path, monkeypatch):
    path, pin = manifest(tmp_path)
    host = load_host(path, pin, tmp_path)
    called = []
    monkeypatch.setattr('refractrouter.readonly_fact_host.strict_json', lambda raw: called.append(raw))
    candidate = {'content': '{"structuralAssertions":[]}' + ' ' * 262144, 'toolCalls': [], 'finishReason': 'stop'}
    try:
        result = execute(host, {'op': 'verify', 'identity': OWNER, 'candidateId': 'large',
            'candidate': candidate, 'receipts': []})['verification']
        assert called == []
        assert result['reasonCode'] == 'candidate-capacity'
        assert not result['allBoundFieldsSupported']
    finally:host.close()


@pytest.mark.parametrize('value', ['\ud800', float('inf'), float('nan')])
def test_invalid_json_values_return_safe_unknown_without_raw_echo(tmp_path, value):
    path, pin = manifest(tmp_path)
    host = load_host(path, pin, tmp_path)
    try:
        invalid = {**query(), 'arguments': {**query()['arguments'], 'path': value}}
        result = execute(host, invalid)
        content = strict_json(result['modelText'])
        assert content['status'] == 'unknown'
        assert content['requestSha256'] is None
        assert result['receipt'] is None
        assert wire(result)
        bad = {'content': value, 'toolCalls': [], 'finishReason': 'stop'}
        result = execute(host, {'op': 'verify', 'identity': OWNER, 'candidateId': 'invalid',
            'candidate': bad, 'receipts': []})['verification']
        assert result['candidateSha256'] is None and not result['allBoundFieldsSupported']
        assert wire(result)
    finally:host.close()


def test_exponent_overflow_is_rejected_during_json_parsing():
    with pytest.raises(ValueError, match='有限'):
        strict_json('{"number":1e999}')
    with pytest.raises(ValueError, match='json-capacity|嵌套'):
        strict_json('[' * 2000 + '0' + ']' * 2000)


def test_binding_cannot_certify_a_side_channel_instead_of_the_final_answer(tmp_path):
    path, pin = manifest(tmp_path)
    first = run(path, pin, tmp_path, query())
    fact = json.loads(first['modelText'])['facts'][0]
    declared = {'answer': {'arity': 3}, 'sideChannel': 2, 'structuralAssertions': [
        {'factId': fact['factId'], 'field': 'fixedTupleArity', 'answerPointer': '/sideChannel'}]}
    result = run(path, pin, tmp_path, {'op': 'verify', 'identity': OWNER, 'candidateId': 'final',
        'candidate': {'content': json.dumps(declared), 'toolCalls': [], 'finishReason': 'stop'},
        'receipts': [first['receipt']]})['verification']
    assert not result['allBoundFieldsSupported']
    assert result['reasonCode'] == 'assertion-outside-final-answer'
