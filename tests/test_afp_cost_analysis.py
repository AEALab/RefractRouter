"""AFP 成本分解的确定性回归；全部使用合成归档，不发起模型调用。"""
import hashlib
import json
from pathlib import Path

import pytest


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def _index(source):
    files = [path for path in source.rglob('*') if path.is_file() and path.name != 'artifact-index.json']
    _write_json(
        source / 'artifact-index.json',
        {str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files},
    )


def _frozen():
    model = {
        'id': 'model-a',
        'model': 'model-a',
        'provider': 'test',
        'role': 'candidate',
        'pricing': {'unit': 'AFP', 'inputPer1k': 0.1, 'outputPer1k': 0.1, 'cachedInputPer1k': 0.1},
    }
    judge = {
        'id': 'judge-a',
        'model': 'judge-a',
        'provider': 'test',
        'role': 'judge',
        'pricing': {'unit': 'AFP', 'inputPer1k': 0.2, 'outputPer1k': 0.2, 'cachedInputPer1k': 0.2},
    }
    configuration = {'billingUnit': 'AFP', 'models': [model, judge]}
    return {
        'sha256': 'synthetic-freeze',
        'protocol': {'configuration': configuration, 'application_configuration': configuration},
    }


def _call(label, model, category, charged, *, cached=0, cache_available=True):
    input_tokens, output_tokens = (1000, 1000) if model == 'model-a' else (500, 250)
    return {
        'label': label,
        'model_id': model,
        'category': category,
        'charged': charged,
        'status': 'billed',
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'reasoning_tokens': output_tokens // 2,
        'cached_input_tokens': cached,
        'cache_usage_available': cache_available,
        'latency_ms': 1000,
        'ttft_ms': None,
        'finish_reason': 'stop',
    }


def _source(tmp_path, *, probe_cached=True):
    source = tmp_path / 'source'
    _write_json(source / 'frozen.json', _frozen())
    probe = _call(
        'model-a/stable-v1/repeat-prefix/0',
        'model-a',
        'production',
        0.2,
        cached=100,
        cache_available=probe_cached,
    )
    _write_json(source / 'probe-ledger.json', {'charged': 0.2, 'calls': [probe]})
    run_dir = source / 'direct' / 'run'
    _write_json(run_dir / 'result.json', {'calls': [
        _call('answer', 'model-a', 'production', 0.2),
        _call('final-judge', 'judge-a', 'evaluation', 0.15),
    ]})
    _write_json(source / 'applications.json', [{
        'id': 'direct',
        'status': 'completed',
        'prefix_policy': 'stable-v1',
        'wall_time_ms': 2000,
        'run_dir': str(run_dir),
        'plan': {'nodes': [{'node_id': 'answer'}]},
        'quality': {'score': 90, 'passed': True},
    }])
    _write_json(source / 'run-status.json', {'actual_calls': 3})
    _index(source)
    return source


def test_afp_breakdown_separates_probe_production_and_evaluation(tmp_path):
    from experiments.analyze_afp_cost import analyze

    result = analyze(_source(tmp_path), tmp_path / 'analysis')
    assert result['ledger_calls'] == result['billed_calls'] == 3
    assert result['total_afp'] == 0.55
    assert result['input_afp'] == 0.3
    assert result['output_afp'] == 0.25
    assert result['output_afp_share'] == 0.45454545
    by_purpose = {row['purpose']: row for row in result['by_purpose']}
    assert by_purpose['probe']['billed_afp'] == 0.2
    assert by_purpose['application-production']['billed_afp'] == 0.2
    assert by_purpose['application-evaluation']['billed_afp'] == 0.15
    assert result['application_totals']['total_afp'] == 0.35
    assert result['application_totals']['output_afp'] == 0.15
    assert result['applications'][0]['afp_per_accepted_task'] is None
    assert result['human_quality_verified'] is False
    readme = (tmp_path / 'analysis' / 'README.md').read_text()
    assert '诊断探针消耗 0.20000 AFP' in readme
    assert '应用侧输出 AFP 占 42.86%' in readme


def test_missing_cache_field_is_unknown_and_not_zero(tmp_path):
    from experiments.analyze_afp_cost import analyze

    source = _source(tmp_path, probe_cached=False)
    _write_json(source / 'run-status.json', {'actual_calls': 3})
    _index(source)
    result = analyze(source, tmp_path / 'analysis')
    assert result['cached_tokens'] == 0
    assert result['cache_unknown_calls'] == 1
    probe = next(row for row in result['by_purpose'] if row['purpose'] == 'probe')
    assert probe['cache_unknown_calls'] == 1


def test_cost_mismatch_is_rejected(tmp_path):
    from experiments.analyze_afp_cost import analyze

    source = _source(tmp_path)
    ledger = json.loads((source / 'probe-ledger.json').read_text())
    ledger['calls'][0]['charged'] = 0.21
    _write_json(source / 'probe-ledger.json', ledger)
    _index(source)
    with pytest.raises(ValueError, match='调用成本与冻结价格不一致'):
        analyze(source, tmp_path / 'analysis')


def test_tampered_artifact_is_rejected(tmp_path):
    from experiments.analyze_afp_cost import analyze

    source = _source(tmp_path)
    (source / 'run-status.json').write_text(json.dumps({'actual_calls': 4}))
    with pytest.raises(ValueError, match='证据摘要不一致'):
        analyze(source, tmp_path / 'analysis')
