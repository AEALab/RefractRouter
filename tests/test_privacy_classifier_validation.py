"""A3 分级器验证契约测试：标注集完整性、占位符政策、严格门槛与 fail-safe 语义。

全部零网络、零付费调用；数据集路径与验证逻辑与 experiments/validate_privacy_classifier.py
保持一致，测试重复加载同一份冻结标注集并复算门槛，防止规则改动悄悄破坏分级行为。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from refractrouter.privacy_placement import RULES, classify_view, default_privacy, scan_deterministic

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / 'data' / 'privacy-classifier'
DATASETS = ('constructed-samples-v1.json', 'desensitized-real-samples-v1.json')
EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+\.[A-Za-z]{2,12}')
PHONE_RE = re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)')
RESERVED_EMAIL_DOMAINS = {'example.com', 'example.org', 'example.net'}
RESERVED_PHONES = {'13800138000', '13900139000'}


def load(name):
    return json.loads((DATA_DIR / name).read_text())


def all_items():
    for name in DATASETS:
        data = load(name)
        assert data['schema_version'] == 'privacy-classifier-samples-v1'
        for item in data['items']:
            yield name, item


def test_dataset_schema_and_unique_ids():
    for name in DATASETS:
        data = load(name)
        ids = [item['id'] for item in data['items']]
        assert len(ids) == len(set(ids)), f'{name} 存在重复 id'
        for item in data['items']:
            assert item['grade'] in {'S1', 'S3'}
            assert isinstance(item['text'], str) and item['text']
            assert isinstance(item['expected_hits'], list)
            assert all(isinstance(hit, str) for hit in item['expected_hits'])
            if item['grade'] == 'S1':
                assert item['expected_hits'] or item.get('known_issue'), (
                    f"{item['id']} 为 S1 却无 expected_hits")
            if item['grade'] == 'S3' and item['expected_hits']:
                assert item.get('known_issue'), (
                    f"{item['id']} 为 S3 却命中规则，必须声明 known_issue")
        terms = [item.get('sensitive_terms') for item in data['items'] if 'sensitive_terms' in item]
        assert all(isinstance(term_list, list) for term_list in terms)


def test_desensitized_set_uses_only_reserved_placeholders():
    data = load('desensitized-real-samples-v1.json')
    for item in data['items']:
        for match in EMAIL_RE.findall(item['text']):
            assert match.rsplit('@', 1)[1] in RESERVED_EMAIL_DOMAINS, (
                f"{item['id']} 出现非保留域名邮箱：{match}")
        for match in PHONE_RE.findall(item['text']):
            assert match in RESERVED_PHONES, f"{item['id']} 出现非演示号码：{match}"
    # 构造集同样不得出现真实个人信息形态（全部为占位符或研究文本）。
    for item in load('constructed-samples-v1.json')['items']:
        for match in EMAIL_RE.findall(item['text']):
            assert match.rsplit('@', 1)[1] in RESERVED_EMAIL_DOMAINS, (
                f"{item['id']} 出现非保留域名邮箱：{match}")


def test_strict_gate_over_clean_items():
    tp = tn = fn = fp = 0
    for _, item in all_items():
        terms = item.get('sensitive_terms', [])
        privacy = {'enabled': True, 'sensitiveTerms': terms,
                   'classifier': {'enabled': False, 'modelId': None}, 'maxPromptBytes': 1048576}
        predicted = classify_view(item['text'], privacy=privacy)['grade']
        if item.get('known_issue'):
            continue
        if item['grade'] == 'S1' and predicted == 'S1':
            tp += 1
        elif item['grade'] == 'S1':
            fn += 1
        elif item['grade'] == 'S3' and predicted == 'S3':
            tn += 1
        else:
            fp += 1
    assert fn == 0, '严格门槛：S1 漏报必须为 0'
    assert fp == 0, '严格门槛：S3 误报必须为 0（known_issue 除外）'
    assert tp > 0 and tn > 0


def test_every_builtin_rule_has_positive_and_negative_coverage():
    text = {item['id']: item for _, item in all_items()}
    for name, _ in RULES:
        positives = [item_id for item_id, item in text.items()
                     if name in item['expected_hits'] and item['grade'] == 'S1']
        assert positives, f'规则 {name} 缺少 S1 正样本'
        negatives = [item_id for item_id, item in text.items()
                     if not item['expected_hits'] and name not in item['expected_hits']
                     and item['grade'] == 'S3']
        assert negatives, f'规则 {name} 缺少 S3 负样本'


def test_known_issue_items_are_documented_and_bounded():
    known = [item for _, item in all_items() if item.get('known_issue')]
    ids = {item['id'] for item in known}
    assert {'c-ph-n05', 'c-cred-n05', 'c-term-n01'} <= ids
    for item in known:
        assert item['known_issue'].strip()
        if item['grade'] == 'S3':
            assert item['expected_hits'], '误报类 known_issue 必须声明实际命中的规则'
    # 已知边界必须保持封闭：规则改动引入新的未文档化偏差时测试应失败。
    assert len(known) <= 5


def test_second_pass_contract_and_fail_safe():
    enabled = {'enabled': True, 'sensitiveTerms': [],
               'classifier': {'enabled': True, 'modelId': 'local-work'}, 'maxPromptBytes': 1048576}
    assert classify_view('公开内容', privacy=enabled,
                         classifier=lambda view: {'label': 'public', 'reason': '无'})['grade'] == 'S3'
    row = classify_view('公开内容', privacy=enabled,
                        classifier=lambda view: {'label': 'sensitive', 'reason': '疑似'})
    assert row['grade'] == 'S1' and row['reasons'] == ['classifier:sensitive', '疑似']
    assert classify_view('公开内容', privacy=enabled,
                         classifier=lambda view: {'label': 'unknown', 'reason': '无法判断'})['grade'] == 'unknown'
    assert classify_view('公开内容', privacy=enabled,
                         classifier=lambda view: {'label': 'weird'})['grade'] == 'unknown'
    assert classify_view('公开内容', privacy=enabled, classifier=None)['grade'] == 'unknown'
    assert classify_view('公开内容', privacy=enabled,
                         classifier=lambda view: (_ for _ in ()).throw(RuntimeError()))['grade'] == 'unknown'
    calls = {'count': 0}

    def counting(view):
        calls['count'] += 1
        return {'label': 'sensitive', 'reason': '不应被调用'}
    assert classify_view('联系人 wang@example.com', privacy=enabled, classifier=counting)['grade'] == 'S1'
    assert calls['count'] == 0, '确定性第一道命中时不得调用分类器'
    assert classify_view('x' * 2048, privacy={**enabled, 'maxPromptBytes': 8},
                         classifier=counting)['grade'] == 'unknown'
    assert calls['count'] == 0, '超限视图在分类器之前被拦截'


def test_credential_rules_cover_json_and_chinese_keys():
    # A3 验证驱动的两个召回修复：JSON 引号键名与中文密码/口令赋值。
    assert scan_deterministic('{"service":"sync","api_key":"sk-abcdef123456"}') == ['credential-assignment']
    assert scan_deterministic('数据库密码：Passw0rd2026') == ['credential-assignment-zh']
    assert scan_deterministic('口令: abcd1234efgh') == ['credential-assignment-zh']
    assert scan_deterministic('{"api_key":"","region":"cn"}') == []
    assert scan_deterministic('{"name":"api_key","enabled":true}') == []
    assert scan_deterministic('密码：ab') == []
    assert scan_deterministic('密钥：公开说明如下') == []
