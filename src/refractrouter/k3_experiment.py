"""K3 整任务基线与质量约束成本选路的分阶段实验。"""
from dataclasses import asdict, replace
import hashlib
import json

from .blind_review import digest, packet, template, import_reviews, FINAL_LIMITS, NODE_LIMITS
from .cost_selection import select_cost_effective
from .deepagents_executor import DeepAgentsGraphExecutor
from .evidence_state import with_evidence_state
from .execution_modes import run_one_shot
from .model_registry import ModelRegistry
from .node_contracts import CONTRACT_FAILURES
from .schemas import TaskDAG, NodeSpec, SourceDocument, NodeResult, ModelSpec
from .scoring import node_contract_checks


def chinese_task(task):
    names = {'Executive Summary': '执行摘要', 'Background': '背景', 'Selection Criteria': '选型标准',
             'Platform Comparison': '平台比较', 'Risks': '风险', 'Conclusion': '结论', 'References': '参考资料'}
    return with_evidence_state(replace(task, expected_claims=(),
        required_sections=tuple(names.get(s, s) for s in task.required_sections),
        output_constraints=(*task.output_constraints, '标题及正文使用简体中文；利用相关来源完成实质比较、取舍分析与有依据的结论。')))


def load_task(data):
    return TaskDAG(**{**data, 'nodes': tuple(NodeSpec(**n) for n in data['nodes']),
        'source_documents': tuple(SourceDocument(**s) for s in data['source_documents'])})


def roles(manifest):
    baseline = replace(manifest.judge, model_id='k3-baseline', role='baseline')
    if baseline.api_model != 'kimi-k3' or any(m.api_model == baseline.api_model for m in manifest.candidates):
        raise ValueError('基线必须是独立于节点候选池的 Kimi-K3')
    return baseline, manifest.candidate_registry()


def prepare(task, manifest, adapter, *, simulation, baseline_only=False):
    baseline, registry = roles(manifest)
    a = run_one_shot(task, baseline.model_id, adapter, ModelRegistry([baseline]))
    if a.failure_types or not a.final_output or any(n.status != 'ok' for n in a.node_results):
        unknown_usage = any(n.attempts > 0 and n.input_tokens == n.output_tokens == 0
                            for n in a.node_results)
        return dict(version='k3-baseline-v1', stage='blocked', reason='baseline-failed',
            simulation=simulation, task=asdict(task), models=[asdict(m) for m in registry.list()],
            baseline_model=asdict(baseline), baseline=asdict(a), reference=None,
            rows=[], node_packet=None, node_mapping=None,
            prepare_cost=None if unknown_usage else a.total_cost, known_prepare_cost=a.total_cost)
    if baseline_only:
        return dict(version='k3-baseline-v1', stage='baseline-ready', simulation=simulation,
            task=asdict(task), models=[asdict(m) for m in registry.list()], baseline_model=asdict(baseline),
            baseline=asdict(a), reference=None, rows=[], node_packet=None, node_mapping=None,
            prepare_cost=a.total_cost, known_prepare_cost=a.total_cost)
    executor = DeepAgentsGraphExecutor(task, adapter, registry)
    reference = executor.execute({n.node_id: registry.strongest().model_id for n in task.nodes}, 'reference')
    context = {n.node_id: n.output for n in reference.node_results}
    status = {n.node_id: n.status for n in reference.node_results}
    rows = []
    records = []
    for node in task.nodes:
        for model in registry.list():
            if any(status[p] != 'ok' for p in node.parents):
                result = NodeResult(node.node_id, node.node_type, model.model_id, '', 0, 0, 0, 0,
                    billing_unit=model.billing_unit, status='failed', failure_type='invalid-reference-context', attempts=0)
            else:
                result = executor.probe_node(node.node_id, model.model_id, context)
            upstream = {p: context[p] for p in node.parents}
            checks = node_contract_checks(task, node, result.output, upstream)
            rejected = result.failure_type in CONTRACT_FAILURES or (result.status == 'ok' and checks['score_cap'] == 0)
            eligible = result.status == 'ok' and checks['score_cap'] > 0
            row = dict(task_id=task.task_id, repeat=1, stage='probe', node_id=node.node_id,
                model_id=model.model_id, upstream=upstream, upstream_sha256=digest(upstream),
                output_sha256=hashlib.sha256(result.output.encode()).hexdigest(), node_result=asdict(result),
                eligible=eligible, evaluation=dict(method='deterministic-rejection' if rejected else 'pending',
                    final_score=0 if rejected else None, error=None if rejected else 'awaiting-independent-review', checks=checks))
            rows.append(row)
            if eligible:
                records.append(dict(record_id=f'{node.node_id}:{model.model_id}', output=result.output,
                    upstream=upstream, node_type=node.node_type, node_request=node.prompt_template))
    public, private = packet(task, records, kind='node')
    return dict(version='k3-baseline-v1', stage='node-review-ready', simulation=simulation,
        task=asdict(task), models=[asdict(m) for m in registry.list()], baseline_model=asdict(baseline),
        baseline=asdict(a), reference=asdict(reference), rows=rows, node_packet=public, node_mapping=private,
        prepare_cost=round(a.total_cost+reference.total_cost+sum(r['node_result']['cost'] for r in rows), 8))


def forbidden(state):
    return [state['baseline_model']['api_model'], *(m['api_model'] for m in state['models'])]


def compose(state, reviews, adapter, *, quality_floor=85, max_quality_gap=5):
    task = load_task(state['task'])
    registry = ModelRegistry(ModelSpec(**m) for m in state['models'])
    judged = import_reviews(state['node_packet'], reviews, forbidden_models=forbidden(state), simulation=state['simulation'])
    rows = json.loads(json.dumps(state['rows']))
    mapped = {state['node_mapping']['sample_records'][sid]: row for sid, row in judged.items()}
    for row in rows:
        review = mapped.get(f"{row['node_id']}:{row['model_id']}")
        if review:
            row['evaluation'] = {**row['evaluation'], 'error': None,
                'method': 'independent-human-review' if review['reviewer']['kind']=='human' else 'independent-node-judge',
                'final_score': min(review['final_score'], row['evaluation']['checks']['score_cap']), 'review': review}
    decision = select_cost_effective(rows, task=task, model_ids=[m.model_id for m in registry.list()],
        quality_floor=quality_floor, max_quality_gap=max_quality_gap)
    result = {**state, 'rows': rows, 'selection': decision, 'node_reviews': reviews}
    if state['baseline']['failure_types']:
        return {**result, 'stage': 'blocked', 'reason': 'baseline-failed', 'routed_cost': 0}
    if not decision['route_executable']:
        return {**result, 'stage': 'blocked', 'routed_cost': 0}
    routed = DeepAgentsGraphExecutor(task, adapter, registry).execute(decision['assignments'], 'cost-routed-dag')
    if routed.failure_types:
        return {**result, 'stage': 'blocked', 'reason': 'routed-execution-failed',
                'routed': asdict(routed), 'routed_cost': routed.total_cost}
    public, private = packet(task, [dict(record_id='baseline', output=state['baseline']['final_output']),
                                   dict(record_id='routed', output=routed.final_output)], kind='final')
    return {**result, 'stage': 'final-review-ready', 'routed': asdict(routed), 'routed_cost': routed.total_cost,
            'final_packet': public, 'final_mapping': private}


def finalize(state, reviews, *, calibration_passed):
    if state.get('stage') != 'final-review-ready':
        raise ValueError('尚未完成两组真实执行')
    judged = import_reviews(state['final_packet'], reviews, forbidden_models=forbidden(state), simulation=state['simulation'])
    mapped = {state['final_mapping']['sample_records'][sid]: row for sid, row in judged.items()}
    a, b = state['baseline'], state['routed']
    complete = all(not r['failure_types'] and r['final_output'] and all(n['status']=='ok' for n in r['node_results']) for r in [a,b])
    ready = complete and calibration_passed
    qa, qb = mapped['baseline']['final_score'], mapped['routed']['final_score']
    setup = state['prepare_cost']-a['total_cost']
    reduction = (a['total_cost']-b['total_cost'])/a['total_cost']*100 if a['total_cost'] else None
    first_use_reduction = (a['total_cost']-setup-b['total_cost'])/a['total_cost']*100 if a['total_cost'] else None
    quality_acceptable = ready and qb >= qa-3
    return {'version': 'k3-baseline-v1', 'simulation': state['simulation'],
        'status': 'complete' if ready else 'incomplete', 'calibration_passed': calibration_passed,
        'baseline_quality': qa, 'routed_quality': qb, 'quality_delta': qb-qa if ready else None,
        'baseline_cost': a['total_cost'], 'routed_cost': b['total_cost'], 'selection_setup_cost': setup,
        'routed_first_use_cost': setup+b['total_cost'], 'total_production_cost': state['prepare_cost']+b['total_cost'],
        'cost_reduction_percent': reduction if ready else None,
        'first_use_cost_reduction_percent': first_use_reduction if ready else None,
        'baseline_latency_ms': a['critical_path_latency_ms'], 'routed_latency_ms': b['critical_path_latency_ms'],
        'first_use_latency_ms': state['reference']['critical_path_latency_ms']+
            sum(r['node_result']['latency_ms'] for r in state['rows'])+b['critical_path_latency_ms'],
        'external_review_cost': None, 'external_review_time_ms': None,
        'decision': 'Simulation-only' if state['simulation'] else 'Insufficient-evidence',
        'routed_only_candidate_signal': quality_acceptable and reduction is not None and reduction>=20,
        'candidate_signal': quality_acceptable and first_use_reduction is not None and first_use_reduction>=20,
        '说明': '单轮仅提供描述性候选信号；评审费用和人工等待时间未知，不计作零。选路开销不得隐藏。',
        'final_reviews': reviews}


def fixture_reviews(public):
    result = template(public)
    result['reviewer'] = {'kind': 'fixture', 'id': 'offline-only'}
    for row in result['reviews']:
        row['scores'] = {k: (v if public['kind']!='node' else v*.9)
                         for k,v in (FINAL_LIMITS if public['kind']!='node' else NODE_LIMITS).items()}
        sample = next(s for s in public['samples'] if s['sample_id']==row['sample_id'])
        row['evidence_quote'] = sample['output'][:30]
        row['rationale'] = '仅验证管线的离线夹具，不是真实评分。'
        if 'task_checks' in row: row['task_checks'] = dict.fromkeys(row['task_checks'], True)
    return result
