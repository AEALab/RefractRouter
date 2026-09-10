"""#39/#40 共用校准与对照的冻结批次；费用和失败分母始终保留。"""
from collections import Counter, defaultdict
from dataclasses import asdict
from difflib import SequenceMatcher
import math
import json
import random
import statistics
import time

from .dag_study import implementation_fingerprint
from .node_routing import load_profile
from .profile_calibration import build_stratified_profile, INPUT_BANDS
from .research_analysis import compare_research
from .research_calibration import freeze_direct_models
from .research_execution import ResearchSession, delivery_task
from .research_protocol import digest, material_digest, FIXED_ARMS
from .responses_api import output_token_limit
from .task_execution import node_messages
from .task_plan import validate_plan

AUTO_ARMS = ('auto-cold-a','auto-cold-b','auto-reuse-a','auto-reuse-b')
ARMS = (*FIXED_ARMS, *AUTO_ARMS)


def historical_materials(root, current_path=None):
    """历史冻结任务仅作排除索引，不重写历史文件。"""
    found = {}
    for directory in ('data/benchmarks', 'data/research'):
        for path in sorted((root/directory).rglob('*.json')):
            if current_path is not None and path.resolve() == current_path.resolve():
                continue
            raw = json.loads(path.read_text())
            for task in raw.get('tasks', []) if isinstance(raw, dict) else []:
                if isinstance(task, dict) and isinstance(task.get('task'), str):
                    found[material_digest(task['task'])] = str(path.relative_to(root))
    return found


def preflight(protocol, manifest, *, excluded_materials=()):
    if protocol['schema_version'] != 'joint-research-v1' or protocol['implementation_sha256'] != implementation_fingerprint():
        raise ValueError('joint protocol implementation changed')
    if protocol['manifest_sha256'] != digest(asdict(manifest)):
        raise ValueError('manifest changed')
    if protocol['repeats'] != 1 or protocol['max_node_fallbacks'] or protocol['planner_repairs']:
        raise ValueError('unsupported repetition or recovery protocol')
    ids, sources, hashes = set(), set(), set()
    counts, coverage = Counter(), []
    for task in protocol['tasks']:
        if task['task_id'] in ids or task['source_id'] in sources:
            raise ValueError('duplicate task/source')
        ids.add(task['task_id']); sources.add(task['source_id'])
        h = material_digest(task['task'])
        if h != task['material_sha256'] or h in hashes or h in excluded_materials:
            raise ValueError('changed, repeated or historical material')
        hashes.add(h)
        counts[task['split'],task['cell']] += 1
        if task['split'] not in ('calibration','test') or task['cell'] not in protocol['coverage_cells']:
            raise ValueError('invalid split/cell')
        plan = validate_plan(task['plan'], required_criteria=task['criteria'], require_v2=True)
        actual = {}
        for n in plan.nodes:
            messages = node_messages(delivery_task(task), n, plan.contracts[n.node_id], task['reference_context'])
            actual[n.node_id] = len(json.dumps(messages,ensure_ascii=False).encode())
        if len(task['task'].encode()) < task['minimum_material_bytes']:
            raise ValueError('declared input size lacks actual material')
        coverage.append({'task_id':task['task_id'],'cell':task['cell'],'split':task['split'],
            'challenge':task['challenge'],'material_bytes':len(task['task'].encode()),'node_input_bytes':actual})
    for cell in protocol['coverage_cells']:
        if counts['calibration',cell] != 3 or counts['test',cell] != 4:
            raise ValueError('requires 3 calibration and 4 test tasks per cell')
    tests = [t for t in protocol['tasks'] if t['split']=='test']
    if set(t['challenge'] for t in tests) != {'short','oversplit','coupled','parallel','serial','bottleneck','handoff'}:
        raise ValueError('planning challenges missing')
    required = math.ceil((2.242*protocol['acceptance']['assumed_task_delta_sd']/protocol['acceptance']['target_mean_half_width'])**2)
    if len(tests) < required:
        raise ValueError('sample size below planning assumption')
    caps = []
    production = evaluation = 0.
    calls = Counter()
    def cost(model, cap):
        output = output_token_limit(model)
        if cap + output > model.context_window:
            raise ValueError('context envelope exceeded')
        return (cap*model.input_cost_per_1k + output*model.output_cost_per_1k)/1000
    models = list(manifest.candidates)
    planner = next(m for m in models if m.model_id==protocol['planner_model'])
    judge = cost(manifest.judge,protocol['judge_input_cap'])
    plan_cost = cost(planner,protocol['planner_input_cap'])
    evaluation += len(protocol['coverage_cells'])*judge
    calls['independent_material_review'] += len(protocol['coverage_cells'])
    runs = []
    for task in protocol['tasks']:
        caps = [n['contract']['capability']['input_budget_tokens'] for n in task['plan']['nodes']]
        if task['split']=='calibration':
            production += sum(2*sum(cost(m,c) for c in caps)+cost(m,max(caps)) for m in models)
            production += sum(max(cost(m,c) for m in models) for c in caps)
            judges = (len(caps)+2)*len(models)+1
            calls['calibration_production'] += (2*len(caps)+1)*len(models)+len(caps)
            calls['calibration_evaluation'] += judges
            evaluation += judges*judge
        else:
            production += 2*plan_cost; evaluation += 2*judge
            calls['cached_planning'] += 2; calls['cached_review'] += 2
            for arm in ARMS:
                ncaps = [protocol['auto_node_input_cap']]*8 if arm.startswith('auto-') else [max(caps)] if arm.startswith('direct-') else caps
                cold = arm.startswith('auto-cold')
                production += sum(max(cost(m,c) for m in models) for c in ncaps) + cold*plan_cost
                evaluation += (1+int(cold))*judge
                calls['test_production'] += len(ncaps)+int(cold)
                calls['test_evaluation'] += 1+int(cold)
                runs.append({'task_id':task['task_id'],'cell':task['cell'],'repeat':1,'arm':arm})
    overlaps = [{'left':a['task_id'],'right':b['task_id'], 'ratio':SequenceMatcher(None,a['task'],b['task']).ratio()}
        for i,a in enumerate(protocol['tasks']) for b in protocol['tasks'][i+1:]]
    return {'protocol_sha256':digest(protocol),'real_model_calls':0,'maximum_calls':sum(calls.values()),
        'budget':{'production':math.ceil(production*10000)/10000,'evaluation':math.ceil(evaluation*10000)/10000},
        'calls_by_phase':dict(calls),'runs':runs,'coverage':coverage,'required_under_assumed_sd':required,
        'largest_text_overlaps':sorted(overlaps,key=lambda r:-r['ratio'])[:10],
        'historical_materials_checked':len(excluded_materials),
        'scope':protocol['scope'],'precision_limit':'正态样本量规划依赖标准差假设；案例是目的性选择，区间只描述这些条件，分层与尾时延不作精确推断。'}


def summarize(session, protocol, preview):
    rows = [r for r in session.result['runs'] if r.get('split')=='test']
    setup = sum(sum(r['costs'].values()) for r in session.result['runs'] if r.get('split')=='calibration')
    setup += sum(sum(r['costs'].values()) for r in session.result.get('probe_runs',[]))
    setup += sum(sum(r['costs'].values()) for r in session.result['plan_setups'])
    setup += sum(c['charged'] for c in session.result['calls'] if c['label'].startswith('material-review:'))
    comparisons = {}
    for issue, arms, pairs in ((39, FIXED_ARMS,[['dag-node-a','dag-single-a'],['dag-node-b','dag-single-b']]),
            (40, ('dag-node-a','dag-node-b',*AUTO_ARMS,'direct-a','direct-b'),
                [['auto-cold-a','direct-a'],['auto-cold-b','direct-b']])):
        p = {**protocol,'arms':list(arms),'acceptance':{**protocol['acceptance'],'primary_pairs':pairs}}
        comparisons[str(issue)] = compare_research({'runs':[r for r in preview['runs'] if r['arm'] in arms]},p,
            [r for r in rows if r['arm'] in arms],simulated=session.result['simulated'],setup_cost=setup)
    expenses = defaultdict(float)
    auxiliary_pairs = [['auto-cold-a','dag-node-a'],['auto-cold-b','dag-node-b'],
        ['auto-reuse-a','auto-cold-a'],['auto-reuse-b','auto-cold-b'],
        ['dag-strong-parallel','dag-strong-serial']]
    auxiliary_protocol = {**protocol,'arms':list(ARMS),'acceptance':{
        'primary_pairs':auxiliary_pairs,'bootstrap_repeats':protocol['acceptance']['bootstrap_repeats'],
        'bootstrap_seed':protocol['acceptance']['bootstrap_seed']}}
    auxiliary = compare_research(preview,auxiliary_protocol,rows,
        simulated=session.result['simulated'],setup_cost=setup)
    for c in session.result['calls']:
        label = c['label']
        bucket = ('material_review' if label.startswith('material-review:') else 'node_calibration' if label.startswith('probe:') else 'cache_planning_setup' if label.startswith('setup:') else
            'handoff_validation' if label.startswith('handoff-') else 'baseline_calibration' if label.startswith('cal-') else
            'runtime_planning' if label.endswith(':planner') else 'runtime_execution')
        if c['category']=='evaluation': bucket += '_evaluation'
        expenses[bucket] += c['charged']
    return {'issues':comparisons,'auxiliary_descriptive_comparisons':auxiliary,
        'auxiliary_limit':'辅助比较仅作描述，其区间未按五项比较调整，不用于确认性收益判定。',
        'cost_phases':dict(expenses),'dsh_outer_cost':0,
        'runtime_review_policy':'计划语义检查与最终评审均为冻结运行协议的必要步骤，计入实际墙钟和运行费；校准/交接检查另列。',
        'setup_accounting':'两项分析共享同一批设置成本，不能把两份报告中的 first_use_cost 相加。所有失败与实验评审仍在总账中。',
        'human_review_complete':False,'independent_task_scope':protocol['scope']}


def run(protocol, manifest, output_dir, client, *, simulated=False, excluded_materials=()):
    preview = preflight(protocol,manifest,excluded_materials=excluded_materials)
    session = ResearchSession(manifest,protocol,output_dir,client,
        production_limit=preview['budget']['production'],evaluation_limit=preview['budget']['evaluation'],
        max_calls=preview['maximum_calls'],simulated=simulated)
    session.result['preflight'],session.result['planned_runs'] = preview,preview['runs']
    calibration = [t for t in protocol['tasks'] if t['split']=='calibration']
    tests = [t for t in protocol['tasks'] if t['split']=='test']
    def trial(task, arm, run_id, split, **kwargs):
        try:
            session.run_trial(task,run_id,**kwargs)
        finally:
            if session.result['runs'] and session.result['runs'][-1]['run_id']==run_id:
                session.result['runs'][-1].update(arm=arm,split=split,repeat=1)
                session.persist()
        return session.result['runs'][-1]
    try:
        session.result['material_reviews'] = {}
        for cell in protocol['coverage_cells']:
            material = [{k:t[k] for k in ('task_id','split','challenge','task','evaluation_reference')}
                for t in protocol['tasks'] if t['cell']==cell]
            review = session._judge('审查下列研究材料是否可以用于声明范围内的独立校准和测试。这里独立指不同问题与来源包，不是表格行，也不要求真实机构数据。'
                '材料均为自编虚构案例，只能支持封闭案例内的结论，不代表线上总体。不得把不同任务共享输出结构本身当作重复；重点寻找相同解题问题仅改数字的复刻、错误答案及不可评分要求。',
                json.dumps(material,ensure_ascii=False),protocol['material_review_criteria'],
                'material-review:'+cell,time.monotonic()+protocol['constraints']['latencyMaxMs']/1000)
            session.result['material_reviews'][cell]=review
            session.persist()
            if not review['passed'] or review['score']<protocol['constraints']['qualityMin']:
                session.result['status']='material-review-rejected'
                return session.result
        for i, task in enumerate(calibration):
            for mid in session.models:
                trial(task,'cal-direct',f'cal-direct-{i}-{mid}','calibration',mode='direct',fixed_model=mid)
                trial(task,'cal-dag',f'cal-dag-{i}-{mid}','calibration',mode='manual',fixed_model=mid)
            for node in task['plan']['nodes']:
                for mid in session.models:
                    session.probe_node(task,node['node_id'],mid)
            order = list(session.models)
            assignments = {node['node_id']:order[(j+i)%len(order)] for j,node in enumerate(task['plan']['nodes'])}
            trial(task,'handoff',f'handoff-{i}','calibration',mode='manual',explicit_assignments=assignments)
        direct_rows = [r for r in session.result['runs'] if r.get('arm')=='cal-direct']
        frozen = freeze_direct_models(calibration,direct_rows,manifest,protocol['constraints'],held_out_ids=[t['task_id'] for t in tests])
        profile = build_stratified_profile(session.result['observations'],manifest,
            calibration_task_ids=[t['task_id'] for t in calibration],test_task_ids=[t['task_id'] for t in tests],allow_unavailable_evaluation=True)
        independent = defaultdict(set)
        for row in session.result['observations']['observations']:
            f=row['features']; lo,hi=next(b for b in INPUT_BANDS if b[0]<=f['input_budget_tokens']<b[1])
            independent[row['model_id'],f['node_type'],f['difficulty'],f['risk'],lo,hi].add(row['task_id'])
        keep=[]
        for p in profile['candidates']:
            key=tuple(p[k] for k in ('model_id','node_type','difficulty','risk','input_min_tokens','input_max_tokens'))
            if len(independent[key])>=3: keep.append(p)
            else: profile['exclusions'].append({**p,'reason':'fewer-than-three-independent-tasks'})
        profile['candidates']=keep
        profiles = load_profile(profile,manifest) if keep else ()
        quality={}
        for cell in protocol['coverage_cells']:
            ranks=[]
            for mid in session.models:
                rows=[r for r in session.result['runs'] if r.get('arm')=='cal-dag' and r['cell']==cell and set(r['assignments'].values())=={mid}]
                if len(rows)==3 and all(r['score'] is not None for r in rows):
                    ranks.append((-statistics.mean(r['score'] for r in rows),statistics.mean(r['deployment_cost'] for r in rows),mid))
            quality[cell]=min(ranks)[2] if ranks else None
        session.result.update(direct_calibration=frozen,node_profile=profile,quality_baselines=quality,
            calibration_frozen_sha256=digest({'direct':frozen,'profile':profile,'quality':quality}))
        session.persist()
        for task in tests:
            for suffix in ('a','b'):
                session.cache_plan(task,task['task_id']+'-'+suffix)
            arms=list(ARMS);random.Random(str(protocol['order_seed'])+task['task_id']).shuffle(arms)
            for arm in arms:
                method='B' if arm.endswith('-b') else 'A'
                kw={'mode':'manual','method':method,'profiles':profiles}
                if arm.startswith('direct-'):
                    mid=frozen['selections'][task['cell']][method]['selected_model']
                    kw.update(mode='direct',fixed_model=mid,unavailable=mid is None)
                elif arm.startswith('auto-'):
                    kw.update(mode='auto-cold' if arm.startswith('auto-cold') else 'auto-reuse',cache_id=task['task_id']+'-'+arm[-1])
                elif arm.startswith('dag-single-'): kw['assignment_mode']='single-model'
                elif arm=='dag-quality': kw.update(fixed_model=quality[task['cell']],unavailable=quality[task['cell']] is None)
                elif arm.startswith('dag-strong-'): kw.update(fixed_model='strong',serial=arm.endswith('serial'))
                trial(task,arm,task['task_id']+'-'+arm,'test',**kw)
    except Exception:
        session.result['status']='stopped-on-infrastructure'
        raise
    finally:
        session.result['analysis']=summarize(session,protocol,preview)
        result=session.close()
    return result
