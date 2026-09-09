"""迁移与规划实验的材料隔离、覆盖检查和零调用包络。"""
from collections import Counter
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import re

from .dag_study import implementation_fingerprint
from .node_routing import number
from .responses_api import output_token_limit
from .task_execution import node_messages
from .task_plan import validate_plan
from .task_scheduling import ExecutionPolicy

FIXED_ARMS = ('dag-node-a', 'dag-node-b', 'dag-single-a', 'dag-single-b',
              'dag-quality', 'dag-strong-serial', 'dag-strong-parallel', 'direct-a', 'direct-b')
PLANNING_ARMS = ('manual-a', 'manual-b', 'auto-cold-a', 'auto-cold-b',
                 'auto-reuse-a', 'auto-reuse-b', 'direct-a', 'direct-b')
PLAN_CRITERIA = ('原始交付条件全部有明确职责覆盖，不用改写条件降低要求。',
    '必要依赖存在，声明的每条边都有真实字段消费，不制造无意义串行依赖。',
    '上下文充分，输入材料和来源可以追溯，无需虚构缺失数据。',
    '允许单节点和不拆分，节点职责不重复，汇总包含原始任务所需内容。',
    '节点能力与输入容量声明合理，拆分符合任务的耦合程度。')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def material_digest(text):
    return hashlib.sha256(re.sub(r'\s+', '', text).encode()).hexdigest()


def historical_materials(root):
    """只读取冻结任务正文；旧测试材料不会重新获得留出身份。"""
    materials = set()
    for path in sorted((Path(root) / 'data/benchmarks').glob('*.json')):
        raw = json.loads(path.read_text())
        if not isinstance(raw, dict) or raw.get('schema_version') == 'research-suite-v1':
            continue
        for task in raw.get('tasks', []):
            if isinstance(task, dict) and isinstance(task.get('task'), str):
                materials.add(material_digest(task['task']))
    return materials


def validate_protocol(raw, manifest, *, excluded_materials=()):
    if raw.get('schema_version') != 'research-suite-v1' or raw.get('issue') not in (39, 40):
        raise ValueError('unsupported research protocol')
    if raw.get('implementation_sha256') != implementation_fingerprint():
        raise ValueError('frozen implementation changed')
    if raw.get('manifest_sha256') != digest(asdict(manifest)):
        raise ValueError('frozen manifest changed')
    arms = FIXED_ARMS if raw['issue'] == 39 else PLANNING_ARMS
    if tuple(raw.get('arms', [])) != arms:
        raise ValueError('unexpected study arms')
    if raw.get('max_node_fallbacks') != 0 or raw.get('planner_repairs') != 0:
        raise ValueError('protocol requires zero recovery and zero planner repairs')
    if raw.get('failure_policy') != 'isolate-settled-stop-on-infrastructure':
        raise ValueError('invalid stop policy')
    ExecutionPolicy.from_request(raw['execution_policy'])
    for key in ('costMax', 'latencyMaxMs'):
        number(raw['constraints'][key], key, positive=True)
    number(raw['constraints']['qualityMin'], 'qualityMin', maximum=100)
    from .model_selection import Weights
    Weights(**raw['constraints']['weights']).normalized()
    for key in ('repeats', 'calibration_per_cell', 'test_per_cell'):
        if type(raw[key]) is not int or not 1 <= raw[key] <= 20:
            raise ValueError('invalid sample count')
    if raw['calibration_per_cell'] < 3:
        raise ValueError('requires three independent calibration tasks per cell')
    for key in ('planner_input_cap', 'auto_node_input_cap', 'judge_input_cap'):
        if type(raw[key]) is not int or not 256 <= raw[key] <= 262144:
            raise ValueError('invalid input cap')
    expected_cells = set(raw['coverage_cells'])
    if not expected_cells or len(expected_cells) != len(raw['coverage_cells']):
        raise ValueError('empty or duplicate coverage cells')
    if raw['planner_model'] not in {m.model_id for m in manifest.candidates}:
        raise ValueError('planner is not a frozen candidate')
    ids, sources, hashes, splits = set(), {}, {}, Counter()
    diagnostics = []
    for task in raw['tasks']:
        tid, split, cell = task['task_id'], task['split'], task['cell']
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,90}', tid) or tid in ids:
            raise ValueError('invalid or duplicate task ID')
        if split not in ('development', 'calibration', 'test') or cell not in expected_cells:
            raise ValueError('invalid split or coverage cell')
        ids.add(tid)
        fingerprint = material_digest(task['task'])
        if fingerprint != task['material_sha256'] or fingerprint in hashes or fingerprint in excluded_materials:
            raise ValueError('duplicate, historical or changed material')
        hashes[fingerprint] = tid
        source = task['source_id']
        if not source or source in sources:
            raise ValueError('source reused across independent tasks')
        sources[source] = split
        splits[cell, split] += 1
        plan = validate_plan(task['plan'], required_criteria=task['criteria'], require_v2=True)
        measured = {}
        for node in plan.nodes:
            messages = node_messages(task['task'], node, plan.contracts[node.node_id], task['reference_context'])
            measured[node.node_id] = len(json.dumps(messages, ensure_ascii=False).encode()) + 256
        if len(task['task'].encode()) < task['minimum_material_bytes']:
            raise ValueError('input scale is only a declaration, not actual material')
        diagnostics.append({'task_id': tid, 'cell': cell, 'split': split,
                            'material_bytes': len(task['task'].encode()), 'reference_input_bounds': measured})
    for cell in expected_cells:
        if (splits[cell, 'development'] < 1 or splits[cell, 'calibration'] != raw['calibration_per_cell']
                or splits[cell, 'test'] != raw['test_per_cell']):
            raise ValueError('incomplete independent split matrix')
    acceptance = raw['acceptance']
    if acceptance['primary_pairs'] != ([['dag-node-a', 'dag-single-a'], ['dag-node-b', 'dag-single-b']]
            if raw['issue'] == 39 else [['auto-cold-a', 'direct-a'], ['auto-cold-b', 'direct-b']]):
        raise ValueError('invalid primary comparisons')
    if acceptance['multiplicity'] != 'bonferroni-two-primary-comparisons' or acceptance['bootstrap_unit'] != 'task_id':
        raise ValueError('invalid inference policy')
    if raw['issue'] == 40 and raw['plan_review_criteria'] != list(PLAN_CRITERIA):
        raise ValueError('plan semantic criteria changed')
    sd = number(acceptance['assumed_task_delta_sd'], 'assumed SD', positive=True)
    half = number(acceptance['target_mean_half_width'], 'target half width', positive=True)
    # 两个主比较各使用 97.5% 区间，正态规划近似 z=2.242；实际推断仍按任务聚类。
    required = math.ceil((2.242 * sd / half) ** 2)
    n = sum(t['split'] == 'test' for t in raw['tasks'])
    if n < required:
        raise ValueError('planned independent tasks do not meet stated precision assumption')
    template_splits = {}
    for task in raw['tasks']:
        template_splits.setdefault(task['template_family'], set()).add(task['split'])
    shared = sorted(k for k, splits in template_splits.items() if len(splits) > 1)
    return {'tasks': diagnostics, 'test_parameter_draws': n, 'required_under_assumed_sd': required,
            'independent_task_transfer_verified': False,
            'templates_shared_across_splits': shared,
            'template_families': len(template_splits),
            'scope': '精度基于预设标准差的规划近似，不保证实际区间宽度；分层与 p95 仅作描述。'}


def preflight(raw, manifest, *, excluded_materials=()):
    coverage = validate_protocol(raw, manifest, excluded_materials=excluded_materials)
    candidates = manifest.candidates
    production = evaluation = 0.0
    calls = Counter()
    def cost(model, cap):
        out = output_token_limit(model)
        if cap + out > model.context_window:
            raise ValueError('frozen envelope exceeds model context')
        return cap / 1000 * model.input_cost_per_1k + out / 1000 * model.output_cost_per_1k
    judge = cost(manifest.judge, raw['judge_input_cap'])
    planner = next(m for m in candidates if m.model_id == raw['planner_model'])
    planner_cost = cost(planner, raw['planner_input_cap'])
    runs = []
    for task in raw['tasks']:
        caps = [n['contract']['capability']['input_budget_tokens'] for n in task['plan']['nodes']]
        if task['split'] == 'development':
            continue
        if task['split'] == 'calibration':
            # 每模型的整图、整任务及固定人工上下文的节点探测；另做一条异构交接路线。
            production += sum(sum(cost(m, c) for c in caps) * 2 + cost(m, max(caps)) for m in candidates)
            production += sum(cost(candidates[i % len(candidates)], cap) for i, cap in enumerate(caps))
            counts = (2 * len(caps) + 1) * len(candidates) + len(caps)
            judges = (len(caps) + 2) * len(candidates) + 1
            calls['calibration_production'] += counts
            calls['calibration_evaluation'] += judges
            evaluation += judges * judge
        else:
            if raw['issue'] == 40:
                calls['cached_plan_setup'] += 2
                calls['cached_plan_review'] += 2
                production += 2 * planner_cost
                evaluation += 2 * judge
            for repeat in range(1, raw['repeats'] + 1):
                for arm in raw['arms']:
                    auto = arm.startswith('auto-')
                    cold = arm.startswith('auto-cold')
                    node_caps = [raw['auto_node_input_cap']] * 8 if auto else [max(caps)] if arm.startswith('direct-') else caps
                    ceiling = sum(max(cost(m, c) for m in candidates) for c in node_caps)
                    production += ceiling + (planner_cost if cold else 0)
                    evaluation += judge * (2 if cold else 1)
                    calls['test_production'] += len(node_caps) + int(cold)
                    calls['test_evaluation'] += 2 if cold else 1
                    runs.append({'task_id': task['task_id'], 'cell': task['cell'], 'repeat': repeat, 'arm': arm})
    return {'schema_version': 'research-preflight-v1', 'real_model_calls': 0, 'protocol_sha256': digest(raw),
            'live_execution_ready': False,
            'blocking_requirements': ['独立任务来源与模板近重复审查尚未通过。',
                '真实运行器、校准冻结、端到端计时与失败分母审计尚未完成。',
                '须对最终冻结协议取得付费范围与预算授权；#40 还需要真实人工复核。'],
            'coverage': coverage, 'runs': runs, 'planned_calls': dict(calls), 'maximum_calls': sum(calls.values()),
            'budget': {'billing_unit': manifest.billing_unit, 'production': production, 'evaluation': evaluation},
            'limitations': ['输入采用实际消息字节保守界，输出采用完整模型上限；调用前按实际请求再次预留。',
                '人工参考上下文只用于独立校准；真实异构交接与最终评分另行记录。',
                '不包含 DSH 外层调用；自动计划复用的初始规划及语义评审已另计。']}
