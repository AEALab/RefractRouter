"""按独立样本隔离已结算的契约失败；基础设施异常停止整批，原始证据不修复。"""
from collections import Counter
from dataclasses import asdict
import hashlib
from itertools import permutations
import json
from pathlib import Path
import random
import statistics
import time

from .dag_study import implementation_fingerprint, study_methods, study_preflight
from .dag_study_execution import StudyDemoClient, direct_plan, write_json
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


OUTCOME_POLICY = 'all-trial-delivery-rate-and-joint-graded-metrics-v1'


def validate_batch_protocol(raw, manifest, base):
    if raw.get('outcome_policy') != OUTCOME_POLICY:
        raise ValueError('batch requires frozen outcome rules')
    tasks = {t['task_id']: t for t in raw['tasks']}
    source_protocol_path = base / raw['context_source_protocol_path']
    if hashlib.sha256(source_protocol_path.read_bytes()).hexdigest() != raw['context_source_protocol_sha256']:
        raise ValueError('frozen context protocol changed')
    source_tasks = {t['task_id']: t for t in json.loads(source_protocol_path.read_text())['tasks'] if t['split']=='calibration'}
    handoff = tasks.get(raw.get('handoff_task_id'))
    if handoff is None or handoff['split'] != 'calibration' or len(handoff['plan']['nodes']) != 3 or len(manifest.candidates) != 3:
        raise ValueError('batch requires six three-model calibration handoffs')
    expected = {(t['task_id'], rep) for t in raw['tasks'] if t['split'] == 'calibration'
                for rep in range(1, raw['calibration_repeats']+1)}
    seen = set()
    for row in raw.get('probe_contexts', []):
        key = (row['task_id'], row['repeat'])
        if key not in expected or key in seen:
            raise ValueError('unexpected or duplicate frozen context')
        seen.add(key)
        source = (base / row['source_path']).resolve()
        if (source_tasks.get(key[0], {}).get('task') != tasks[key[0]]['task'] or
                source.parent.name != f'{key[0]}--{key[1]}--calibration--strong'):
            raise ValueError('context must originate in the matching calibration task')
        if hashlib.sha256(source.read_bytes()).hexdigest() != row['source_sha256']:
            raise ValueError('frozen calibration source changed')
        archived = json.loads(source.read_text())
        plan = validate_plan(tasks[key[0]]['plan'], require_v2=True)
        context = {n['node_id']: decode_output(n['output'], plan.contracts[n['node_id']]) for n in archived['nodes']}
        if row['context'] != context:
            raise ValueError('frozen context differs from source fields')
        for node in plan.nodes:
            node_messages(tasks[key[0]]['task'], node, plan.contracts[node.node_id], context)
    if seen != expected:
        raise ValueError('incomplete frozen calibration contexts')
    if raw.get('calibration_source'):
        spec = raw['calibration_source']
        directory = calibration_source(raw)
        if hashlib.sha256((directory/'artifact-index.json').read_bytes()).hexdigest() != spec['index_sha256']:
            raise ValueError('calibration source index changed')
        index = json.loads((directory/'artifact-index.json').read_text())
        for name,digest in index.items():
            path = (directory/name).resolve()
            if not path.is_relative_to(directory) or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
                raise ValueError('calibration source artifact changed')
        prior = json.loads((directory/'protocol.json').read_text())
        if (prior['manifest_sha256'] != raw['manifest_sha256'] or prior['constraints'] != raw['constraints']
                or prior['calibration_repeats'] != raw['calibration_repeats']
                or [t for t in prior['tasks'] if t['split']=='calibration'] != [t for t in raw['tasks'] if t['split']=='calibration']):
            raise ValueError('calibration source does not match frozen tasks and constraints')
        source = json.loads((directory/'study-result.json').read_text())
        calibration = [r for r in source['runs'] if r['split']=='calibration']
        expected_runs = len(expected)*len(manifest.candidates)
        if len(calibration)!=expected_runs or any(r['status'] not in ('completed','failed') for r in calibration):
            raise ValueError('incomplete calibration source')
        prefixes = tuple(t['task_id']+'--' for t in raw['tasks'] if t['split']=='calibration')
        calls = [c for c in source['calls'] if c['label'].startswith('probe:') or
                 (c['label'].startswith(prefixes) and '--calibration--' in c['label'])]
        if any(c['status']!='billed' or c.get('input_tokens',0)<=0 or c.get('output_tokens',0)<=0
               or c.get('finish_reason')!='stop' for c in calls):
            raise ValueError('unconfirmed calibration usage cannot be reused')


def calibration_source(protocol):
    root = Path(__file__).resolve().parents[2]
    path = (root/protocol['calibration_source']['repository_path']).resolve()
    if not path.is_relative_to(root/'reports'):
        raise ValueError('calibration source must be a repository report')
    return path


def recoverable(exc, budget):
    """只有明确的结果/容量/截止失败可隔离；未知用量、I/O、认证、账本错误不能继续。"""
    _, calls = budget.snapshot()
    if any(c['status'] not in ('billed', 'cancelled-before-dispatch') for c in calls):
        return False
    if not isinstance(exc, ValueError):
        return False
    message = str(exc)
    return isinstance(exc, json.JSONDecodeError) or message.startswith((
        'node-output-contract-invalid', 'invalid judge', 'invalid final judge',
        'inconsistent final judge', 'invalid or truncated output',
        'node-input-budget-exceeded', 'judge-input-cap-exceeded',
        'task-deadline-exhausted', 'study-task-deadline-exhausted',
        'invalid judge score', 'invalid judge rationale', 'invalid criterion rationale',
        'study-no-feasible-route', 'study-no-feasible-calibrated-single-model'))


def compare_batch(runs, protocol, *, simulated):
    rows = [r for r in runs if r['split'] == 'test']
    methods = study_methods(protocol)
    expected = {(t['task_id'], rep, method) for t in protocol['tasks'] if t['split'] == 'test'
                for rep in range(1, protocol['test_repeats']+1) for method in methods}
    keys = [(r['task_id'], r['repeat'], r['method']) for r in rows]
    complete = (len(keys) == len(set(keys)) and set(keys) == expected
                and all(r['status'] != 'started' and r['cost_known'] for r in rows))
    groups = []
    for method in methods:
        group = [r for r in rows if r['method'] == method]
        groups.append({'method': method, 'planned': len(expected)//len(methods), 'recorded': len(group),
            'delivered': sum(r['delivered'] for r in group),
            'delivery_rate': sum(r['delivered'] for r in group)/len(group) if group else None,
            'outcomes': dict(Counter(r['status'] for r in group)),
            'graded': sum(r['score'] is not None for r in group),
            'total_deployment_cost': sum(r['deployment_cost'] for r in group)})
    pairs = [('dag-strong-parallel', 'dag-strong-serial'), ('dag-strong-serial', 'direct-strong'),
             ('dag-node-a', 'dag-calibrated-single'), ('dag-node-b', 'dag-calibrated-single'),
             ('dag-node-a', 'dag-strong-parallel'), ('dag-node-b', 'dag-strong-parallel'),
             ('dag-node-a', 'dag-single-a'), ('dag-node-b', 'dag-single-b')]
    comparison = []
    indexed = dict(zip(keys, rows))
    task_repeats = sorted({(key[0], key[1]) for key in expected})
    for candidate, baseline in pairs:
        matched, outcomes = [], []
        for tid, rep in task_repeats:
            a, b = indexed.get((tid, rep, candidate)), indexed.get((tid, rep, baseline))
            if a is None or b is None:
                continue
            outcomes.append({'task_id': tid, 'repeat': rep, 'candidate_delivered': a['delivered'],
                             'baseline_delivered': b['delivered']})
            if (a['score'] is not None and b['score'] is not None and
                    b['deployment_cost'] > 0 and b['wall_time_ms'] > 0):
                matched.append({'task_id': tid, 'repeat': rep, 'quality_delta': a['score']-b['score'],
                    'cost_saving': 1-a['deployment_cost']/b['deployment_cost'],
                    'latency_ratio': a['wall_time_ms']/b['wall_time_ms']})
        intervals = None
        if matched:
            by_task = {tid: [r for r in matched if r['task_id'] == tid] for tid in sorted({r['task_id'] for r in matched})}
            rng = random.Random(protocol['acceptance']['bootstrap_seed'])
            boot = []
            for _ in range(protocol['acceptance']['bootstrap_repeats']):
                sample = [r for tid in rng.choices(list(by_task), k=len(by_task)) for r in by_task[tid]]
                boot.append({k: statistics.mean(r[k] for r in sample) for k in ('quality_delta','cost_saving','latency_ratio')})
            intervals = {k: [sorted(r[k] for r in boot)[int(.025*len(boot))],
                             sorted(r[k] for r in boot)[min(len(boot)-1,int(.975*len(boot)))]] for k in boot[0]}
        limits = protocol['acceptance']
        all_delivered = complete and all(r['candidate_delivered'] and r['baseline_delivered'] for r in outcomes)
        signal = (all_delivered and len(matched) == len(task_repeats) and intervals is not None
                  and intervals['quality_delta'][0] >= -limits['maximum_mean_quality_loss']
                  and intervals['cost_saving'][0] >= limits['minimum_cost_saving_fraction']
                  and intervals['latency_ratio'][1] <= limits['maximum_latency_ratio'])
        comparison.append({'candidate': candidate, 'baseline': baseline, 'outcome_pairs': outcomes,
            'joint_graded_pairs': matched, 'conditional_interval_95': intervals,
            'exploratory_signal': None if simulated or not complete else bool(signal)})
    return {'status': 'simulated' if simulated else ('complete-with-outcomes' if complete else 'incomplete'),
            'complete': complete, 'groups': groups, 'comparisons': comparison,
            'limitations': ['失败不填质量零分；交付率分母为所有计划样本，仅完整运行时汇总。',
                '质量、成本、时延仅在共同已评分集合比较，存在非随机缺失偏差。',
                '完整采集不要求产生正收益；仅三个任务，不能泛化。']}


def run_batch_study(protocol, manifest, output_dir, *, simulated=True, client=None,
                    production_limit=None, evaluation_limit=None):
    preflight = study_preflight(protocol, manifest)
    if not simulated and (client is None or getattr(client, 'max_retries', None) != 0 or
            production_limit is None or evaluation_limit is None or
            production_limit < preflight['budget']['production'] or evaluation_limit < preflight['budget']['evaluation']):
        raise ValueError('batch requires zero retries and full admission envelope')
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=False)
    (out/'calls').mkdir()
    for name, data in [('protocol', protocol), ('preflight', preflight), ('manifest', asdict(manifest)),
                       ('implementation', implementation_fingerprint())]:
        write_json(out/(name+'.json'), data)
    limits = preflight['budget'] if simulated else {'production': production_limit, 'evaluation': evaluation_limit}
    summary = {'schema_version':'dag-batch-result-v1', 'status':'started', 'simulated':simulated,
               'runs':[], 'issues':[], 'calls':[], 'charged':{'production':0.,'evaluation':0.}, 'preflight':preflight}
    observations = {'schema_version':'node-observations-v1', 'kind':'synthetic' if simulated else 'empirical',
                    'expected_contexts':[], 'observations':[]}
    client = StudyDemoClient() if simulated else client
    candidates = {m.model_id:m for m in manifest.candidates}
    policy = ExecutionPolicy.from_request(protocol['execution_policy'])
    active = []
    def persist():
        write_json(out/'study-result.json', summary)
        write_json(out/'observations.json', observations)
    def new_budget():
        prior = list(summary['calls'])
        budget = TaskCallBudget(client, *(limits[c]-summary['charged'][c] for c in ('production','evaluation')),
                                max_calls=preflight['maximum_calls']-len(prior))
        def checkpoint():
            _, calls = budget.snapshot()
            summary['calls'] = prior + calls
            summary['charged'] = {c:sum(r['charged'] for r in summary['calls'] if r['category']==c)
                                  for c in ('production','evaluation')}
            persist()
        def request(res):
            write_json(out/'calls'/(hashlib.sha256(res.row['label'].encode()).hexdigest()+'-request.json'),
                       {'label':res.row['label'], 'model_id':res.model.model_id, 'messages':res.messages})
            checkpoint()
        def response(row, value):
            write_json(out/'calls'/(hashlib.sha256(row['label'].encode()).hexdigest()+'-response.json'),
                       {'label':row['label'], **asdict(value)})
        budget.on_reserve, budget.on_response = request, response
        active[:] = [budget, checkpoint]
        return budget, checkpoint

    def run_one(task, repeat, method, *, fixed=None, profiles=(), explicit=None, split=None):
        run_id = f"{task['task_id']}--{repeat}--{method}"+(f'--{fixed}' if fixed else '')
        folder = out/run_id
        folder.mkdir()
        budget, book = new_budget()
        plan = direct_plan(task) if method == 'direct-strong' else validate_plan(task['plan'], require_v2=True)
        current_policy = ExecutionPolicy(1, policy.provider_concurrency, policy.provider_min_interval_ms) if method in (
            'calibration', 'direct-strong', 'dag-strong-serial') else policy
        start = time.monotonic()
        deadline = start+protocol['constraints']['latencyMaxMs']/1000
        result = {'status':'started','nodes':[], 'assignments':{}, 'plan':plan.to_dict(), 'final_output':'','evaluation':None}
        row = {'task_id':task['task_id'], 'family':task['family'], 'split':split or task['split'],
               'repeat':repeat, 'method':method, 'fixed_model':fixed, 'result_path':folder.name+'/result.json'}
        summary['runs'].append(row)
        def checkpoint():
            _, result['calls'] = budget.snapshot()
            result['wall_time_ms'] = (time.monotonic()-start)*1000
            grade = result['evaluation'] if result['status']=='completed' else None
            row.update(status=result['status'], score=grade['score'] if grade else None,
                passed=grade['passed'] if grade else None,
                delivered=bool(grade and grade['passed'] and grade['score']>=protocol['acceptance']['minimum_final_quality']),
                production_cost=sum(c['charged'] for c in result['calls'] if c['category']=='production'),
                evaluation_cost=sum(c['charged'] for c in result['calls'] if c['category']=='evaluation'),
                cost_known=all(c['status'] in ('billed','cancelled-before-dispatch') for c in result['calls']),
                deployment_cost=sum(c['charged'] for c in result['calls']), wall_time_ms=result['wall_time_ms'])
            write_json(folder/'result.json', result)
            book()
        try:
            if explicit is not None:
                result['assignments'] = explicit
                result['assignment_origin'] = 'frozen-validation-permutations'
            elif fixed is not None:
                result['assignments'] = {n.node_id:fixed for n in plan.nodes}
            elif method == 'dag-calibrated-single':
                raise ValueError('study-no-feasible-calibrated-single-model')
            else:
                cap = protocol['constraints']
                eligible = {n.node_id:[mid for mid,m in candidates.items()
                    if plan.contracts[n.node_id]['capability']['input_budget_tokens']+min(m.max_output_tokens,8192)<=m.context_window]
                    for n in plan.nodes}
                result['routing'] = route_nodes(plan, profiles, method='A' if method.endswith('-a') else 'B',
                    quality_min=cap['qualityMin'], cost_max=cap['costMax'], latency_max_ms=cap['latencyMaxMs'],
                    weights=Weights(**cap['weights']) if method.endswith('-b') else None,
                    eligible_models=eligible, execution_policy=current_policy,
                    model_providers={mid:m.provider for mid,m in candidates.items()},
                    assignment_mode='single-model' if method.startswith('dag-single-') else 'per-node')
                if result['routing']['status'] != 'selected':
                    raise ValueError('study-no-feasible-route')
                result['assignments'] = result['routing']['assignments']
            result['final_output'] = execute_nodes(plan, task['task'], result['assignments'], candidates,
                budget, current_policy, result, checkpoint, started=start, deadline=deadline, label_prefix=run_id+':')
            result['evaluation'] = evaluate_text(budget, manifest.judge, task['task'], result['final_output'],
                criteria=plan.acceptance_criteria, label=run_id+':final-judge', deadline=deadline,
                input_cap=protocol['input_caps']['final_judge'])
            result['status'] = 'completed'
        except Exception as exc:
            result['status'] = 'no-feasible-route' if str(exc).startswith('study-no-feasible') else 'failed'
            result['issue'] = str(exc)[:500] if isinstance(exc, ValueError) else type(exc).__name__
            if not recoverable(exc, budget):
                raise
        finally:
            budget.stop()
            checkpoint()
        return result

    try:
        handoff = next(t for t in protocol['tasks'] if t['task_id']==protocol['handoff_task_id'])
        order = validate_plan(handoff['plan']).order()
        for rep, mids in enumerate(permutations(candidates), 1):
            run_one(handoff, rep, 'handoff', explicit=dict(zip(order,mids)), split='handoff')
        calibration_tasks = [] if protocol.get('calibration_source') else [t for t in protocol['tasks'] if t['split']=='calibration']
        if protocol.get('calibration_source'):
            source = calibration_source(protocol)
            observations = json.loads((source/'observations.json').read_text())
            summary['calibration_source'] = protocol['calibration_source']
            calibration_rows = [r for r in json.loads((source/'study-result.json').read_text())['runs'] if r['split']=='calibration']
            write_json(out/'calibration-source-runs.json',calibration_rows)
        for task in calibration_tasks:
            for rep in range(1,protocol['calibration_repeats']+1):
                for mid in candidates:
                    run_one(task, rep, 'calibration', fixed=mid)
                context = next(r['context'] for r in protocol['probe_contexts'] if (r['task_id'],r['repeat'])==(task['task_id'],rep))
                plan = validate_plan(task['plan'], require_v2=True)
                for node in plan.nodes:
                    contract = plan.contracts[node.node_id]
                    messages = node_messages(task['task'], node, contract, context)
                    input_text = json.dumps(messages,ensure_ascii=False)
                    ih = hashlib.sha256(input_text.encode()).hexdigest()
                    subject = {'task_id':task['task_id'], 'repeat':rep, 'node_id':node.node_id}
                    observations['expected_contexts'].append(subject)
                    for mid, model in candidates.items():
                        budget, book = new_budget()
                        label = f"probe:{task['task_id']}:{rep}:{node.node_id}:{mid}"
                        deadline = time.monotonic()+protocol['constraints']['latencyMaxMs']/1000
                        # 已结算的空白/截断输出同样作为确定性拒绝；未知用量仍停止整批。
                        try:
                            response = budget.complete(model,messages,label=label,json_mode=contract['output']['format']=='json',
                                                       timeout_seconds=deadline-time.monotonic())
                        except ValueError as exc:
                            if not recoverable(exc,budget) or not str(exc).startswith('invalid or truncated output'):
                                raise
                            archived = json.loads((out/'calls'/(hashlib.sha256(label.encode()).hexdigest()+'-response.json')).read_text())
                            response = ChatResponse(**{k:v for k,v in archived.items() if k!='label'})
                        oh = hashlib.sha256(response.content.encode()).hexdigest()
                        obs = {**subject, 'model_id':mid,'input':input_text,'output':response.content,
                            'input_sha256':ih,'output_sha256':oh,
                            'status':'completed' if response.finish_reason=='stop' and response.content.strip() else 'invalid-output',
                            'finish_reason':response.finish_reason,
                            'features':{'node_type':node.node_type, **{k:contract['capability'][k] for k in ('difficulty','risk','input_budget_tokens')}},
                            'output_contract':contract['output'],'latency_ms':response.latency_ms,
                            'usage':{k:getattr(response,k) for k in ('input_tokens','output_tokens','cached_input_tokens','reasoning_tokens')}}
                        observations['observations'].append(obs)
                        book()
                        try:
                            if obs['status'] != 'completed':
                                raise ValueError('unavailable probe output')
                            decode_output(response.content,contract)
                        except ValueError:
                            obs['evaluation'] = {'method':'deterministic-rejection','status':'rejected','score':0,
                                'passed':False,'input_sha256':ih,'output_sha256':oh}
                        else:
                            try:
                                judged = evaluate_text(budget,manifest.judge,task['task'],response.content,
                                    criteria=contract['checks'],node_input=json.loads(input_text),label=label+':judge',
                                    deadline=deadline,input_cap=protocol['input_caps']['node_judge'])
                                obs['evaluation'] = {**judged,'method':'independent-text-node-v1','status':'completed',
                                                     'input_sha256':ih,'output_sha256':oh}
                            except Exception as exc:
                                if not recoverable(exc,budget):
                                    raise
                                obs['evaluation'] = {'method':'unavailable-independent-evaluation','status':'unavailable',
                                    'score':None,'input_sha256':ih,'output_sha256':oh,'issue':str(exc)[:500]}
                        book()
        profile = build_stratified_profile(observations,manifest,
            calibration_task_ids=[t['task_id'] for t in protocol['tasks'] if t['split']=='calibration'],
            test_task_ids=[t['task_id'] for t in protocol['tasks'] if t['split']=='test'],allow_unavailable_evaluation=True)
        if protocol.get('calibration_source'):
            original = json.loads((calibration_source(protocol)/'profile.json').read_text())
            if profile['candidates'] != original['candidates'] or profile['exclusions'] != original['exclusions']:
                raise ValueError('reused calibration changed model profiles')
        write_json(out/'profile.json',profile)
        profiles = load_profile(profile,manifest) if profile['candidates'] else ()
        frozen, quality_reference = {}, {}
        if not protocol.get('calibration_source'):
            calibration_rows = [r for r in summary['runs'] if r['split']=='calibration']
        for family in sorted({t['family'] for t in protocol['tasks']}):
            groups = {mid:[r for r in calibration_rows if r['family']==family and r['fixed_model']==mid]
                      for mid in candidates}
            # 质量基准只用完整已评分模型，避免用幸存评分掩盖失败。
            graded = [mid for mid,rows in groups.items() if rows and all(r['score'] is not None for r in rows)]
            rank = lambda mid:(-statistics.mean(r['score'] for r in groups[mid]),statistics.mean(r['deployment_cost'] for r in groups[mid]),mid)
            quality_reference[family] = min(graded,key=rank) if graded else None
            eligible = [mid for mid in graded if all(r['delivered'] for r in groups[mid])]
            frozen[family] = min(eligible,key=rank) if eligible else None
        summary['calibrated_single_models'],summary['quality_baseline_models'] = frozen,quality_reference
        summary['calibration_and_handoff_cost'] = dict(summary['charged'])
        write_json(out/'calibrated-single-models.json',frozen)
        for task in (t for t in protocol['tasks'] if t['split']=='test'):
            for rep in range(1,protocol['test_repeats']+1):
                methods = list(study_methods(protocol))
                random.Random(f"{protocol['method_order_seed']}:{task['task_id']}:{rep}").shuffle(methods)
                for method in methods:
                    fixed = protocol['reference_model_id'] if method in ('direct-strong','dag-strong-serial','dag-strong-parallel') else (
                        frozen[task['family']] if method=='dag-calibrated-single' else None)
                    run_one(task,rep,method,fixed=fixed,profiles=profiles)
        summary['status'] = 'simulated' if simulated else 'completed'
    except Exception as exc:
        if active:
            active[0].stop()
            active[1]()
        summary['status'] = 'failed'
        summary['issues'] = [str(exc)[:500] if isinstance(exc,ValueError) else type(exc).__name__]
    finally:
        summary['comparison'] = compare_batch(summary['runs'],protocol,simulated=simulated)
        persist()
        write_json(out/'artifact-index.json',{str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted(out.rglob('*')) if p.is_file() and p.name!='artifact-index.json'})
    return summary
