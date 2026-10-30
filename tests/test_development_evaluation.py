"""封闭任务也须拒绝无关引用、伪补丁和以重复样本冒充质量证明。"""
import json

import pytest

from refractrouter.development_evaluation import evaluate, paired_screen, sha, tree_sha


FILES = {'a.py': 'CAP = 3\nOTHER = 1\n', 'b.py': 'from a import CAP\nvalue = CAP\n'}


def fixture():
    oracle = {'criteriaSha256': 'a'*64, 'answers': {'cap': 3},
        'evidence': {'cap': [{'path': 'a.py', 'start': 0, 'end': 8, 'allOf': ['CAP = 3']}]},
        'expectedTrees': {'a.py': tree_sha('CAP = 5\nOTHER = 1\n')},
        'filesSha256': {p: sha(t.encode()) for p, t in FILES.items()}}
    candidate = {'answers': {'cap': 3}, 'evidence': {'cap': [{'path': 'a.py', 'quote': 'CAP = 3'}]},
        'edits': [{'path': 'a.py', 'before': 'CAP = 3', 'after': 'CAP = 5'}]}
    return oracle, candidate


def test_complete_closed_task_and_equivalent_patch_spacing():
    oracle, candidate = fixture()
    assert evaluate(json.dumps(candidate), FILES, oracle)['passed']
    candidate['edits'][0]['after'] = 'CAP=5'
    assert evaluate(json.dumps(candidate), FILES, oracle)['passed']
    assert FILES['a.py'].startswith('CAP = 3')


@pytest.mark.parametrize('mutation', ['wrong-answer', 'unrelated-ref', 'duplicate-ref', 'bad-offset',
    'extra-behavior', 'missing-patch', 'other-file', 'bool-not-int', 'extra-key', 'markdown'])
def test_mutations_cannot_pass(mutation):
    oracle, candidate = fixture()
    if mutation == 'wrong-answer': candidate['answers']['cap'] = 4
    if mutation == 'bool-not-int': candidate['answers']['cap'] = True
    if mutation == 'unrelated-ref': candidate['evidence']['cap'].append({'path': 'a.py', 'quote': 'OTHER = 1'})
    if mutation == 'duplicate-ref': candidate['evidence']['cap'] *= 2
    if mutation == 'bad-offset': candidate['evidence']['cap'][0]['quote'] = 'CAP = 3\nOTHER = 1'
    if mutation == 'extra-behavior': candidate['edits'][0]['after'] = 'CAP = 5\nraise RuntimeError()'
    if mutation == 'missing-patch': candidate['edits'] = []
    if mutation == 'other-file': candidate['edits'].append({'path': 'b.py', 'before': 'value = CAP', 'after': 'value = 5'})
    if mutation == 'extra-key': candidate['explanation'] = '附加字段'
    content = json.dumps(candidate)
    if mutation == 'markdown': content = '```json\n' + content + '\n```'
    assert not evaluate(content, FILES, oracle)['passed']


def test_source_drift_and_invalid_oracle_are_infrastructure_errors():
    oracle, candidate = fixture()
    with pytest.raises(ValueError):
        evaluate(json.dumps(candidate), {**FILES, 'a.py': 'CAP = 4\n'}, oracle)
    oracle['evidence']['cap'][0]['end'] = 999
    with pytest.raises(ValueError): evaluate(json.dumps(candidate), FILES, oracle)


def test_invalid_coding_header_and_invalid_unicode_fail_without_executing_patch():
    oracle, candidate = fixture()
    candidate['edits'][0]['after'] = '# coding: unknown-encoding\nCAP = 5'
    assert not evaluate(json.dumps(candidate), FILES, oracle)['passed']
    result = evaluate('\ud800', FILES, oracle)
    assert not result['passed']
    assert result['candidateSha256'] is None
    assert result['failureCodes'] == ['output-format']


def test_curated_evidence_requires_full_negation_context():
    files = {'policy.txt': '不允许 use_cache = True'}
    oracle = {'criteriaSha256': 'a'*64, 'answers': {'allowed': False},
        'evidence': {'allowed': [{'path': 'policy.txt', 'start': 0, 'end': len(files['policy.txt']),
            'allOf': [files['policy.txt']]}]}, 'expectedTrees': {},
        'filesSha256': {p: sha(t.encode()) for p, t in files.items()}}
    candidate = {'answers': {'allowed': False}, 'evidence': {'allowed': [
        {'path': 'policy.txt', 'quote': 'use_cache = True'}]}, 'edits': []}
    assert not evaluate(json.dumps(candidate), files, oracle)['dimensions']['citations']


def test_semantically_frozen_alternative_fragments_are_accepted():
    files = {'a.py': 'CAP = 3\n# Default cap: 3\n'}
    oracle = {'criteriaSha256': 'a'*64, 'answers': {'cap': 3},
        'evidence': {'cap': [{'path': 'a.py', 'start': 0, 'end': len(files['a.py']),
            'allOf': [], 'anyOf': ['CAP = 3', '# Default cap: 3']}]}, 'expectedTrees': {},
        'filesSha256': {p: sha(t.encode()) for p, t in files.items()}}
    candidate = {'answers': {'cap': 3}, 'evidence': {'cap': [
        {'path': 'a.py', 'quote': '# Default cap: 3'}]}, 'edits': []}
    assert evaluate(json.dumps(candidate), files, oracle)['passed']
    oracle['evidence']['cap'][0]['anyOf'] = []
    with pytest.raises(ValueError): evaluate(json.dumps(candidate), files, oracle)


def rows(n):
    return [{'taskId': str(i), 'half': i % 2, 'baselinePassed': True, 'candidatePassed': True,
        'knownCost': True, 'completedPair': True, 'baselineCost': 1, 'candidateCost': .5} for i in range(n)]


def test_twenty_four_zero_losses_still_cannot_prove_three_percent_quality_margin():
    result = paired_screen(rows(24))
    assert result['qualityDifferenceLower95'] == pytest.approx(-.117346156, abs=1e-8)
    assert result['costTargetObserved']
    assert not result['qualityIntervalWithinMargin']
    assert not result['releaseAllowed']


def test_unknown_failure_kept_and_incomplete_cost_does_not_fake_savings():
    data = rows(6)
    data[0].update(candidatePassed=None, completedPair=False, knownCost=False)
    result = paired_screen(data)
    assert result['strongCompletedCandidateNotCompleted'] == 1
    assert result['savingsFraction'] is None
    assert not result['costTargetObserved']


def test_unknown_labels_cannot_become_zero_losses_or_improvements():
    data = rows(100)
    for row in data:
        row.update(baselinePassed=None, candidatePassed=None, completedPair=False, knownCost=False)
    result = paired_screen(data)
    assert result['qualityDifferenceObserved'] is None
    assert result['qualityDifferenceLower95'] is None
    assert not result['qualityIntervalWithinMargin']
    data[0]['candidatePassed'] = True
    assert paired_screen(data)['candidateImproved'] == 0


def test_both_predeclared_halves_must_save_and_ids_unique():
    data = rows(6)
    data[0]['candidateCost'] = 4
    assert not paired_screen(data)['costTargetObserved']
    data[1]['taskId'] = data[0]['taskId']
    with pytest.raises(ValueError): paired_screen(data)


@pytest.mark.parametrize('changes', [{'minimum_savings': .1}, {'quality_margin': .04}])
def test_no_posthoc_relaxation(changes):
    with pytest.raises(ValueError): paired_screen(rows(6), **changes)
