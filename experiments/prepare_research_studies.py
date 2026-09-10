"""生成 #39/#40 分离的合成材料协议；只做零调用准备，不代表真实团队任务。"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import random

from refractrouter.dag_study import implementation_fingerprint
from refractrouter.dag_study_execution import write_json
from refractrouter.manifest import load_model_manifest
from refractrouter.research_protocol import FIXED_ARMS, PLANNING_ARMS, PLAN_CRITERIA, digest, material_digest

ROOT = Path(__file__).resolve().parents[1]
CHALLENGES = ('parallel', 'serial', 'coupled', 'short', 'oversplit', 'bottleneck', 'handoff')
INSTRUCTIONS = {
    'parallel': '费用和业务风险分别直接由原始材料决定，可以独立分析，最后综合。',
    'serial': '必须先计算两方案总费用，再计算预算缺口，风险判断必须引用该缺口。预算为甲总费用的九成。',
    'coupled': '价格、迁移窗口和离线能力必须同时满足，不能只按某一维度决定方案。',
    'short': '只将给定句子改写得简洁，保留原意，不增加分析：',
    'oversplit': '交付一段可直接使用的简短结论；材料规模很小，不需要分章节。',
    'bottleneck': '最终交付必须包含逐项费用汇总、总费用、冲突核对、两方案风险以及带条件建议，不能只转述中间节点。',
    'handoff': '最终建议必须引用所有材料来源编号，说明两方案费用差额及风险限制；不能遗漏任何必要上游事实。',
}


def make_task(issue, cell, split, index, *, family='comparison', scale='small', risk='medium', challenge='parallel'):
    tid = f'i{issue}_{cell}_{split}_{index}'
    rng = random.Random(tid)
    template = 'single-answer' if challenge in ('short', 'oversplit') else 'serial-analysis' if challenge in ('serial', 'coupled') or family == 'verification' else 'parallel-analysis'
    plan = json.loads((ROOT / f'data/task-plans/{template}-v2.json').read_text())
    plan['decomposition_reason'] = '人工冻结参考计划；用于隔离拆分与选模的变化，不代表自动规划正确性。'
    count = 90 if scale == 'large' else 3
    records = []
    total_a = total_b = 0
    for i in range(count):
        a, b = rng.randint(20, 180), rng.randint(20, 180)
        quantity = rng.randint(1, 12)
        total_a += a * quantity
        total_b += b * quantity
        records.append(f'材料 {tid}-S{i+1:03d}：项目 {i+1} 的年度数量为 {quantity}，甲单价 {a} 元，乙单价 {b} 元。两方案价格均已含全部服务费用，年度数量固定，不另外叠加月费或折扣。')
    risks = f'材料 {tid}-R：甲支持离线查阅，每日同步一次；乙每五分钟同步，断网时不能查阅。仅有一次恢复演练，甲 45 分钟、乙 80 分钟，不能推断长期故障率。'
    if risk == 'high':
        risks += '本场景涉及未发布内部资料；任何外部保存均要求可验证删除，乙当前仅有口头承诺。'
    else:
        risks += '本场景只处理公开资料；要求明确未验证的假设。'
    if family == 'verification':
        challenge = 'serial'
    criteria = ['准确计算并比较年度总费用，列出来源编号和计算口径。', '结合所有风险约束提出带条件建议，保留不确定性，不虚构事实或声称执行工具。']
    if challenge == 'serial':
        criteria.append('以甲总费用的九成为预算，计算两方案预算缺口，并在风险判断中引用计算结果。')
    if challenge == 'handoff':
        criteria.append('引用每一条材料来源编号，保留费用差额及全部风险限制。')
    if challenge == 'bottleneck':
        criteria.append('逐项列出费用小计，核对冲突并完成综合判断，不只转述上游摘要。')
    if challenge == 'coupled':
        risks += '两方案迁移窗口均为周六两小时；要求断网查阅，并在每年费用不超过甲总额的 110% 时优先满足离线要求。'
        criteria.append('同时核对年度费用门槛、迁移窗口和离线能力，明确哪些方案满足全部条件。')
    task = '这是合成封闭材料任务。只使用下列材料，不检索或执行工具。' + INSTRUCTIONS[challenge] + '\n' + '\n'.join(records) + '\n' + risks
    if challenge == 'short':
        task = f'把下面一句话改写成更简洁的中文，保留交付时间和条件：项目 {tid} 的 {rng.randint(3,20)} 份草稿应在材料全部核对完毕之后，于周五下午提交。'
        criteria = ['保留原始条件、数量和交付时间，表达更简洁，不添加原文不存在的事实。']
    plan['acceptance_criteria'] = criteria
    context = {}
    for node in plan['nodes']:
        cap = 32768 if scale == 'large' else 8192
        if node['node_id'] == plan['final_node_id']:
            cap = 131072 if scale == 'large' else 32768
            node['contract']['covers'] = list(range(len(criteria)))
        node['contract']['capability'].update(input_budget_tokens=cap, risk=risk)
        if family == 'verification' and node['node_id'] != plan['final_node_id']:
            node['node_type'] = 'extraction' if not node['parents'] else 'verification'
            node['prompt_template'] = '抽取并核对全部费用事实，给出总额与证据。' if not node['parents'] else '根据上游费用核验方案约束，明确矛盾及风险。'
            node['contract']['objective'] = node['prompt_template']
        if node['node_id'] == 'risk' and node['parents']:
            node['prompt_template'] = ('基于上游费用计算预算缺口并引用缺口评估风险，保留全部业务风险。'
                if challenge == 'serial' else '结合上游费用同时核对价格门槛、迁移窗口和离线能力，保留全部风险。')
            node['contract']['objective'] = node['prompt_template']
        if node['contract']['output']['format'] == 'json':
            context[node['node_id']] = {'result': f'甲年度合计 {total_a} 元，乙 {total_b} 元，甲减乙为 {total_a-total_b} 元。' if node['node_id']=='cost' else risks,
                'evidence': f'来自材料 {tid}-S001 至 {tid}-S{count:03d} 及 {tid}-R。',
                'assumptions': '年度数量与单价固定；风险演练仅一次，不能推断长期可靠性。'}
        else:
            context[node['node_id']] = {'text': '人工参考占位，不作为模型交付或评分。'}
    return {'task_id': tid, 'cell': cell, 'family': family, 'split': split, 'source_id': tid,
        'source_kind': 'independently-seeded-synthetic-records',
        'template_family': 'sentence-rewrite' if challenge == 'short' else 'two-option-cost-risk',
        'task': task, 'criteria': criteria,
        'material_sha256': material_digest(task), 'minimum_material_bytes': 9000 if scale=='large' else 1,
        'plan': plan, 'reference_context': context, 'expected_totals': {'a': total_a, 'b': total_b},
        'challenge': challenge, 'input_scale': scale, 'risk': risk}


def prepare(issue):
    tasks, cells = [], []
    dimensions = ([(f'{family}_{scale}_{risk}', family, scale, risk, 'parallel')
                   for family in ('comparison', 'verification') for scale in ('small', 'large')
                   for risk in ('medium', 'high')] if issue == 39 else
                  [(case, 'comparison', 'small', 'medium', case) for case in CHALLENGES])
    for cell, family, scale, risk, challenge in dimensions:
        cells.append(cell)
        for split, n in (('development', 1), ('calibration', 3), ('test', 3)):
            for i in range(1, n + 1):
                tasks.append(make_task(issue, cell, split, i, family=family, scale=scale, risk=risk, challenge=challenge))
    manifest_path = ROOT / 'data/model-manifests/volcengine-agent-plan.json'
    manifest = load_model_manifest(manifest_path)
    return {'schema_version': 'research-suite-v1', 'issue': issue, 'status': 'draft-offline-only',
        'manifest_path': '../model-manifests/volcengine-agent-plan.json', 'manifest_sha256': digest(asdict(manifest)),
        'implementation_sha256': implementation_fingerprint(), 'coverage_cells': cells, 'tasks': tasks,
        'arms': list(FIXED_ARMS if issue == 39 else PLANNING_ARMS), 'repeats': 2,
        'calibration_per_cell': 3, 'test_per_cell': 3, 'max_node_fallbacks': 0, 'planner_repairs': 0,
        'failure_policy': 'isolate-settled-stop-on-infrastructure', 'planner_model': 'strong',
        'planner_input_cap': 32768, 'auto_node_input_cap': 32768, 'judge_input_cap': 262144,
        'execution_policy': {'maxConcurrency': 2, 'providerConcurrency': {'ark-plan': 2}, 'providerMinIntervalMs': {'ark-plan': 100}},
        'constraints': {'qualityMin': 80, 'costMax': 150, 'latencyMaxMs': 300000,
                        'weights': {'quality': .5, 'cost': .25, 'latency': .25}},
        'plan_review_criteria': list(PLAN_CRITERIA),
        'acceptance': {'primary_pairs': [['dag-node-a','dag-single-a'],['dag-node-b','dag-single-b']] if issue==39 else
            [['auto-cold-a','direct-a'],['auto-cold-b','direct-b']],
            'multiplicity': 'bonferroni-two-primary-comparisons', 'bootstrap_unit': 'task_id',
            'bootstrap_repeats': 2000, 'bootstrap_seed': 3940, 'assumed_task_delta_sd': 10,
            'target_mean_half_width': 5, 'maximum_quality_loss': 3, 'minimum_cost_saving': .2,
            'maximum_latency_ratio': 1.1, 'human_review': '每个规划类别按 task_id 首个留出任务抽检全部方案，并复核所有被拒计划；人工结果单独记录，未收到时不得标记完成。'},
        'limitations': ['合成材料共享模板，随机种子只保证参数生成独立，不证明独立任务迁移；不能据此关闭 Issue。',
            '分层独立任务仅三个，不支持精确的分层收益或尾延迟结论。',
            '参考上下文由冻结材料计算及固定风险说明组成，不能用它冒充真实跨模型交接。']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--issue', type=int, choices=(39,40), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('必须使用新协议文件，不覆盖已冻结材料')
    write_json(args.output, prepare(args.issue))
