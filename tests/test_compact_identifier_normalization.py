"""合法化标识不能改写图语义，也不能掩盖冲突或非法节点类型。"""
from copy import deepcopy
import pytest
from refractrouter.compact_planning import normalize_compact_ids, normalize_compact_types, compile_compact


def plan(first='cost-calc', second='answer', kind='synthesis'):
    return {'reason':'计算并交付','nodes':[
        {'id':first,'type':kind,'job':'计算费用','parents':[], 'difficulty':'low','risk':'low'},
        {'id':second,'type':'generation','job':'汇总完整交付','parents':[first], 'difficulty':'low','risk':'low'}]}


def test_identifier_normalization_preserves_exact_jobs_and_dependencies():
    raw = plan()
    old = deepcopy(raw)
    result, changes = normalize_compact_ids(raw)
    assert raw == old
    assert changes == {'cost-calc':'cost_calc'}
    assert result['nodes'][1]['parents'] == ['cost_calc']
    assert result['nodes'][0]['job'] == raw['nodes'][0]['job']
    assert compile_compact(result).final_node_id == 'answer'


def test_collision_and_unknown_type_are_still_rejected():
    with pytest.raises(ValueError, match='collision'):
        normalize_compact_ids(plan(second='cost_calc'))
    result, _ = normalize_compact_ids(plan(kind='analysis'))
    with pytest.raises(ValueError): compile_compact(result)


def test_documented_analysis_alias_preserves_jobs_edges_and_strict_unknown_rejection():
    raw = plan(first='facts', kind='analysis')
    original = deepcopy(raw)
    result, changes = normalize_compact_types(raw)
    assert raw == original
    assert changes == [{'node_id': 'facts', 'from': 'analysis', 'to': 'synthesis'}]
    original['nodes'][0]['type'] = 'synthesis'
    assert result == original
    assert compile_compact(result).final_node_id == 'answer'
    with pytest.raises(ValueError):
        compile_compact(normalize_compact_types(plan(kind='execute_shell'))[0])
    raw = plan(first='中文')
    result, changes = normalize_compact_ids(raw)
    assert changes == {} and result is raw
    with pytest.raises(ValueError): compile_compact(result)
