from dataclasses import FrozenInstanceError, replace
import hashlib
import json
from pathlib import Path

import pytest

from experiments.run_execution_modes import FixtureAdapter
from refractrouter.adapters import OpenAICompatibleAdapter
from refractrouter.evidence_state import evidence_artifact, with_evidence_state
from refractrouter.graph_executor import GraphExecutor
from refractrouter.scoring import node_contract_checks
from tests.helpers import make_registry, make_task
from tests.test_openai_compatible import SequenceTransport, real_model, success_response
from refractrouter.openai_compatible import OpenAICompatibleClient


def fixture():
    task, registry = with_evidence_state(make_task()), make_registry()
    adapter = FixtureAdapter(registry)
    result = GraphExecutor(task, adapter, registry).execute(
        {n.node_id: 'strong-model' for n in task.nodes}, 'dag')
    return task, registry, adapter, result, {n.node_id: n.output for n in result.node_results}


def test_evidence_is_immutable_and_descendants_cannot_replace_it():
    original = make_task()
    task, _, adapter, result, context = fixture()
    assert original.output_contract_version == 'v0.3'
    assert original.nodes[4].parents == ('synthesize_analysis',)
    assert all('extract_evidence' in n.parents for n in task.nodes[3:])
    assert adapter.calls == 7 and not result.failure_types
    artifact = evidence_artifact(task, context)
    assert artifact.output_sha256 == hashlib.sha256(context['extract_evidence'].encode()).hexdigest()
    with pytest.raises(FrozenInstanceError):
        artifact.items[0].claim = 'replacement'
    context['write_report'] = json.dumps({'evidence': [{'claim': 'replacement'}]})
    assert evidence_artifact(task, context) == artifact


@pytest.mark.parametrize('index', [3, 4])
def test_new_outputs_use_citations_without_copying_evidence(index):
    task, _, _, _, context = fixture()
    node = task.nodes[index]
    raw = context[node.node_id]
    assert 'evidence' not in json.loads(raw)
    assert node_contract_checks(task, node, raw, context)['score_cap'] == 100
    assert 'invalid-evidence' in node_contract_checks(make_task(), node, raw, context)['issues']
    transport = SequenceTransport([success_response(raw)])
    adapter = OpenAICompatibleAdapter(OpenAICompatibleClient(
        transport=transport, environment={'TEST_API_KEY': 'fixture'}, max_retries=0))
    result = adapter.invoke(task, node, node.prompt_template, context, real_model())
    assert result.status == 'ok' and result.output == raw
    assert len(transport.calls) == 1
    replaced = {**json.loads(raw), 'evidence': json.loads(context['extract_evidence'])['evidence']}
    assert adapter._output_failure(task, node, json.dumps(replaced), context) == 'unexpected-evidence'


@pytest.mark.parametrize('raw', ['', '{}', '{"evidence":[]}', '{"evidence":[{"source_id":"invented"}]}'])
def test_invalid_extraction_blocks_before_spending(raw):
    task, registry, adapter, _, context = fixture()
    context['extract_evidence'] = raw
    before = adapter.calls
    result = GraphExecutor(task, adapter, registry).probe_node('write_report', 'strong-model', context)
    assert result.failure_type == 'invalid-reference-context'
    assert result.attempts == result.cost == 0 and adapter.calls == before


def test_valid_but_unextracted_sources_do_not_resolve():
    task, _, _, _, context = fixture()
    evidence = json.loads(context['extract_evidence'])['evidence']
    context['extract_evidence'] = json.dumps({'evidence': evidence[:1]})
    node = task.nodes[3]
    for analysis in ['Missing citation', '[source_999] is invented', '[source_002] is outside extraction']:
        assert 'unresolved-citations' in node_contract_checks(
            task, node, json.dumps({'analysis': analysis}), context)['issues']
    assert 'unresolved-citations' in node_contract_checks(
        task, task.nodes[5], context['render_html'], context)['issues']


def test_each_v04_node_contract_passes_with_exact_direct_parent_context():
    task, _, _, result, context = fixture()
    for node, output in zip(task.nodes, result.node_results):
        upstream = {parent: context[parent] for parent in node.parents}
        assert node_contract_checks(task, node, output.output, upstream)['score_cap'] == 100


def test_archived_flash_failure_remains_a_failure_without_repair():
    from tests.test_contract_replay import task as frozen_task
    path = Path(__file__).resolve().parents[1] / (
        'reports/v0.4-known-rejections/repeated-agent-plan/'
        'single-models/report_001/repeat-3/cheap.json')
    before = path.read_bytes()
    record = json.loads(before)
    result = record['result']
    context = {n['node_id']: n['output'] for n in result['node_results']}
    task = frozen_task()
    node = next(n for n in task.nodes if n.node_type == 'synthesis')
    raw = context[node.node_id]
    assert set(json.loads(raw)) == {'analysis'}
    assert 'invalid-evidence' in node_contract_checks(task, node, raw, context)['issues']
    assert 'unresolved-citations' in node_contract_checks(with_evidence_state(task), node, raw, context)['issues']
    assert path.read_bytes() == before
