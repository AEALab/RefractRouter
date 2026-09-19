"""A3 分级器验证：构造 + 脱敏真实样本标注集；全部分级器本地调用，零网络零付费。

验证对象：
1. 确定性第一道（内置规则 + 自定义词）在两个标注集上的分级质量；
2. 分类器第二道的调用合同与 fail-safe 语义（本地替身，不发起模型调用）；
3. 超限与 unknown 状态在候选收窄中的保守行为（不静默放行到云端）。

已知边界（保守设计的代价）作为 known_issue 单独报告，不进入严格门槛：
手机号规则对订单流水号误报、自定义词子串命中、含空格秘密值漏报。
真实 ML 分类器的模型质量留待 A6（真实本地端点）验证。
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from refractrouter.application_config import SCHEMA_V2, compile_configuration
from refractrouter.privacy_placement import (RULES, classify_view, default_privacy, new_record,
    resolve_placement, scan_deterministic)
from refractrouter.task_plan import validate_plan

ROOT = Path(__file__).resolve().parents[1]
DATASETS = ('constructed-samples-v1.json', 'desensitized-real-samples-v1.json')
PLAN_PATH = ROOT / 'data/task-plans/parallel-analysis-v2.json'
TERMS = ('合同金额', '客户名单')
GATE = {'s1_precision': 1.0, 's1_recall': 1.0, 's3_precision': 1.0, 's3_recall': 1.0}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_datasets():
    directory = ROOT / 'data/privacy-classifier'
    sets = []
    for name in DATASETS:
        path = directory / name
        data = json.loads(path.read_text())
        errors = validate_dataset(data)
        if errors:
            raise ValueError(f'{name} invalid: {errors}')
        sets.append({'name': name, 'sha256': sha256(path), 'data': data})
    return sets


def validate_dataset(data):
    errors = []
    if data.get('schema_version') != 'privacy-classifier-samples-v1':
        errors.append('schema_version mismatch')
    items = data.get('items')
    if not isinstance(items, list) or not items:
        errors.append('items missing or empty')
        return errors
    ids = [item.get('id') for item in items]
    if len(set(ids)) != len(ids):
        errors.append('duplicate ids')
    for item in items:
        if item.get('grade') not in {'S1', 'S3'}:
            errors.append(f"{item.get('id')}: grade must be S1 or S3")
        if not isinstance(item.get('expected_hits'), list):
            errors.append(f"{item.get('id')}: expected_hits must be a list")
        if item.get('grade') == 'S1' and not item['expected_hits'] and not item.get('known_issue'):
            errors.append(f"{item.get('id')}: S1 without expected hits or known_issue")
        if item.get('grade') == 'S3' and item['expected_hits'] and not item.get('known_issue'):
            errors.append(f"{item.get('id')}: S3 with hits must declare known_issue")
        terms = item.get('sensitive_terms')
        if terms is not None and not isinstance(terms, list):
            errors.append(f"{item.get('id')}: sensitive_terms must be a list")
    return errors


def deterministic_pass(sets):
    rows = []
    for entry in sets:
        for item in entry['data']['items']:
            terms = item.get('sensitive_terms', [])
            privacy = {'enabled': True, 'sensitiveTerms': terms,
                       'classifier': {'enabled': False, 'modelId': None}, 'maxPromptBytes': 1048576}
            hits = scan_deterministic(item['text'], terms)
            grade = classify_view(item['text'], privacy=privacy)['grade']
            rows.append({'id': item['id'], 'set': entry['name'], 'category': item.get('category'),
                         'ground': item['grade'], 'predicted': grade,
                         'hits': hits, 'expected_hits': item['expected_hits'],
                         'known_issue': item.get('known_issue'),
                         'hits_match': hits == item['expected_hits']})
    return rows


def metrics(rows):
    clean = [row for row in rows if not row['known_issue']]
    tp = sum(1 for row in clean if row['ground'] == 'S1' and row['predicted'] == 'S1')
    tn = sum(1 for row in clean if row['ground'] == 'S3' and row['predicted'] == 'S3')
    fn = sum(1 for row in clean if row['ground'] == 'S1' and row['predicted'] == 'S3')
    fp = sum(1 for row in clean if row['ground'] == 'S3' and row['predicted'] == 'S1')
    result = {'clean_count': len(clean), 'tp': tp, 'tn': tn, 'fn': fn, 'fp': fp,
              's1_precision': tp / (tp + fp) if tp + fp else 1.0,
              's1_recall': tp / (tp + fn) if tp + fn else 1.0,
              's3_precision': tn / (tn + fn) if tn + fn else 1.0,
              's3_recall': tn / (tn + fp) if tn + fp else 1.0,
              'accuracy': (tp + tn) / len(clean) if clean else 1.0}
    result['gate_passed'] = all(result[key] >= value for key, value in GATE.items())
    return result


def rule_table(rows):
    rule_names = [name for name, _ in RULES] + [f'term:{term}' for term in TERMS]
    table = {}
    for name in rule_names:
        expected = [row for row in rows if name in row['expected_hits']]
        unexpected = [row for row in rows if name in row['hits'] and name not in row['expected_hits']]
        table[name] = {'expected_count': len(expected),
                       'matched': sum(1 for row in expected if name in row['hits']),
                       'unexpected_hits': [row['id'] for row in unexpected],
                       'unexpected_documented': all(row['known_issue'] for row in unexpected)}
    return table


def second_pass_scenarios():
    base = {'enabled': True, 'sensitiveTerms': [], 'maxPromptBytes': 1048576}
    enabled = {**base, 'classifier': {'enabled': True, 'modelId': 'local-work'}}
    rows = []

    def run(label, view, classifier):
        return classify_view(view, privacy=enabled, classifier=classifier)

    verdicts = [
        ('public', lambda view: {'label': 'public', 'reason': '无敏感迹象'}),
        ('sensitive', lambda view: {'label': 'sensitive', 'reason': '疑似个人合同'}),
        ('unknown', lambda view: {'label': 'unknown', 'reason': '无法判断'}),
        ('invalid', lambda view: {'label': 'weird'}),
    ]
    for name, classifier in verdicts:
        rows.append({'scenario': f'classifier:{name}', 'view': '公开内容',
                     'result': run(name, '公开内容', classifier)})

    def failing(view):
        raise RuntimeError('stand-in failure')
    rows.append({'scenario': 'classifier:exception', 'view': '公开内容',
                 'result': run('exception', '公开内容', failing)})
    rows.append({'scenario': 'classifier:missing', 'view': '公开内容',
                 'result': classify_view('公开内容', privacy=enabled, classifier=None)})

    calls = {'count': 0}

    def counting(view):
        calls['count'] += 1
        return {'label': 'sensitive', 'reason': '不应被调用'}
    preempted = classify_view('联系人 wang@example.com', privacy=enabled, classifier=counting)
    rows.append({'scenario': 'deterministic-preempts-classifier', 'view': '联系人 wang@example.com',
                 'result': preempted, 'classifier_calls': calls['count']})
    sized = classify_view('x' * 2048, privacy={**enabled, 'maxPromptBytes': 8}, classifier=counting)
    rows.append({'scenario': 'oversized-before-classifier', 'view': 'x' * 2048,
                 'result': sized, 'classifier_calls': calls['count']})
    return rows


def placement_models(local=True):
    raw = {'schemaVersion': SCHEMA_V2, 'billingUnit': 'USD', 'qualityMin': 80,
           'providers': [
               {'id': 'cloud', 'type': 'openai-compatible', 'baseUrl': 'https://cloud.example/v1',
                'credentialEnv': 'CLOUD_KEY'},
               {'id': 'local', 'type': 'openai-compatible', 'baseUrl': 'https://local.example/v1',
                'credentialEnv': 'LOCAL_KEY',
                **({'deployment': 'simulated-local'} if local else {})}],
           'models': [
               {'id': 'cloud-strong', 'provider': 'cloud', 'model': 'CLOUD_STRONG', 'role': 'candidate',
                'contextWindow': 131072, 'maxOutputTokens': 2048,
                'pricing': {'unit': 'USD', 'inputPer1k': .01, 'outputPer1k': .02},
                'routing': {'quality': 95, 'latencyMs': 3000}},
               {'id': 'local-work', 'provider': 'local', 'model': 'LOCAL_WORK', 'role': 'candidate',
                'contextWindow': 131072, 'maxOutputTokens': 2048,
                'pricing': {'unit': 'USD', 'inputPer1k': .001, 'outputPer1k': .002},
                'routing': {'quality': 85, 'latencyMs': 20000}},
               {'id': 'judge', 'provider': 'local', 'model': 'JUDGE', 'role': 'judge',
                'contextWindow': 131072, 'maxOutputTokens': 2048,
                'pricing': {'unit': 'USD', 'inputPer1k': .001, 'outputPer1k': .002}}]}
    return compile_configuration(raw).manifest.models


def fail_safe_checks():
    plan = validate_plan(json.loads(PLAN_PATH.read_text()))
    privacy = {'enabled': True, 'sensitiveTerms': [], 'maxPromptBytes': 8,
               'classifier': {'enabled': False, 'modelId': None}}
    views = {node.node_id: 'x' * 2048 for node in plan.nodes}
    rows = []
    record = new_record(privacy, placement_models(local=True))
    resolve_placement(plan=plan, node_views=views, models=placement_models(local=True),
                      privacy=privacy, record=record)
    rows.append({'scenario': 'oversized-with-local', 'status': record['status'],
                 'grades': {nid: row['grade'] for nid, row in record['grades'].items()},
                 'eligible': record['eligible_models']})
    record = new_record(privacy, placement_models(local=False))
    resolve_placement(plan=plan, node_views=views, models=placement_models(local=False),
                      privacy=privacy, record=record)
    rows.append({'scenario': 'oversized-cloud-only', 'status': record['status'],
                 'blocked': record['blocked']})
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path,
                        default=ROOT / 'reports/privacy-classifier-v1/validation-01')
    args = parser.parse_args(argv)
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error('必须使用全新输出目录')
    args.output_dir.mkdir(parents=True)

    sets = load_datasets()
    rows = deterministic_pass(sets)
    metric_rows = metrics(rows)
    second_pass = second_pass_scenarios()
    fail_safe = fail_safe_checks()
    known = [{'id': row['id'], 'ground': row['ground'], 'predicted': row['predicted'],
              'hits': row['hits'], 'issue': row['known_issue']}
             for row in rows if row['known_issue']]
    evidence = {
        'schema_version': 'privacy-classifier-validation-v1',
        'study': '隐私感知节点放置 A3：分级器验证',
        'issue': 87,
        'created': '2026-09-19',
        'zero_network_calls': True,
        'datasets': [{'name': entry['name'], 'sha256': entry['sha256'],
                      'item_count': len(entry['data']['items'])} for entry in sets],
        'frozen_terms': list(TERMS),
        'gate': GATE,
        'gate_passed': metric_rows['gate_passed'],
        'metrics': metric_rows,
        'rule_table': rule_table(rows),
        'known_issues': known,
        'second_pass_contract': [{'scenario': row['scenario'],
                                  'grade': row['result']['grade'],
                                  'reasons': row['result']['reasons'],
                                  'classifier_calls': row.get('classifier_calls')}
                                 for row in second_pass],
        'fail_safe_placement': fail_safe,
        'limitations': [
            'phone-cn 对形态相同的订单流水号保守误报，代价由 A4 开关对照量化。',
            '自定义敏感词按子串命中，保守误报；语义边界留待分类器第二道。',
            '含空格的秘密值暂不捕获（召回缺口），后续评估值字符集扩展。',
            'S2 在 v0 不产出；真实 ML 分类器的模型质量留待 A6 真实本地端点验证。']}
    validation_path = args.output_dir / 'validation.json'
    validation_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
    readme = ('# 隐私分级器验证 A3（validation-01）\n\n'
              '跟踪 Issue #87。本目录为分级器验证的冻结证据：两个标注集、确定性第一道指标、\n'
              '第二道调用合同与 fail-safe 放置检查。全部分级器本地调用，零网络、零付费模型调用。\n\n'
              '- 数据集与 sha256 见 validation.json 的 datasets 字段；\n'
              '- 严格门槛只统计非 known_issue 样本，门禁值见 gate 字段；\n'
              '- known_issue 是保守设计的已文档化代价，见 known_issues 与 limitations。\n\n'
              f'结论：{"通过" if evidence["gate_passed"] else "未通过"}严格门禁。\n')
    (args.output_dir / 'README.md').write_text(readme)
    index = {'validation.json': sha256(validation_path),
             'README.md': sha256(args.output_dir / 'README.md')}
    (args.output_dir / 'artifact-index.json').write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if evidence['gate_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
