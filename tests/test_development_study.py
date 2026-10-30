"""真实客户端＋账本＋事实宿主的确定性回归；传输层只用内存模拟。"""
import json
from pathlib import Path

import pytest

from refractrouter.development_study import (load_suite, preflight, run_generation, sha, wire)
from refractrouter.openai_compatible import TransportResponse


def suite(tmp_path):
    root = tmp_path / 'suite'; root.mkdir()
    source = root / 'visible' / 'dev-test' / 'a.py'; source.parent.mkdir(parents=True)
    source.write_text('CAP = 3\n')
    host = root / 'visible' / 'host.json'
    host.write_bytes(wire({'schemaVersion': 'readonly-facts-host-v1', 'root': str(source.parent),
        'files': {'a.py': sha(source.read_bytes())}}))
    finance = tmp_path/'finance.json'
    finance.write_bytes(wire({'plan_no_overage_is_user_declared': True, 'cash_limit_cny': '300',
        'cumulative_cash_protected_cny': '26.3507702502422', 'all_current_calls_settled': True,
        'unknown_reserves_released': False}))
    task = {'taskId': 'dev-test', 'root': 'visible/dev-test', 'criteria': {'question': '提取 CAP', 'contract': '只输出JSON'},
        'criteriaSha256': 'a'*64, 'half': 0, 'kind': '确定性提取',
        'host': 'visible/host.json', 'hostSha256': sha(host.read_bytes()),
        'files': [{'path': 'a.py', 'sha256': sha(source.read_bytes())}]}
    value = {'schemaVersion': 'whole-task-development-v1', 'tasks': [task],
        'models': {'S0': 'glm-5.3', 'W0': 'glm-5.3-flash', 'WF': 'glm-5.3-flash'},
        'order': [{'taskId': 'dev-test', 'arm': arm} for arm in ('S0', 'W0', 'WF')],
        'output': {'wireAnswerTokens': 131072, 'contextWindow': 1024000,
            'costContextEnvelopeTokens': 1048576, 'thinking': {'type': 'enabled'}, 'reasoningEffort': 'low'},
        'billing': {'maxStandardAFP': 4404.0192, 'incrementalCashConditionalOnPlanNoOverageCNY': 0},
        'funding': {'sourcePath': str(finance), 'sourceSha256': sha(finance.read_bytes())},
        'limits': {'maxCalls': 36, 'maxWFCallsPerTask': 4, 'maxInputBytes': 512000,
            'maxToolQueriesPerTask': 8, 'perCallTimeoutSeconds': 600, 'batchTimeboxSeconds': 10800}}
    (root / 'manifest.json').write_bytes(wire(value))
    return root, sha((root / 'manifest.json').read_bytes())


class FakeTransport:
    def __init__(self, *, fail=None, tool=True):
        self.requests = []; self.fail = fail; self.tool = tool

    def post(self, url, headers, body, timeout_seconds):
        request = json.loads(body); self.requests.append(request)
        assert '/api/plan/v3/chat/completions' in url
        assert request['max_tokens'] == 131072
        assert 'max_completion_tokens' not in request
        assert request['thinking'] == {'type': 'enabled'}
        assert request['reasoning_effort'] == 'low'
        if self.fail == 'authentication':
            return TransportResponse(401, {}, wire({'error': {'message': '模拟拒绝'}}))
        model = 'unexpected-model' if self.fail == 'identity' else request['model']
        usage = {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120,
            'completion_tokens_details': {'reasoning_tokens': 10}}
        message = {'role': 'assistant', 'content': '{"仅用于宿主传输回归":true}', 'reasoning_content': '模拟思考'}
        finish = 'stop'
        if request.get('tools') and self.tool:
            if request['messages'][-1]['role'] != 'tool':
                message['content'] = None
                message['tool_calls'] = [{'id': 'one', 'type': 'function', 'function': {
                    'name': 'refract_source_excerpt', 'arguments': json.dumps(
                        {'path': 'a.py', 'start': 0, 'end': 7, 'unit': 'char'})}}]
                if self.fail == 'bad-tool': message['tool_calls'][0]['function']['arguments'] = '[]'
                finish = 'tool_calls'
            else:
                assert request['messages'][-2]['reasoning_content'] == '模拟思考'
                assert 'CAP = 3' in request['messages'][-1]['content']
        result = {'model': model, 'id': 'fake', 'choices': [{'message': message, 'finish_reason': finish}]}
        if self.fail != 'usage': result['usage'] = usage
        return TransportResponse(200, {'x-request-id': 'simulated', 'set-cookie': '绝不保存'}, wire(result))


def test_preflight_reads_no_oracle_and_detects_source_drift(tmp_path):
    root, expected = suite(tmp_path)
    loaded_root, definition = load_suite(root, expected)
    result = preflight(loaded_root, definition)
    assert result['modelCalls'] == 0
    assert not result['hiddenEvaluationRead']
    assert result['maxCalls'] == 6
    assert result['maxStandardAFP'] == pytest.approx(734.0032)
    (root / 'visible/dev-test/a.py').write_text('CAP = 9\n')
    with pytest.raises(ValueError, match='漂移'):
        load_suite(root, expected)


@pytest.mark.parametrize('mutation', ['model-price', 'duplicate-order'])
def test_rejects_model_price_mismatch_and_duplicate_execution_even_if_rehashed(tmp_path, mutation):
    root, _ = suite(tmp_path)
    manifest = json.loads((root/'manifest.json').read_bytes())
    if mutation == 'model-price': manifest['models']['W0'] = 'glm-5.3'
    else: manifest['order'] = [manifest['order'][0]] * 3
    (root/'manifest.json').write_bytes(wire(manifest))
    with pytest.raises(ValueError):
        load_suite(root, sha((root/'manifest.json').read_bytes()))


@pytest.mark.parametrize('closed', [False, True])
def test_new_batch_requires_prior_batch_closed_and_unknown_reserves_retained(tmp_path, closed):
    root, _ = suite(tmp_path)
    manifest = json.loads((root/'manifest.json').read_bytes())
    finance_path = tmp_path/'finance.json'
    finance = json.loads(finance_path.read_bytes())
    finance.update(all_current_calls_settled=False, batch_closed_no_inflight=closed,
        outstanding_unknown_preserved=closed, cumulative_unknown_reserved_standard_afp='52.4288')
    finance_path.write_bytes(wire(finance))
    manifest['funding']['sourceSha256'] = sha(finance_path.read_bytes())
    (root/'manifest.json').write_bytes(wire(manifest))
    expected = sha((root/'manifest.json').read_bytes())
    if closed:
        assert load_suite(root, expected)
    else:
        with pytest.raises(ValueError, match='财务'):
            load_suite(root, expected)


def test_live_source_swap_cannot_send_hidden_answer_to_next_request(tmp_path):
    root, expected = suite(tmp_path)
    hidden = root/'isolated-evaluation/oracles.json'; hidden.parent.mkdir()
    hidden.write_text('隐藏答案不得发送')
    class SwapTransport(FakeTransport):
        def post(self, *args):
            response = super().post(*args)
            if len(self.requests) == 1:
                source = root/'visible/dev-test/a.py'
                source.unlink(); source.symlink_to(hidden)
            return response
    transport = SwapTransport()
    result = run_generation(root, expected, tmp_path/'run', {'CODEX_ARK_API_KEY': '模拟'}, transport=transport)
    assert result['modelCalls'] == 1
    assert result['stopReason'] == 'frozen-source-drift'
    assert '隐藏答案不得发送' not in json.dumps(transport.requests, ensure_ascii=False)


def test_three_arms_tool_history_full_ledger_and_no_credential_leak(tmp_path):
    root, expected = suite(tmp_path)
    transport = FakeTransport()
    output = tmp_path / 'run'
    result = run_generation(root, expected, output, {'CODEX_ARK_API_KEY': '模拟密钥勿存'}, transport=transport)
    assert result['modelCalls'] == 4
    assert result['completedResultCount'] == 3
    assert result['stopReason'] is None
    journal = json.loads((output / 'ledger.json').read_bytes())
    assert len(journal['calls']) == 4
    assert all(r['status'] == 'billed' and r['actual_model'] for r in journal['calls'])
    assert journal['chargedStandardAFPIncludingUnknownReserves'] == pytest.approx(.072)
    assert len(journal['results'][2]['toolQueries']) == 1
    for path in output.rglob('*'):
        if path.is_file():
            assert '模拟密钥勿存'.encode() not in path.read_bytes()
            assert '绝不保存'.encode() not in path.read_bytes()
    with pytest.raises(FileExistsError):
        run_generation(root, expected, output, {'CODEX_ARK_API_KEY': '模拟'}, transport=transport)
    assert len(transport.requests) == 4


@pytest.mark.parametrize('failure', ['identity', 'usage', 'authentication'])
def test_unknown_or_auth_stops_without_retry_and_protects_full_reserve(tmp_path, failure):
    root, expected = suite(tmp_path); output = tmp_path / 'run'
    transport = FakeTransport(fail=failure)
    result = run_generation(root, expected, output, {'CODEX_ARK_API_KEY': '模拟'}, transport=transport)
    assert result['modelCalls'] == 1
    assert result['completedResultCount'] == 0
    assert result['stopReason'] in {'unknown-usage', 'authentication'}
    ledger = json.loads((output / 'ledger.json').read_bytes())
    assert ledger['calls'][0]['status'] == 'unknown-usage'
    assert ledger['calls'][0]['charged'] == pytest.approx(471.8592)


def test_malformed_tool_is_known_failed_attempt_without_unbounded_loop(tmp_path):
    root, expected = suite(tmp_path)
    result = run_generation(root, expected, tmp_path/'run', {'CODEX_ARK_API_KEY': '模拟'},
        transport=FakeTransport(fail='bad-tool'))
    assert result['modelCalls'] == 3
    assert result['completedResultCount'] == 2
    ledger = json.loads((tmp_path/'run/ledger.json').read_bytes())
    assert len(ledger['calls']) == 3
    assert all(r['status'] == 'billed' for r in ledger['calls'])


def test_isolated_score_counts_failed_format_and_detects_candidate_substitution(tmp_path):
    from experiments.score_whole_task_development import score
    from refractrouter.development_study import save
    root, expected = suite(tmp_path); output = tmp_path/'run'
    oracle = {'oracle': {'criteriaSha256': 'a'*64, 'answers': {'cap': 3},
        'evidence': {'cap': [{'path': 'a.py', 'start': 0, 'end': 8, 'allOf': ['CAP = 3']}]},
        'expectedTrees': {}, 'filesSha256': {'a.py': sha(b'CAP = 3\n')}}}
    oracle_path = root/'isolated-evaluation/oracles.json'
    save(oracle_path, {'dev-test': oracle})
    run_generation(root, expected, output, {'CODEX_ARK_API_KEY': '模拟'}, transport=FakeTransport(tool=False))
    assessment = score(root, output, expected, sha(oracle_path.read_bytes()))
    assert all(i['passed'] is False and i['knownCost'] for i in assessment['items'])
    assert assessment['totals']['S0']['knownStandardAFP'] == pytest.approx(.054)
    assert assessment['comparisons']['WF']['batchCostComparable']
    assert not assessment['releaseAllowed']
    ledger = json.loads((output/'ledger.json').read_bytes())
    ledger['results'][0]['candidate'] = '{"替换答卷":true}'
    (output/'ledger.json').write_bytes(wire(ledger))
    with pytest.raises(ValueError, match='绑定'):
        score(root, output, expected, sha(oracle_path.read_bytes()))


@pytest.mark.parametrize('mutation', ['missing-call', 'changed-total', 'receipt-content', 'output-hash'])
def test_scoring_rejects_ledger_gaps_and_disagreeing_terminal_receipts(tmp_path, mutation):
    from experiments.score_whole_task_development import score
    from refractrouter.development_study import save
    root, expected = suite(tmp_path); output = tmp_path/'run'
    oracle = {'oracle': {'criteriaSha256': 'a'*64, 'answers': {'cap': 3},
        'evidence': {'cap': [{'path': 'a.py', 'start': 0, 'end': 8, 'allOf': ['CAP = 3']}]},
        'expectedTrees': {}, 'filesSha256': {'a.py': sha(b'CAP = 3\n')}}}
    oracle_path = root/'isolated-evaluation/oracles.json'; save(oracle_path, {'dev-test': oracle})
    run_generation(root, expected, output, {'CODEX_ARK_API_KEY': '模拟'}, transport=FakeTransport(tool=False))
    ledger = json.loads((output/'ledger.json').read_bytes())
    if mutation == 'missing-call': ledger['calls'].pop(0)
    if mutation == 'changed-total': ledger['chargedStandardAFPIncludingUnknownReserves'] = 0
    if mutation == 'receipt-content': ledger['calls'][0]['response']['content'] = '另一份答案'
    if mutation == 'output-hash': ledger['calls'][0]['output_sha256'] = '0'*64
    (output/'ledger.json').write_bytes(wire(ledger))
    with pytest.raises(ValueError): score(root, output, expected, sha(oracle_path.read_bytes()))


def test_only_one_prompt_revision_leaves_old_evidence_and_scoring_rules_unchanged(tmp_path):
    from experiments.revise_whole_task_development import revise
    from refractrouter.development_study import save
    root, _ = suite(tmp_path)
    finance_path = tmp_path/'finance.json'
    finance = json.loads(finance_path.read_bytes())
    finance.update(historical_unknown_cash_retained_cny='2', cumulative_known_standard_afp_lower='10',
        cumulative_unknown_reserved_standard_afp='20')
    finance_path.write_bytes(wire(finance))
    manifest = json.loads((root/'manifest.json').read_bytes())
    manifest['funding']['sourceSha256'] = sha(finance_path.read_bytes())
    (root/'manifest.json').write_bytes(wire(manifest))
    expected = sha((root/'manifest.json').read_bytes())
    save(root/'source-provenance.json', {})
    oracles = {'dev-test': {'oracle': {'criteriaSha256': 'a'*64, 'answers': {'cap': 3},
        'evidence': {'秘密评分': '不可出现在提示中'}, 'expectedTrees': {}}, 'goldSelfTest': '固定'}}
    save(root/'isolated-evaluation/oracles.json', oracles)
    run = tmp_path/'old-run'
    save(run/'ledger.json', {'manifestSha256': expected,
        'calls': [{'status': 'billed', 'charged': .1}, {'status': 'unknown-usage', 'charged': 52.4288}],
        'chargedStandardAFPIncludingUnknownReserves': 52.5288,
        'results': [{'candidate': '```json\n{}\n```'}]})
    save(run/'generation-summary.json', {'manifestSha256': expected, 'stopReason': 'unknown-usage'})
    before = {str(p): sha(p.read_bytes()) for p in [root/'manifest.json',
        root/'isolated-evaluation/oracles.json', run/'ledger.json']}
    revised = tmp_path/'revised'
    result = revise(root, run, revised)
    assert result['developmentRevision'] == 1
    newer = json.loads((revised/'isolated-evaluation/oracles.json').read_bytes())
    newer['dev-test']['oracle']['criteriaSha256'] = 'a'*64
    assert newer == oracles
    assert all(sha(Path(p).read_bytes()) == value for p, value in before.items())
    after = json.loads((revised/'financial-before.json').read_bytes())
    assert after['cumulative_known_standard_afp_lower'] == '10.1'
    assert after['cumulative_unknown_reserved_standard_afp'] == '72.4288'
    assert after['historical_unknown_cash_retained_cny'] == '2'
    assert not after['all_current_calls_settled']
    with pytest.raises(ValueError, match='第二次'):
        revise(revised, run, tmp_path/'forbidden-second-revision')
