"""固定计划的校准、节点探测和六组对照；统一预算，首个异常后停止。"""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import random
import statistics
import time

from .dag_study import study_methods, study_preflight
from .model_selection import Weights
from .node_routing import load_profile, route_nodes
from .openai_compatible import ChatResponse
from .profile_calibration import build_stratified_profile
from .task_budget import TaskCallBudget
from .task_contracts import decode_output
from .task_evaluation import evaluate_text
from .task_execution import execute_nodes, node_messages
from .task_plan import validate_plan
from .task_scheduling import ExecutionPolicy


def write_json(path, value):
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    temp.replace(path)


class StudyDemoClient:
    max_retries = 0

    def complete(self, model, messages, *, json_mode=False):
        payload = json.loads(messages[-1]['content'])
        if model.role == 'judge':
            content = json.dumps({'score': 90, 'passed': True, 'rationale': '[SIMULATED] 模拟评审',
                'criteria': [{'criterion': c, 'passed': True, 'rationale': '[SIMULATED] 模拟通过'} for c in payload['criteria']]})
        elif json_mode:
            content = json.dumps({key: '[SIMULATED] ' + key for key in payload['contract']['output']['fields']})
        else:
            content = '[SIMULATED] 文本产物'
        # 只用于流程验证；不会作为实测 profile 发布。
        return ChatResponse(content, 100, 80, 0, 0, 10, 1, 'stop', None)


def direct_plan(task):
    raw = deepcopy(task['plan'])
    final = next(n for n in raw['nodes'] if n['node_id'] == raw['final_node_id'])
    final['parents'], final['contract']['inputs'] = [], {}
    final['prompt_template'] = '直接完成原始任务，给出完整文本答案、证据与假设。'
    final['contract']['objective'] = '一次模型调用完成原始任务'
    final['contract']['covers'] = list(range(len(raw['acceptance_criteria'])))
    final['contract']['capability']['input_budget_tokens'] = max(n['contract']['capability']['input_budget_tokens'] for n in raw['nodes'])
    raw['nodes'] = [final]
    raw['decomposition_reason'] = '整任务单次调用对照，不使用模型规划。'
    return validate_plan(raw, require_v2=True)


def compare_runs(runs, protocol, *, simulated):
    test_runs = [r for r in runs if r['split'] == 'test']
    groups = {(r['task_id'], r['repeat'], r['method']): r for r in test_runs}
    keys = [(t['task_id'], repeat) for t in protocol['tasks'] if t['split'] == 'test'
            for repeat in range(1, protocol['test_repeats']+1)]
    comparisons = []
    pairs = [('dag-strong-parallel', 'dag-strong-serial'), ('dag-strong-serial', 'direct-strong'),
             ('dag-node-a', 'dag-calibrated-single'), ('dag-node-b', 'dag-calibrated-single'),
             ('dag-node-a', 'dag-strong-parallel'), ('dag-node-b', 'dag-strong-parallel')]
    if protocol['schema_version'] == 'dag-routing-study-v2':
        pairs += [('dag-node-a', 'dag-single-a'), ('dag-node-b', 'dag-single-b')]
    for candidate, baseline in pairs:
        rows = []
        for tid, repeat in keys:
            a, b = groups.get((tid, repeat, candidate)), groups.get((tid, repeat, baseline))
            if a is None or b is None:
                return {'status': 'insufficient-evidence', 'reason': 'missing paired runs'}
            if b['deployment_cost'] <= 0 or b['wall_time_ms'] <= 0:
                return {'status': 'insufficient-evidence', 'reason': 'invalid baseline denominator'}
            rows.append({'task_id': tid, 'repeat': repeat,
                'quality_delta': a['score']-b['score'], 'cost_saving': 1-a['deployment_cost']/b['deployment_cost'],
                'latency_ratio': a['wall_time_ms']/max(b['wall_time_ms'], .000001)})
        def means(values):
            return {k: statistics.mean(r[k] for r in values) for k in ('quality_delta', 'cost_saving', 'latency_ratio')}
        by_task = {tid: [r for r in rows if r['task_id'] == tid] for tid in sorted({r['task_id'] for r in rows})}
        rng = random.Random(protocol['acceptance']['bootstrap_seed'])
        boot = [means([row for tid in rng.choices(list(by_task), k=len(by_task)) for row in by_task[tid]])
                for _ in range(protocol['acceptance']['bootstrap_repeats'])]
        intervals = {k: [sorted(v[k] for v in boot)[int(.025*len(boot))],
                         sorted(v[k] for v in boot)[min(len(boot)-1, int(.975*len(boot)))]] for k in means(rows)}
        limits = protocol['acceptance']
        signal = (intervals['quality_delta'][0] >= -limits['maximum_mean_quality_loss']
                  and intervals['cost_saving'][0] >= limits['minimum_cost_saving_fraction']
                  and intervals['latency_ratio'][1] <= limits['maximum_latency_ratio']
                  and all(r['score'] >= limits['minimum_final_quality'] and r['passed'] for r in test_runs
                          if r['method'] in (candidate, baseline)))
        comparisons.append({'candidate': candidate, 'baseline': baseline, 'pairs': rows,
                            'mean': means(rows), 'task_cluster_bootstrap_interval_95': intervals,
                            'exploratory_signal': None if simulated else signal})
    return {'status': 'simulated' if simulated else 'complete-exploratory-comparison', 'comparisons': comparisons,
            'limitations': ['固定人工 DAG；不验证自动规划质量。', '只有 3 个测试任务，区间是探索性描述，不构成泛化证明。',
                           'deployment_cost 包含节点调用及运行时必需的最终评审，校准/探测费用另列。']}


def run_study(protocol, manifest, output_dir, *, simulated=True, client=None, production_limit=None, evaluation_limit=None):
    if protocol['schema_version'] == 'dag-routing-study-v3':
        from .dag_batch_study import run_batch_study
        return run_batch_study(protocol, manifest, output_dir, simulated=simulated, client=client,
                               production_limit=production_limit, evaluation_limit=evaluation_limit)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=False)
    preflight = study_preflight(protocol, manifest)
    write_json(out/'protocol.json', protocol)
    write_json(out/'preflight.json', preflight)
    write_json(out/'manifest.json', asdict(manifest))
    write_json(out/'implementation.json', {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(Path(__file__).parent.glob('*.py'))})
    if not simulated:
        if client is None or getattr(client, 'max_retries', None) != 0:
            raise ValueError('study requires an explicit zero-retry client')
        if production_limit is None or evaluation_limit is None or production_limit < preflight['budget']['production'] or evaluation_limit < preflight['budget']['evaluation']:
            raise ValueError('study budgets are below the frozen admission envelope')
    budget = TaskCallBudget(StudyDemoClient() if simulated else client,
        1e12 if simulated else production_limit, 1e12 if simulated else evaluation_limit,
        max_calls=preflight['maximum_calls'])
    candidates = {m.model_id: m for m in manifest.candidates}
    policy = ExecutionPolicy.from_request(protocol['execution_policy'])
    summary = {'schema_version': 'dag-study-result-v1', 'status': 'started', 'simulated': simulated,
               'runs': [], 'issues': [], 'preflight': preflight}
    observations = {'schema_version': 'node-observations-v1', 'kind': 'synthetic' if simulated else 'empirical',
                    'expected_contexts': [], 'observations': []}
    def persist():
        summary['charged'], summary['calls'] = budget.snapshot()
        write_json(out/'study-result.json', summary)
        write_json(out/'observations.json', observations)

    def run_one(task, repeat, method, *, fixed_model=None, profiles=None):
        run_id = f"{task['task_id']}--{repeat}--{method}" + (f'--{fixed_model}' if fixed_model else '')
        folder = out/run_id
        folder.mkdir()
        start = time.monotonic()
        deadline = start + protocol['constraints']['latencyMaxMs']/1000
        plan = direct_plan(task) if method == 'direct-strong' else validate_plan(task['plan'], require_v2=True)
        current_policy = (ExecutionPolicy(1, policy.provider_concurrency, policy.provider_min_interval_ms)
                          if method in ('calibration', 'direct-strong', 'dag-strong-serial') else policy)
        result = {'nodes': [], 'plan': plan.to_dict(), 'final_output': '', 'evaluation': None}
        first = len(budget.records)
        def checkpoint():
            _, rows = budget.snapshot()
            result['calls'] = rows[first:]
            result['wall_time_ms'] = (time.monotonic()-start)*1000
            write_json(folder/'result.json', result)
            persist()
        try:
            if fixed_model is not None:
                assignments = {n.node_id: fixed_model for n in plan.nodes}
            else:
                cap = protocol['constraints']
                eligible = {n.node_id: [mid for mid, model in candidates.items()
                    if n.node_id in plan.contracts and
                       plan.contracts[n.node_id]['capability']['input_budget_tokens'] + min(model.max_output_tokens, 8192) <= model.context_window]
                    for n in plan.nodes}
                routing = route_nodes(plan, profiles, method='A' if method in ('dag-node-a', 'dag-single-a') else 'B',
                    quality_min=cap['qualityMin'], cost_max=cap['costMax'], latency_max_ms=cap['latencyMaxMs'],
                    weights=Weights(**cap['weights']) if method in ('dag-node-b', 'dag-single-b') else None,
                    eligible_models=eligible, execution_policy=current_policy,
                    model_providers={mid: model.provider for mid, model in candidates.items()},
                    assignment_mode='single-model' if method.startswith('dag-single-') else 'per-node')
                result['routing'] = routing
                if routing['status'] != 'selected':
                    checkpoint()
                    raise ValueError('study-no-feasible-route')
                assignments = routing['assignments']
            result['assignments'] = assignments
            result['final_output'] = execute_nodes(plan, task['task'], assignments, candidates, budget, current_policy,
                result, checkpoint, started=start, deadline=deadline, label_prefix=run_id+':')
            result['evaluation'] = evaluate_text(budget, manifest.judge, task['task'], result['final_output'],
                criteria=plan.acceptance_criteria, label=run_id+':final-judge', deadline=deadline,
                input_cap=protocol['input_caps']['final_judge'])
            if time.monotonic() > deadline:
                raise ValueError('study-task-deadline-exhausted')
            result['status'] = 'completed'
            checkpoint()
        except Exception:
            result['status'] = 'failed'
            raise
        finally:
            checkpoint()
        production = sum(r['charged'] for r in result['calls'] if r['category'] == 'production')
        evaluation = sum(r['charged'] for r in result['calls'] if r['category'] == 'evaluation')
        summary['runs'].append({'task_id': task['task_id'], 'family': task['family'], 'split': task['split'],
            'repeat': repeat, 'method': method, 'fixed_model': fixed_model, 'score': result['evaluation']['score'],
            'passed': result['evaluation']['passed'], 'production_cost': production, 'evaluation_cost': evaluation,
            'deployment_cost': production+evaluation, 'wall_time_ms': result['wall_time_ms'], 'result_path': folder.name+'/result.json'})
        persist()
        return result

    call_folder = out/'calls'
    call_folder.mkdir()
    def call_path(label, suffix):
        return call_folder/(hashlib.sha256(label.encode()).hexdigest() + suffix)
    def archive_request(reservation):
        write_json(call_path(reservation.row['label'], '-request.json'),
                   {'label': reservation.row['label'], 'model_id': reservation.model.model_id, 'messages': reservation.messages})
        persist()
    def archive_response(row, response):
        write_json(call_path(row['label'], '-response.json'), {'label': row['label'], **asdict(response)})
    budget.on_reserve, budget.on_response = archive_request, archive_response
    try:
        for task in (t for t in protocol['tasks'] if t['split'] == 'calibration'):
            for repeat in range(1, protocol['calibration_repeats']+1):
                reference = None
                for mid in candidates:
                    result = run_one(task, repeat, 'calibration', fixed_model=mid)
                    if mid == protocol['reference_model_id']:
                        reference = result
                plan = validate_plan(task['plan'], require_v2=True)
                context = {row['node_id']: decode_output(row['output'], plan.contracts[row['node_id']]) for row in reference['nodes']}
                for node in plan.nodes:
                    contract = plan.contracts[node.node_id]
                    messages = node_messages(task['task'], node, contract, context)
                    input_text = json.dumps(messages, ensure_ascii=False)
                    ih = hashlib.sha256(input_text.encode()).hexdigest()
                    subject = {'task_id': task['task_id'], 'repeat': repeat, 'node_id': node.node_id}
                    observations['expected_contexts'].append(subject)
                    for mid, model in candidates.items():
                        label = f"probe:{task['task_id']}:{repeat}:{node.node_id}:{mid}"
                        deadline = time.monotonic()+protocol['constraints']['latencyMaxMs']/1000
                        response = budget.complete(model, messages, label=label,
                            json_mode=contract['output']['format']=='json', timeout_seconds=deadline-time.monotonic())
                        oh = hashlib.sha256(response.content.encode()).hexdigest()
                        row = {**subject, 'model_id': mid, 'input': input_text, 'output': response.content,
                            'input_sha256': ih, 'output_sha256': oh, 'status': 'completed', 'finish_reason': response.finish_reason,
                            'features': {'node_type': node.node_type, **{k: contract['capability'][k] for k in ('difficulty', 'risk', 'input_budget_tokens')}},
                            'output_contract': contract['output'], 'latency_ms': response.latency_ms,
                            'usage': {k: getattr(response, k) for k in ('input_tokens', 'output_tokens', 'cached_input_tokens', 'reasoning_tokens')}}
                        observations['observations'].append(row)
                        persist()  # 先保存付费探测原文，后续校验/评审失败也可追溯。
                        decode_output(response.content, contract)
                        judged = evaluate_text(budget, manifest.judge, task['task'], response.content,
                            criteria=contract['checks'], node_input=json.loads(input_text), label=label+':judge',
                            deadline=deadline, input_cap=protocol['input_caps']['node_judge'])
                        row['evaluation'] = {**judged, 'method': 'independent-text-node-v1', 'status': 'completed',
                                             'input_sha256': ih, 'output_sha256': oh}
                        persist()
        profile = build_stratified_profile(observations, manifest,
            calibration_task_ids=[t['task_id'] for t in protocol['tasks'] if t['split']=='calibration'],
            test_task_ids=[t['task_id'] for t in protocol['tasks'] if t['split']=='test'])
        write_json(out/'profile.json', profile)
        profiles = load_profile(profile, manifest)
        frozen_models, quality_baselines = {}, {}
        for family in sorted({t['family'] for t in protocol['tasks']}):
            def rank(mid):
                rows = [r for r in summary['runs'] if r['family']==family and r['fixed_model']==mid]
                return (-statistics.mean(r['score'] for r in rows), statistics.mean(r['deployment_cost'] for r in rows), mid)
            quality_baselines[family] = min(candidates, key=rank)
            eligible = [mid for mid in candidates if all(r['passed'] for r in summary['runs'] if r['family']==family and r['fixed_model']==mid)
                        and -rank(mid)[0] >= protocol['constraints']['qualityMin']]
            if not eligible:
                raise ValueError('study-no-feasible-calibrated-single-model')
            frozen_models[family] = min(eligible, key=rank)
        summary['calibrated_single_models'] = frozen_models
        summary['quality_baseline_models'] = quality_baselines
        summary['calibration_cost'], _ = budget.snapshot()
        write_json(out/'calibrated-single-models.json', frozen_models)
        for task in (t for t in protocol['tasks'] if t['split']=='test'):
            for repeat in range(1, protocol['test_repeats']+1):
                methods = list(study_methods(protocol))
                if protocol['schema_version'] == 'dag-routing-study-v2':
                    random.Random(f"{protocol['method_order_seed']}:{task['task_id']}:{repeat}").shuffle(methods)
                for method in methods:
                    mid = protocol['reference_model_id'] if method in ('direct-strong', 'dag-strong-serial', 'dag-strong-parallel') else (
                        frozen_models[task['family']] if method=='dag-calibrated-single' else None)
                    run_one(task, repeat, method, fixed_model=mid, profiles=profiles)
        summary['comparison'] = compare_runs(summary['runs'], protocol, simulated=simulated)
        summary['status'] = 'simulated' if simulated else 'completed'
    except Exception as exc:
        budget.stop()
        summary['status'] = 'failed'
        summary['issues'] = [str(exc)[:500] if isinstance(exc, ValueError) else type(exc).__name__]
    finally:
        persist()
        write_json(out/'artifact-index.json', {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(out.rglob('*')) if p.is_file() and p.name!='artifact-index.json'})
    return summary
