"""Installed application behavior; all execution tests use deterministic adapters."""
from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from refractrouter.agent import run_agent, plan_template, resource
from refractrouter.agent_cli import main
from tests.test_text_tasks import Client


@pytest.mark.parametrize(('strategy','model'), [
    ('economy', 'deepseek-v4-flash'), ('balanced', 'minimax-m3'), ('quality', 'deepseek-v4-pro'),
])
def test_three_presets_use_the_same_router_and_report_real_assignments(tmp_path, strategy, model):
    with patch('socket.socket', side_effect=AssertionError('no network in application tests')):
        result = run_agent({'task': '根据给定材料比较两种部署方式。', 'strategy': strategy},
            mode='live', execute_paid_run=True, runs_dir=tmp_path, client=Client())
    assert result['status'] == 'completed' and result['models'] == {'answer': model}
    assert result['quality']['passed'] and not result['simulated']
    assert result['costs']['production'] > 0 and result['costs']['evaluation'] > 0
    directory = Path(result['run_dir'])
    assert json.loads((directory/'summary.json').read_text()) == result
    assert (directory/'answer.md').read_text() == result['answer']
    raw = json.loads((directory/'result.json').read_text())
    assert len(raw['calls']) == 2  # no planner, reference run or model probes
    assert set(result['artifact_hashes']) >= {'request.json','manifest.json','profile.json','result.json','answer.md'}


def test_compare_template_reuses_existing_dag_and_retains_handoffs(tmp_path):
    client = Client()
    result = run_agent({'task': '比较方案 A 与 B 的成本、风险和建议。', 'template': 'compare'},
        mode='live', execute_paid_run=True, runs_dir=tmp_path, client=client)
    assert result['status'] == 'completed'
    assert len(client.calls) == 4 and set(result['models']) == {'cost', 'risk', 'answer'}
    assert set(json.loads(client.calls[2][1][-1]['content'])['upstream']) == {'cost','risk'}


def test_compare_template_accepts_a_typical_dsh_system_context(tmp_path):
    result = run_agent({'task': '比较 A/B 成本风险。', 'template': 'compare', 'context': '背景材料' * 4000},
        mode='live', execute_paid_run=True, runs_dir=tmp_path, client=Client())
    assert result['status'] == 'completed', result['issues']


def test_demo_shows_the_task_and_simulation_label_without_dumping_system_context(tmp_path):
    result = run_agent({'task':'演示任务','context':'internal system context'},mode='demo',runs_dir=tmp_path)
    assert result['answer'].startswith('[SIMULATED]')
    assert '演示任务' in result['answer'] and 'internal system context' not in result['answer']
    assert result['quality'] is None and result['simulated']


def test_history_reaches_execution_and_judge_without_becoming_a_new_plan(tmp_path):
    client = Client()
    result = run_agent({'task': '把之前的答案缩成两句。', 'context': '用户：只允许依据附件 A；助手：先前答案'},
        mode='live', execute_paid_run=True, runs_dir=tmp_path, client=client)
    assert result['status'] == 'completed' and len(client.calls) == 2
    assert all('只允许依据附件 A' in messages[-1]['content'] for _, messages in client.calls)


def test_judge_unavailable_preserves_answer_and_budget_record(tmp_path):
    result = run_agent({'task': '给出可用的最终答案。'}, mode='live', execute_paid_run=True,
                       runs_dir=tmp_path, client=Client(bad_judge=True))
    assert result['status']=='failed' and result['quality'] is None and result['answer']
    assert result['costs']['evaluation']>0 and Path(result['result_path']).is_file()


def test_preview_never_resolves_credentials_or_calls_models_and_run_ids_are_unique(tmp_path):
    with patch('socket.socket', side_effect=AssertionError('network forbidden')):
        first = run_agent({'task':'预检任务'}, runs_dir=tmp_path)
        second = run_agent({'task':'预检任务'}, runs_dir=tmp_path)
    assert first['status']=='preview' and first['costs']==dict(production=0,evaluation=0,unconfirmed=0)
    assert first['run_id'] != second['run_id']


def test_live_requires_explicit_execution_and_limits(tmp_path):
    for overrides in ({'mode':'live'}, {'mode':'demo','execute_paid_run':True},
                      {'production_budget':0}, {'evaluation_budget':float('inf')}, {'max_output_tokens':0}):
        with pytest.raises(ValueError):
            run_agent({'task':'不能意外调用'}, runs_dir=tmp_path, **overrides)
    assert not list(tmp_path.iterdir())


def test_packaged_resources_are_runtime_inputs_and_match_their_source_snapshots():
    root=Path(__file__).resolve().parents[1]
    for packaged, original in [('agent-plan.json','data/model-manifests/volcengine-agent-plan.json'),
                               ('report-profile.json','data/routing/report-transfer-v1.json'),
                               ('compare-plan.json','data/task-plans/parallel-analysis-v2.json')]:
        assert json.loads(resource(packaged).read_text())==json.loads((root/original).read_text())


def test_cli_generates_safe_dsh_override_and_refuses_to_overwrite(tmp_path, capsys):
    output=tmp_path/'refractagent.json'
    args=['dsh-config','--output',str(output),'--runs-dir',str(tmp_path/'runs'),'--mode','live']
    assert main(args)==0
    patch=json.loads(output.read_text())
    assert patch[0]['id']=='refractagent'
    assert patch[0]['config']['allowPaidRuns'] is False
    assert Path(patch[0]['config']['pythonExecutable']).is_file()
    assert main(args)==1
