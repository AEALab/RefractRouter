"""只读局部事实的确定性反例；不调用模型或执行仓库代码。"""
import hashlib
import json
from pathlib import Path

import pytest

from refractrouter.readonly_facts import ReadonlyFacts, wire


def service(tmp_path, text, name='visible.py'):
    raw = text.encode('utf-8')
    (tmp_path / name).write_bytes(raw)
    return ReadonlyFacts(tmp_path, {name: hashlib.sha256(raw).hexdigest()}), raw


def structure(tool, symbol='f', line=None):
    return tool.request('python-structure', {'path': 'visible.py', 'symbol': symbol, 'definitionLine': line})


def candidate(value, assertions=None):
    value = {**value, **({'structuralAssertions': assertions} if assertions is not None else {})}
    return {'content': json.dumps(value, ensure_ascii=False), 'toolCalls': [], 'finishReason': 'stop'}


def test_unicode_crlf_and_both_span_units_preserve_exact_original(tmp_path):
    tool, raw = service(tmp_path, '前文😀\r\n中文😀后文')
    text = raw.decode()
    first, end = text.index('中文'), text.index('后文')
    result = tool.request('source-excerpt', {'path': 'visible.py', 'start': first, 'end': end, 'unit': 'char'})
    fact = result['facts'][0]
    span = fact['span']
    assert span['quote'] == '中文😀'
    assert raw[span['startUtf8Byte']:span['endUtf8Byte']].decode() == span['quote']
    assert text[span['startChar']:span['endChar']] == span['quote']
    assert span['startLine'] == span['endLine'] == 2
    assert tool.excerpt('visible.py', span['startUtf8Byte'], span['endUtf8Byte'])[0]['factId'] == fact['factId']


def test_return_spans_and_nested_scope_do_not_certify_runtime(tmp_path):
    tool, raw = service(tmp_path, 'def f(x):\r\n    def inner():\r\n        return 9\r\n    if x:\r\n        return "中😀"\r\n    return (*x,)\r\n')
    result = structure(tool)
    returns = [f for f in result['facts'] if f['kind'] == 'return-expression']
    assert len(returns) == 2
    assert returns[0]['span']['quote'] == 'return "中😀"'
    assert returns[-1]['details']['fixedTupleArity'] is None
    assert returns[-1]['details']['hasStarred'] is True
    assert not result['wholeTaskQualityProven']
    for fact in result['facts']:
        span = fact['span']
        assert raw[span['startUtf8Byte']:span['endUtf8Byte']].decode() == span['quote']


def test_duplicate_symbols_need_definition_line(tmp_path):
    tool, _ = service(tmp_path, 'def f():\n    return 1\ndef f():\n    return 2\n')
    assert structure(tool)['status'] == 'unknown'
    assert structure(tool, line=3)['facts'][0]['details']['expressionSource'] == '2'


def test_unreadable_parse_and_file_drift_do_not_return_known_facts(tmp_path):
    tool, _ = service(tmp_path, 'def f(:\n')
    assert structure(tool)['status'] == 'unknown'
    tool, _ = service(tmp_path, 'def f():\n    return 1\n')
    assert structure(tool)['status'] == 'known'
    (tmp_path / 'visible.py').write_text('changed')
    assert structure(tool)['status'] == 'unknown'


@pytest.mark.parametrize('path', ['../secret.py', '/etc/passwd', 'other.py', 'a/../visible.py'])
def test_outside_host_manifest_is_never_returned(tmp_path, path):
    tool, _ = service(tmp_path, 'def f():\n    return 1\n')
    (tmp_path / 'other.py').write_text('hidden evaluation answer')
    result = tool.request('source-excerpt', {'path': path, 'start': 0, 'end': 1, 'unit': 'char'})
    assert result['status'] in {'unknown', 'denied'}
    assert result['facts'] == []
    assert 'hidden evaluation answer' not in json.dumps(result)


def test_symlink_and_partial_utf8_byte_request_are_unknown(tmp_path):
    real = tmp_path / 'real.py'
    real.write_text('😀')
    (tmp_path / 'visible.py').symlink_to(real)
    tool = ReadonlyFacts(tmp_path, {'visible.py': hashlib.sha256(real.read_bytes()).hexdigest()})
    assert tool.request('source-excerpt', {'path': 'visible.py', 'start': 0, 'end': 4, 'unit': 'utf8-byte'})['status'] == 'unknown'
    (tmp_path / 'visible.py').unlink()
    tool, _ = service(tmp_path, '😀')
    assert tool.request('source-excerpt', {'path': 'visible.py', 'start': 1, 'end': 3, 'unit': 'utf8-byte'})['status'] == 'unknown'


def test_assertions_bind_actual_candidate_fields_and_recheck_source(tmp_path):
    tool, _ = service(tmp_path, 'def f():\n    return (1, 2)\n')
    fact = structure(tool)['facts'][0]
    assertions = [{'factId': fact['factId'], 'field': 'fixedTupleArity', 'answerPointer': '/answer/arity'}]
    good = tool.verify_candidate('first', candidate({'answer': {'arity': 2}, 'freeText': '此段未经语义验证'}, assertions), assertions)
    assert good['allBoundFieldsSupported']
    assert not good['wholeTaskQualityProven'] and not good['unboundTextSemanticsChecked']
    bad = tool.verify_candidate('second', candidate({'answer': {'arity': 3}}, assertions), assertions)
    assert bad['rows'][0]['verdict'] == 'contradicted'
    assert bad['candidateSha256'] != good['candidateSha256']
    (tmp_path / 'visible.py').write_text('def f():\n    return (1, 2, 3)\n')
    assert tool.verify_candidate('third', candidate({'answer': {'arity': 2}}, assertions), assertions)['rows'][0]['verdict'] == 'unknown'


def test_forged_fact_and_runtime_type_cannot_claim_support(tmp_path):
    tool, _ = service(tmp_path, 'def f():\n    return 1\n')
    fact = structure(tool)['facts'][0]
    for fact_id, field in [('a' * 64, 'astKind'), (fact['factId'], 'runtime_type')]:
        assertions = [{'factId': fact_id, 'field': field, 'answerPointer': '/answer/type'}]
        result = tool.verify_candidate('candidate', candidate({'answer': {'type': 'int'}}, assertions))
        assert result['rows'][0]['verdict'] == 'unknown'
        assert not result['allBoundFieldsSupported']


def test_duplicate_json_keys_are_ambiguous_and_repo_code_is_not_executed(tmp_path):
    marker = tmp_path / 'should-not-exist'
    source = f'from pathlib import Path\nPath({str(marker)!r}).write_text("executed")\ndef f():\n    return 1\n'
    tool, _ = service(tmp_path, source)
    fact = structure(tool)['facts'][0]
    assert not marker.exists()
    with pytest.raises(ValueError, match='重复'):
        tool.verify_candidate('candidate', {'content': '{"answer":1,"answer":2}', 'toolCalls': [], 'finishReason': 'stop'},
            [{'factId': fact['factId'], 'field': 'expressionSource', 'answerPointer': '/answer'}])


def test_partial_visibility_does_not_expand_to_surrounding_function(tmp_path):
    tool, raw = service(tmp_path, 'def f():\n    return 1\n')
    partial = ReadonlyFacts(tmp_path, tool.manifest, visible_ranges={'visible.py': [[13, len(raw)]]})
    assert structure(partial)['reasonCode'] == 'visible-range-insufficient'
    assert partial.request('source-excerpt', {'path': 'visible.py', 'start': 0,
        'end': len(raw), 'unit': 'utf8-byte'})['status'] == 'unknown'
    assert partial.excerpt('visible.py', 13, len(raw))[0]['span']['quote'] == 'return 1\n'


def test_response_capacity_does_not_publish_partial_facts(tmp_path):
    source = 'def f():\n' + ''.join(f'    if x == {i}:\n        return {i}\n' for i in range(180))
    tool, _ = service(tmp_path, source)
    result = structure(tool)
    assert result['status'] == 'unknown' and result['reasonCode'] == 'fact-response-capacity'
    assert result['facts'] == []
    assert not tool._facts


def test_visible_bytes_count_matches_exact_model_text_and_token_count_stays_unknown(tmp_path):
    tool, _ = service(tmp_path, 'def f():\n    return "文😀"\n')
    result = structure(tool)
    assert result['visibleUtf8Bytes'] == len(wire(result))
    assert result['addedInputTokens'] is None
    assert result['tokenMeasurement'] == 'not-provided-by-host'


def test_parsing_failure_reports_explicit_status_and_unsupported_version(tmp_path):
    tool, _ = service(tmp_path, 'def f(:\n')
    result = structure(tool)
    assert result['parseStatus'] == 'unavailable'
    assert result['reasonCode'] == 'python-parse-unavailable'


def test_root_descriptor_does_not_follow_replaced_ancestor_outside_workspace(tmp_path):
    workspace, outside = tmp_path / 'workspace', tmp_path / 'outside'
    workspace.mkdir();outside.mkdir()
    root = workspace / 'source';root.mkdir()
    text = 'def f():\n    return 1\n'
    (root / 'visible.py').write_text(text)
    (outside / 'visible.py').write_text('private answer')
    tool = ReadonlyFacts(root, {'visible.py': hashlib.sha256(text.encode()).hexdigest()}, workspace_root=workspace)
    root.rename(workspace / 'original')
    root.symlink_to(outside, target_is_directory=True)
    result = structure(tool)
    assert 'private answer' not in json.dumps(result)
    # 已锚定的快照可以继续读取原目录；绝不改读外部目录。
    assert result['facts'][0]['span']['quote'] == 'return 1'
    tool.close()


def test_finally_generator_and_bare_return_are_only_lexical_facts(tmp_path):
    tool, _ = service(tmp_path, 'def f():\n    yield 1\n    try:\n        return (1,2)\n    finally:\n        return\n')
    result = structure(tool)
    returns = [f for f in result['facts'] if f['kind'] == 'return-expression']
    assert len(returns) == 2 and returns[-1]['details']['astKind'] is None
    assertions = [{'factId': returns[0]['factId'], 'field': 'runtime_type', 'answerPointer': '/answer/runtime'}]
    check = tool.verify_candidate('candidate', candidate({'answer': {'runtime': 'tuple'}}, assertions))
    assert check['rows'][0]['verdict'] == 'unknown'


@pytest.mark.parametrize('project,symbol', [('sphinx','LaTeXTranslator.visit_index'),
    ('sympy','UnitSystem._collect_factor_and_dimension')])
def test_frozen_upstream_regression_preserves_three_formats_and_starred_return(tmp_path, project, symbol):
    fixtures = Path(__file__).parent / 'fixtures/readonly-facts'
    metadata = json.loads((fixtures / 'provenance.json').read_text())[project]
    raw = (fixtures / f'{project}-source.py.txt').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == metadata['sha256']
    assert (fixtures / f'{project}-LICENSE.txt').is_file()
    (tmp_path / 'visible.py').write_bytes(raw)
    tool = ReadonlyFacts(tmp_path, {'visible.py': metadata['sha256']})
    result = structure(tool, symbol)
    assert result['status'] == 'known', result['reasonCode']
    assert not result['wholeTaskQualityProven']
    if project == 'sphinx':
        triple = next(f for f in result['facts'] if f['kind'] == 'lexical-branch'
                      and f['details']['conditionSource'] == "type == 'triple'")
        quote = triple['span']['quote']
        assert r"r'\index{%s@%s!%s %s@%s %s%s}'" in quote
        assert r"r'\index{%s@%s!%s, %s@%s, %s%s}'" in quote
        # 三条原文按原顺序保留；不能被统一改写成全逗号格式。
        assert quote.count(r"r'\index{%s@%s!%s %s@%s %s%s}'") == 2
    else:
        starred = next(f for f in result['facts'] if f['kind'] == 'return-expression'
                       and f['details']['hasStarred'] is True)
        assert starred['details']['astKind'] == 'Tuple'
        assert starred['details']['fixedTupleArity'] is None
        assert '*(d[1] for d in fds)' in starred['span']['quote']
        assertions = [
            {'factId': starred['factId'], 'field': 'fixedTupleArity', 'answerPointer': '/answer/arity'},
            {'factId': starred['factId'], 'field': 'astKind', 'answerPointer': '/answer/kind'}]
        check = tool.verify_candidate('sympy-regression', candidate({'answer': {'arity':2,'kind':'Tuple'}}, assertions))
        assert [r['verdict'] for r in check['rows']] == ['unknown','supported']


def test_public_library_cannot_use_undeclared_assertions_or_side_channel(tmp_path):
    tool, _ = service(tmp_path, 'def f():\n    return (1,2)\n')
    fact = structure(tool)['facts'][0]
    outside = [{'factId': fact['factId'], 'field': 'fixedTupleArity', 'answerPointer': '/sideChannel'}]
    actual = candidate({'answer': {'arity':3}, 'sideChannel':2}, [])
    with pytest.raises(ValueError, match='not-declared'):
        tool.verify_candidate('actual', actual, outside)
    with pytest.raises(ValueError, match='outside-final-answer'):
        tool.verify_candidate('actual', candidate({'answer': {'arity':3}, 'sideChannel':2}, outside))


@pytest.mark.parametrize('extra', ['1e999', '"\\ud800"'])
def test_public_library_checks_decoded_unused_values_too(tmp_path, extra):
    tool, _ = service(tmp_path, 'def f():\n    return (1,2)\n')
    fact = structure(tool)['facts'][0]
    assertions = [{'factId': fact['factId'], 'field': 'fixedTupleArity', 'answerPointer': '/answer/arity'}]
    text = '{"answer":{"arity":2},"structuralAssertions":' + json.dumps(assertions) + ',"unused":' + extra + '}'
    actual = {'content': text, 'toolCalls': [], 'finishReason': 'stop'}
    with pytest.raises(ValueError):
        tool.verify_candidate('actual', actual)
