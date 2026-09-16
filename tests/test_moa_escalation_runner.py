"""MoA 升级评审运行器的确定性测试；全部使用注入的模拟 CLI，不发起真实调用。"""
import json
from pathlib import Path

import pytest

import experiments.run_moa_escalation as runner
from refractrouter.moa_review import MOA_POLICY, default_invoke
from refractrouter.quality_study import load_study


STUDY = Path(__file__).resolve().parents[1] / 'data/quality-study-v1'


@pytest.fixture(scope='module')
def study():
    _, tasks, _references, controls, *_ = load_study(STUDY)
    return {task['task_id']: task for task in tasks}, controls


def fake_invoke(verdict='fail'):
    def invoke(reviewer, messages, schema=None):
        criteria = json.loads(messages[1]['content'])['criteria']
        body = json.dumps({'verdict': verdict, 'rationale': '合成升级依据',
                           'criteria': [{'criterion': criterion, 'verdict': verdict,
                                         'rationale': '合成升级依据'} for criterion in criteria]},
                          ensure_ascii=False)
        return 0, body, '', 12.0, 'test-version'
    return invoke


def test_envelope_counts_escalation_calls(study):
    frozen = runner.envelope(['a', 'b', 'c'])
    assert frozen['maximum_calls'] == 3 * len(MOA_POLICY['escalation'])
    assert frozen['real_model_calls'] == 0
    assert frozen['timeout_sum_seconds'] == frozen['maximum_calls'] * MOA_POLICY['timeout_seconds']
    assert frozen['policy_sha256']


def test_disputed_case_ids_reads_summary():
    summary = {'disputed': [{'case_id': 'x'}, {'case_id': 'y'}]}
    assert runner.disputed_case_ids(summary) == ['x', 'y']
    assert runner.disputed_case_ids({}) == []


def test_run_escalation_writes_two_records_per_case_and_resumes(study, tmp_path):
    tasks_by_id, controls = study
    cases = controls[:2]
    records = runner.run_escalation(cases, tasks_by_id, tmp_path, invoke=fake_invoke())
    assert [record['reviewer_id'] for record in records] == [
        MOA_POLICY['escalation'][0]['reviewer_id'], MOA_POLICY['escalation'][1]['reviewer_id'],
        MOA_POLICY['escalation'][0]['reviewer_id'], MOA_POLICY['escalation'][1]['reviewer_id']]
    assert all(record['status'] == 'reviewed' and record['role'] == 'escalation'
               for record in records)
    stored = runner.read_evidence(tmp_path / runner.EVIDENCE_NAME)
    assert len(stored) == 4
    assert {record['case_id'] for record in stored} == {case['case_id'] for case in cases}
    assert all(record['prompt_sha256'] for record in stored)
    again = runner.run_escalation(cases, tasks_by_id, tmp_path, invoke=fake_invoke())
    assert again == []
    assert len(runner.read_evidence(tmp_path / runner.EVIDENCE_NAME)) == 4


def test_summarize_counts_reviewed_and_failed(study, tmp_path):
    tasks_by_id, controls = study
    cases = controls[:1]
    records = runner.run_escalation(cases, tasks_by_id, tmp_path, invoke=fake_invoke('pass'))
    records[1] = dict(records[1], status='failed', verdict='pending', error='合成失败')
    summary = runner.summarize(cases, records, policy_sha256='sha')
    assert summary['calls'] == 2 and summary['reviewed'] == 1 and summary['failed'] == 1
    assert summary['verdict_counts'] == {'pass': 1, 'fail': 0, 'pending': 1}
    assert summary['by_case'][cases[0]['case_id']]
    assert summary['moa_review_cost']['calls'] == 2


def test_cli_preflight_then_live_with_injected_invoke(study, tmp_path, monkeypatch):
    tasks_by_id, controls = study
    case_ids = [case['case_id'] for case in controls[:2]]
    output = tmp_path / 'escalation-out'
    runner.main(['--study-dir', str(STUDY), '--case-id', case_ids[0], '--case-id', case_ids[1],
                 '--output-dir', str(output), '--preflight'])
    preflight = json.loads((output / 'preflight.json').read_text(encoding='utf-8'))
    assert preflight['envelope']['maximum_calls'] == 2 * len(MOA_POLICY['escalation'])
    assert preflight['envelope']['policy_sha256'] == preflight['policy_sha256']
    original = runner.run_escalation
    monkeypatch.setattr(runner, 'run_escalation',
                        lambda cases, by_id, path, **kwargs: original(
                            cases, by_id, path, invoke=fake_invoke('fail')))
    runner.main(['--study-dir', str(STUDY), '--case-id', case_ids[0], '--case-id', case_ids[1],
                 '--output-dir', str(output), '--live'])
    summary = json.loads((output / 'summary.json').read_text(encoding='utf-8'))
    assert summary['cases'] == 2 and summary['reviewed'] == 4 and summary['failed'] == 0
    assert summary['verdict_counts'] == {'pass': 0, 'fail': 4, 'pending': 0}
    assert set(json.loads((output / 'artifact-index.json').read_text(encoding='utf-8'))) >= {
        'preflight.json', 'summary.json', runner.EVIDENCE_NAME}


def test_cli_consensus_mode_reads_disputed_cases(study, tmp_path):
    _tasks_by_id, controls = study
    disputed = controls[0]['case_id']
    consensus_dir = tmp_path / 'consensus'
    consensus_dir.mkdir()
    (consensus_dir / 'summary.json').write_text(
        json.dumps({'disputed': [{'case_id': disputed}]}), encoding='utf-8')
    output = tmp_path / 'escalation-from-consensus'
    runner.main(['--study-dir', str(STUDY), '--consensus', str(consensus_dir),
                 '--output-dir', str(output), '--preflight'])
    preflight = json.loads((output / 'preflight.json').read_text(encoding='utf-8'))
    assert preflight['envelope']['cases'] == [disputed]


def test_live_rejects_changed_policy(study, tmp_path):
    _tasks_by_id, controls = study
    case = controls[0]['case_id']
    output = tmp_path / 'escalation-stale'
    runner.main(['--study-dir', str(STUDY), '--case-id', case, '--output-dir', str(output),
                 '--preflight'])
    path = output / 'preflight.json'
    frozen = json.loads(path.read_text(encoding='utf-8'))
    frozen['envelope']['policy_sha256'] = 'stale'
    path.write_text(json.dumps(frozen, ensure_ascii=False), encoding='utf-8')
    with pytest.raises(SystemExit):
        runner.main(['--study-dir', str(STUDY), '--case-id', case, '--output-dir', str(output),
                     '--live'])


def test_cli_requires_single_source_of_cases(study, tmp_path):
    _tasks_by_id, controls = study
    with pytest.raises(SystemExit):
        runner.main(['--study-dir', str(STUDY), '--consensus', str(tmp_path),
                     '--case-id', controls[0]['case_id'],
                     '--output-dir', str(tmp_path / 'out'), '--preflight'])


def test_default_invoke_is_zero_retry_cli_path():
    """升级运行器默认走真实 CLI 调用；此处只固定接口，不做网络调用。"""
    assert runner.run_escalation.__kwdefaults__ == {'invoke': default_invoke}
