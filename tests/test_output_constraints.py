"""最终长度契约的真实失败回放；全部生成与评审使用离线替身。"""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from refractrouter.agent import run_agent
from refractrouter.agent_cli import main
from refractrouter.output_constraints import check_output_constraints
from tests.test_text_tasks import Client, live
from tests.test_task_decomposition import example

ROOT = Path(__file__).resolve().parents[1]
LIMIT = {'maxLength': 250, 'unit': 'unicode-code-points', 'countWhitespace': False}


class AnswerClient(Client):
    def __init__(self, answer, **kwargs):
        super().__init__(**kwargs)
        self.answer = answer

    def complete(self, model, messages, *, json_mode=False):
        result = super().complete(model, messages, json_mode=json_mode)
        if model.role != 'judge' and not json_mode:
            return replace(result, content=self.answer)
        return result


@pytest.fixture(autouse=True)
def no_network():
    with patch('socket.socket', side_effect=AssertionError('no paid calls in tests')):
        yield


@pytest.mark.parametrize(('answer', 'unit', 'spaces', 'actual'), [
    ('中文 A1，。\n\t\u3000', 'unicode-code-points', True, 10),
    ('中文 A1，。\n\t\u3000', 'unicode-code-points', False, 6),
    ('中 A\n', 'utf8-bytes', True, 6),
    ('中 A\n', 'utf8-bytes', False, 4),
    ('😀e\u0301', 'unicode-code-points', True, 3),
    ('😀e\u0301', 'utf8-bytes', True, 7),
    ('a\u00a0b\u200bc', 'unicode-code-points', False, 4),  # 零宽空格不属于 isspace。
])
def test_explicit_counting_units_and_whitespace(answer, unit, spaces, actual):
    for maximum in (actual - 1, actual, actual + 1):
        result = check_output_constraints({'maxLength': maximum, 'unit': unit, 'countWhitespace': spaces}, answer)
        assert result['actual_length'] == actual
        assert result['passed'] is (actual <= maximum)
        assert result['output_sha256'] == hashlib.sha256(answer.encode()).hexdigest()


@pytest.mark.parametrize('constraints', [None, {}, [], {'maxLength': 250},
    {**LIMIT, 'maxLength': True}, {**LIMIT, 'maxLength': 0}, {**LIMIT, 'maxLength': -1},
    {**LIMIT, 'maxLength': 250.5}, {**LIMIT, 'maxLength': float('nan')},
    {**LIMIT, 'maxLength': 1000001}, {**LIMIT, 'unit': 'tokens'},
    {**LIMIT, 'unit': []}, {**LIMIT, 'countWhitespace': 0}, {**LIMIT, 'repair': True},
])
def test_invalid_constraints_rejected_before_record_or_call(tmp_path, constraints):
    client = AnswerClient('答案')
    with pytest.raises(ValueError, match='outputConstraints'):
        run_agent({'task': '摘要', 'outputConstraints': constraints}, mode='live',
                  execute_paid_run=True, preset='ark-agent-plan', runs_dir=tmp_path, client=client)
    assert not client.calls and not list(tmp_path.iterdir())


def test_original_m3_answer_fails_length_even_when_independent_judge_passes(tmp_path):
    archive = ROOT/'reports/refractagent-local/20260908/live-answers.md'
    original = archive.read_bytes()
    answer = original.decode().split('## balanced\n\n', 1)[1].split('\n\n## quality', 1)[0]
    assert len(answer) == 283
    client = AnswerClient(answer)
    result = run_agent({'task': '比较 A/B，最多 250 个非空白字符。', 'outputConstraints': LIMIT},
        mode='live', execute_paid_run=True, preset='ark-agent-plan', runs_dir=tmp_path, client=client)
    assert result['status'] == 'output-constraint-failed'
    assert result['generation_status'] == 'completed' and result['quality']['passed'] is True
    assert result['format_validation']['actual_length'] == 263
    assert result['format_validation']['passed'] is False
    assert result['issues'] == ['output-length-exceeded']
    assert result['answer'] == answer and len(client.calls) == 2
    assert result['costs']['production'] > 0 and result['costs']['evaluation'] > 0
    saved = json.loads(Path(result['result_path']).read_text())
    assert saved['format_validation'] == result['format_validation']
    assert saved['calls'][0]['response_output'] == answer
    assert (Path(result['run_dir'])/'answer.md').read_text() == answer
    assert json.loads((Path(result['run_dir'])/'summary.json').read_text()) == result
    assert archive.read_bytes() == original


def test_no_default_250_limit_or_free_text_inference(tmp_path):
    result = run_agent({'task': '材料引用「250 字以内」，请分析它。'}, mode='live',
        execute_paid_run=True, preset='ark-agent-plan', runs_dir=tmp_path, client=AnswerClient('长文' * 300))
    assert result['status'] == 'completed' and len(result['answer']) == 600
    assert result['format_validation']['status'] == 'not-requested'
    assert result['format_validation']['passed'] is None


def test_final_constraint_does_not_limit_intermediate_nodes_or_trigger_recovery():
    client = AnswerClient('答案' * 150)
    result = live(client, plan=example(), outputConstraints=LIMIT, maxNodeFallbacks=2)
    assert result['status'] == 'output-constraint-failed' and len(client.calls) == 4
    assert result['recovery']['events'] == []
    payloads = [json.loads(messages[-1]['content']) for _, messages in client.calls]
    assert all('output_constraints' not in p for p in payloads[:2])
    assert payloads[2]['output_constraints'] == LIMIT
    assert '最终交付正文' in payloads[2]['output_constraint_instruction']


def test_length_result_and_answer_checkpoint_survive_unavailable_judge(tmp_path):
    result = run_agent({'task': '摘要', 'outputConstraints': LIMIT}, mode='live',
        execute_paid_run=True, preset='ark-agent-plan', runs_dir=tmp_path,
        client=AnswerClient('长' * 251, bad_judge=True))
    assert result['status'] == 'failed' and result['generation_status'] == 'completed'
    assert result['quality'] is None and result['format_validation']['passed'] is False
    assert result['answer'] == '长' * 251 and result['costs']['evaluation'] > 0


def test_passing_length_does_not_override_failed_semantic_review():
    from tests.test_application_boundaries import OmittedRequirementJudge
    result = live(OmittedRequirementJudge(), plan=example('single-answer'), outputConstraints=LIMIT)
    assert result['status'] == 'quality-failed'
    assert result['evaluation']['passed'] is False and result['format_validation']['passed'] is True


def test_check_is_persisted_before_judge_dispatch():
    from refractrouter.task_runtime import run_task
    from tests.test_text_tasks import REQUEST, MANIFEST, PROFILE
    snapshots = []

    class CheckpointJudge(AnswerClient):
        def complete(self, model, messages, *, json_mode=False):
            if model.role == 'judge':
                assert snapshots[-1]['format_validation']['passed'] is False
                assert snapshots[-1]['generation_status'] == 'completed'
                assert snapshots[-1]['final_output'] == self.answer
            return super().complete(model, messages, json_mode=json_mode)

    run_task({**REQUEST, 'plan': example('single-answer'), 'outputConstraints': LIMIT},
        MANIFEST, {**PROFILE, 'kind': 'empirical'}, client=CheckpointJudge('长' * 251),
        production_limit=100, evaluation_limit=100, checkpoint=lambda r: snapshots.append(deepcopy(r)))


@pytest.mark.parametrize('mode', ['preflight', 'demo'])
def test_no_actual_validation_claim_for_preview_or_demo(tmp_path, mode):
    result = run_agent({'task': '只用一字回答', 'outputConstraints': {**LIMIT, 'maxLength': 1}},
                       mode=mode, runs_dir=tmp_path)
    assert result['format_validation']['status'] == 'not-evaluated'
    assert result['format_validation']['passed'] is None and result['quality'] is None
    assert result['generation_status'] == ('not-started' if mode == 'preflight' else 'simulated')


def test_production_failure_cannot_pass_length_as_an_empty_answer(tmp_path):
    result = run_agent({'task': '摘要', 'outputConstraints': LIMIT}, mode='live',
        execute_paid_run=True, preset='ark-agent-plan', runs_dir=tmp_path, client=Client(fail_at=1))
    assert result['status'] == 'failed' and result['generation_status'] == 'failed'
    assert not result['answer'] and result['format_validation']['status'] == 'not-evaluated'
    assert result['costs']['unconfirmed'] > 0


def test_cli_accepts_structured_constraint_request_and_replays_result(tmp_path, capsys):
    request = tmp_path/'request.json'
    request.write_text(json.dumps({'task': '摘要', 'outputConstraints': LIMIT}))
    assert main(['run', '--request-file', str(request), '--runs-dir', str(tmp_path/'runs')]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['format_validation']['constraints'] == LIMIT
    assert main(['show', result['run_dir']]) == 0
    assert json.loads(capsys.readouterr().out) == result
