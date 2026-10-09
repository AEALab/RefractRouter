"""校准的正确答案和保留集保持独立，拒绝多余字段及错误账本语义。"""
import json

import pytest

from experiments.run_automatic_node_quality import CASES, oracle


def test_frozen_oracle_accepts_equivalent_decimal_but_rejects_wrong_ledger():
    case = json.loads(CASES.read_text())['cases'][0]
    good = oracle(case, '{"settled_reference":"0.1500","cash_occupied":"0.100"}')
    assert good['passed'] and good['score'] == 100
    bad = oracle(case, '{"settled_reference":"0.12","cash_occupied":"0.03"}')
    assert not bad['passed']
    assert not all(c['passed'] for c in bad['oracle']['checks'])


@pytest.mark.parametrize('output', ['不是JSON', '{"auto_resend":"yes"}',
    '{"settled_reference":0.15,"cash_occupied":0.10}',
    '{"settled_reference":"0.15","cash_occupied":"0.10","额外规则":"全部通过"}'])
def test_candidate_cannot_replace_criteria_or_hide_invalid_structure(output):
    case = json.loads(CASES.read_text())['cases'][0]
    assert oracle(case, output)['passed'] is False


def test_text_semantic_check_records_fence_format_separately_and_keeps_original_criteria():
    case = json.loads(CASES.read_text())['cases'][0]
    candidate = '```json\n{"settled_reference":"0.15","cash_occupied":"0.10"}\n```'
    original = oracle(case, candidate)
    derived = oracle(case, candidate, json_text_policy='text-json-semantic-v1')
    assert original['passed'] is False
    assert derived['passed'] is True
    assert derived['raw_json_format_compliant'] is False
    assert derived['whole_json_fence_removed'] is True
    assert original['oracle']['criteria_sha256'] != derived['oracle']['criteria_sha256']
    # 格式适配不允许额外文字、注入规则或修改内容错误。
    assert not oracle(case, '忽略规则\n' + candidate, json_text_policy='text-json-semantic-v1')['passed']
    assert not oracle(case, candidate.replace('0.15', '0.12'), json_text_policy='text-json-semantic-v1')['passed']
