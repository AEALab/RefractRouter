from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from experiments.run_real_v0_1 import main
from refractrouter.adapters import FakeModelAdapter
from refractrouter.dataset import load_benchmark_dataset
from refractrouter.manifest import load_model_manifest
from refractrouter.node_availability import (
    select_available_candidates, LEGACY_SELECTION_POLICY, REJECTION_SELECTION_POLICY,
)
from tests.test_node_quality import JudgeClient

ROOT = Path(__file__).resolve().parents[1]


def archived_matrix():
    dataset = load_benchmark_dataset(ROOT/'data/benchmarks/v0.1.json', ROOT/'data/tasks', ROOT/'data/source_packs')
    task = next(task for task in dataset.all_tasks if task.task_id == 'report_001')
    matrix = json.loads((ROOT/'reports/v0.3-contract-recovery/repeated-agent-plan/node-quality-matrix.json').read_text())['rows']
    return task, [row for row in matrix if row['repeat'] == 1]


def select(task, rows, policy=REJECTION_SELECTION_POLICY):
    return select_available_candidates(rows, task=task, model_ids=['cheap','mid','strong'], policy=policy)


def test_v2_excludes_the_saved_known_rejection_without_changing_v1_or_evidence():
    task, rows = archived_matrix()
    original = deepcopy(rows)
    v2 = select(task, rows)
    assert v2['route_executable'] and len(v2['assignments']) == 7
    assert v2['assignments']['synthesize_analysis'] != 'cheap'
    assert select(task, rows, LEGACY_SELECTION_POLICY)['assignments'] == {}
    assert rows == original


@pytest.mark.parametrize('case', ['all-rejected','missing-record','missing-judge','transport','invalid-context',
                                   'context-hash','output-hash','duplicate','mixed-repeat','invalid-cost'])
def test_v2_stops_on_unknowns_invalid_context_or_no_candidates(case):
    task, rows = archived_matrix()
    rejected = next(row for row in rows if row['evaluation'].get('method') == 'deterministic-rejection')
    if case == 'all-rejected':
        for row in rows:
            if row['node_id'] == rejected['node_id'] and row is not rejected:
                row.update(evaluation=deepcopy(rejected['evaluation']),eligible=False)
                row['node_result'].update(output=rejected['node_result']['output'],status='failed',failure_type='invalid-evidence')
                row['output_sha256'] = rejected['output_sha256']
    elif case == 'missing-record':
        rows.pop()
    elif case == 'missing-judge':
        rows[0]['evaluation'].update(final_score=None,error=None)
    elif case == 'transport':
        rows[0]['node_result'].update(status='failed',failure_type='timeout')
    elif case == 'invalid-context':
        row = next(row for row in rows if row['upstream'])
        row['upstream'][next(iter(row['upstream']))] = 'invalid reference output'
        row['upstream_sha256'] = hashlib.sha256(json.dumps(row['upstream'],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    elif case == 'context-hash':
        rows[0]['upstream_sha256'] = 'tampered'
    elif case == 'output-hash':
        rows[0]['output_sha256'] = 'tampered'
    elif case == 'duplicate':
        rows.append(deepcopy(rows[0]))
    elif case == 'mixed-repeat':
        rows[0]['repeat'] = 4
    else:
        rows[0]['node_result']['cost'] = float('nan')
    decision = select(task, rows)
    assert not decision['route_executable'] and not decision['assignments']
    assert decision['blocking_reasons']


def test_v2_fake_admission_executes_alternative_and_keeps_rejection_cost(tmp_path):
    manifest_path = ROOT/'data/model-manifests/volcengine-agent-plan.json'
    manifest = load_model_manifest(manifest_path)
    registry = manifest.candidate_registry()
    client = JudgeClient()
    class Adapter(FakeModelAdapter):
        calls = 0
        def invoke(self, task, node, prompt, context, model):
            self.calls += 1
            result = super().invoke(task,node,prompt,context,replace(model,capability=1.0))
            if self.calls == 31:  # Three whole single runs, then the first synthesis probe.
                assert node.node_id == 'synthesize_analysis' and model.model_id == 'cheap'
                return replace(result, output='{"analysis":"Missing evidence"}', status='failed',
                               failure_type='invalid-evidence')
            return result
    adapter=Adapter(registry)
    with patch('experiments.run_real_v0_1.OpenAICompatibleClient', return_value=client), \
         patch('experiments.run_real_v0_1.OpenAICompatibleAdapter', return_value=adapter), \
         patch.dict('os.environ', {manifest.candidates[0].api_key_env:'offline-test-only'}):
        assert main(['--phase','dry-run','--manifest',str(manifest_path),'--output-dir',str(tmp_path),
                     '--selection-policy',REJECTION_SELECTION_POLICY,'--execute-paid-run',
                     '--max-production-cost','250','--max-evaluation-cost','430','--max-retries','0']) == 0
    summary=json.loads((tmp_path/'benchmark-summary.json').read_text())
    assert summary['status'] == 'complete' and not summary['blocking_failures']
    assert summary['failure_taxonomy']['node-probe:invalid-evidence'] == 1
    assert summary['selection_policy'] == summary['preflight']['node_quality']['selection_policy'] == REJECTION_SELECTION_POLICY
    assert summary['oracle_gate']['decision'] == 'Insufficient-evidence'  # Only one repeat.
    matrix=json.loads((tmp_path/'node-quality-matrix.json').read_text())
    rejected=next(row for row in matrix['rows'] if row['evaluation_state']=='contract-rejected')
    assert rejected['evaluation']['final_score']==0 and rejected['node_result']['cost']>0
    assert not rejected['selected'] and len(matrix['rows'])==21
    assert matrix['selection_policy']==REJECTION_SELECTION_POLICY
    assert adapter.calls==56 and len(client.payloads)==25
    decision=json.loads((tmp_path/'selection-report_001-1.json').read_text())
    assert decision['route_executable'] and decision['assignments']['synthesize_analysis']!='cheap'
    assert summary['costs']['production'] > summary['strategies']['node-oracle']['production_cost_total']
