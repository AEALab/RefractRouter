"""对正式留出实验做零模型调用的质量失败归因。"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from refractrouter.moa_review import MOA_POLICY, digest, final_quality_status
from refractrouter.quality_study import file_digest


ARMS = ('direct-strong', 'task-selector', 'direct-or-dag')
ROUTING_STAGES = ('selector', 'planner', 'worker', 'final')
EVALUATION_STAGES = ('delivery-judge', 'research-judge')


def _counts(values):
    return dict(sorted(Counter(values).items()))


def _bound_review(records, row):
    matches = [record for record in records
               if record.get('run_id') == row['run_id']
               and record.get('task_id') == row['task_id']
               and record.get('output_sha256') == digest(row['output'])
               and record.get('policy_sha256') == digest(MOA_POLICY)]
    if len(matches) != 1:
        raise ValueError(f'{row["run_id"]}: MoA 评审绑定数量不是 1')
    return matches[0]


def _cost_analysis(result, rows, final_analysis):
    """按实际调用拆解费用，并显式分离路由执行与实验评审。"""
    row_by_id = {row['run_id']: row for row in rows}
    stages = {arm: defaultdict(lambda: {'calls': 0, 'afp': 0.0}) for arm in ARMS}
    run_stages = defaultdict(lambda: defaultdict(
        lambda: {'calls': 0, 'afp': 0.0, 'input_tokens': 0, 'output_tokens': 0}
    ))
    unmatched = []
    for call in result.get('calls', []):
        matches = [run_id for run_id in row_by_id
                   if call['label'].startswith(f'{run_id}:')]
        if len(matches) != 1:
            unmatched.append(call['label'])
            continue
        arm = row_by_id[matches[0]]['arm']
        stage = call['stage']
        stages[arm][stage]['calls'] += 1
        stages[arm][stage]['afp'] += call.get('charged', 0.0)
        run_stages[matches[0]][stage]['calls'] += 1
        run_stages[matches[0]][stage]['afp'] += call.get('charged', 0.0)
        run_stages[matches[0]][stage]['input_tokens'] += call.get('input_tokens', 0)
        run_stages[matches[0]][stage]['output_tokens'] += call.get('output_tokens', 0)
    if unmatched:
        raise ValueError(f'有 {len(unmatched)} 个调用不能唯一绑定运行：{unmatched[:3]}')

    arms = {}
    baseline = final_analysis['arms']['direct-strong']
    baseline_total = baseline['accepted_task_metrics']['total_afp_all_tasks']
    baseline_accepted = baseline['accepted_task_count']
    baseline_per_accepted = baseline['accepted_task_metrics']['afp_per_accepted_task']
    for arm in ARMS:
        metrics = final_analysis['arms'][arm]
        accepted = metrics['accepted_task_count']
        accepted_metrics = metrics['accepted_task_metrics']
        total = accepted_metrics['total_afp_all_tasks']
        routing_afp = sum(stages[arm][stage]['afp'] for stage in ROUTING_STAGES)
        evaluation_afp = sum(stages[arm][stage]['afp'] for stage in EVALUATION_STAGES)
        arms[arm] = {
            'calls': sum(item['calls'] for item in stages[arm].values()),
            'total_afp_all_tasks': total,
            'routing_execution_afp': routing_afp,
            'evaluation_afp': evaluation_afp,
            'evaluation_share': evaluation_afp / total if total else 0.0,
            'accepted_tasks': accepted,
            'afp_per_accepted_task': accepted_metrics['afp_per_accepted_task'],
            'gross_afp_change_vs_direct_strong': total / baseline_total - 1,
            'accepted_task_change_vs_direct_strong': accepted / baseline_accepted - 1,
            'afp_per_accepted_change_vs_direct_strong': (
                accepted_metrics['afp_per_accepted_task'] / baseline_per_accepted - 1
            ),
            'stages': {
                stage: {
                    'calls': item['calls'],
                    'afp': item['afp'],
                }
                for stage, item in sorted(stages[arm].items())
            },
        }

    dag_rows = [row for row in rows
                if row['arm'] == 'direct-or-dag' and row['node_count'] > 1]
    dag_cases = []
    for dag in dag_rows:
        peers = [row for row in rows
                 if row['task_id'] == dag['task_id'] and row['repeat'] == dag['repeat']]
        dag_cases.append({
            'run_id': dag['run_id'],
            'task_id': dag['task_id'],
            'repeat': dag['repeat'],
            'node_count': dag['node_count'],
            'comparisons': [
                {
                    'arm': peer['arm'],
                    'final_status': peer['final_status'],
                    'node_count': peer['node_count'],
                    'online_afp': peer['online_afp'],
                    'offline_afp': peer['offline_afp'],
                    'total_afp': peer['online_afp'] + peer['offline_afp'],
                    'routing_execution_afp': sum(
                        run_stages[peer['run_id']][stage]['afp']
                        for stage in ROUTING_STAGES
                    ),
                    'routing_execution_tokens': sum(
                        run_stages[peer['run_id']][stage]['input_tokens']
                        + run_stages[peer['run_id']][stage]['output_tokens']
                        for stage in ROUTING_STAGES
                    ),
                    'routing_stages': {
                        stage: dict(run_stages[peer['run_id']][stage])
                        for stage in ROUTING_STAGES
                        if run_stages[peer['run_id']][stage]['calls']
                    },
                }
                for peer in sorted(peers, key=lambda item: ARMS.index(item['arm']))
            ],
        })
    return {
        'accounting_scope': (
            'routing_execution_afp 包含 selector、planner、worker、final；evaluation_afp '
            '包含在线 delivery-judge 与离线 research-judge。主指标沿用冻结口径，二者均计入。'
        ),
        'arms': arms,
        'actual_multi_node_cases': dag_cases,
        'identification_limit': (
            '只有 1 次真实多节点运行，无法从本批数据识别 DAG 拆分对成本的平均因果效应。'
        ),
    }


def analyze(result, tasks, moa_records, final_analysis):
    """返回可复算的失败分层、任务稳定性与路由行为。"""
    task_by_id = {task['task_id']: task for task in tasks}
    rows = []
    failed_checks = defaultdict(Counter)
    for row in result['runs']:
        task = task_by_id[row['task_id']]
        item = {
            'run_id': row['run_id'], 'task_id': row['task_id'], 'arm': row['arm'],
            'repeat': row['repeat'], 'category': task['category'],
            'structure_stratum': task['structure_stratum'], 'run_status': row['status'],
            'node_count': len(row.get('nodes', [])),
            'online_afp': row.get('online_afp', 0.0),
            'offline_afp': row.get('offline_afp', 0.0),
        }
        if 'output' in row:
            item['moa_consensus'] = _bound_review(moa_records, row)['consensus']['overall']
        else:
            item['moa_consensus'] = 'no-output'
        if row['status'] == 'failed':
            item.update(final_status='fail', failure_layer='execution-failed')
        elif row['status'] in ('withheld', 'deadline-failed'):
            item.update(final_status='fail', failure_layer='delivery-gate')
        elif row['status'] == 'delivered-unconfirmed' and 'output' in row:
            deterministic = row['adjudication']['deterministic']['status']
            consensus = item['moa_consensus']
            status = final_quality_status(deterministic, consensus)
            if deterministic == 'fail':
                layer = 'deterministic-check'
            elif consensus == 'fail':
                layer = 'moa-semantic'
            elif consensus == 'pending':
                layer = 'moa-pending'
            else:
                layer = 'pass'
            item.update(final_status=status, failure_layer=layer,
                        deterministic_status=deterministic, moa_consensus=consensus)
            for check in row['adjudication']['deterministic'].get('checks', []):
                if check['status'] == 'fail':
                    kind = 'citation' if check['check'].endswith(':sources') else 'value'
                    failed_checks[row['arm']][kind] += 1
                    item.setdefault('failed_checks', []).append(check['check'])
        else:
            item.update(final_status='pending', failure_layer='unclassified')
        rows.append(item)

    arms = {}
    for arm in ARMS:
        group = [row for row in rows if row['arm'] == arm]
        task_groups = defaultdict(list)
        for row in group:
            task_groups[row['task_id']].append(row)
        robust = {task_id: all(row['final_status'] == 'pass' for row in task_rows)
                  for task_id, task_rows in task_groups.items()}
        arms[arm] = {
            'runs': len(group),
            'final_status': _counts(row['final_status'] for row in group),
            'failure_layer': _counts(row['failure_layer'] for row in group),
            'moa_consensus_all_runs': _counts(row['moa_consensus'] for row in group),
            'deterministic_failed_check_instances': dict(failed_checks[arm]),
            'robust_pass_tasks': sum(robust.values()),
            'failed_tasks': sorted(task_id for task_id, passed in robust.items() if not passed),
            'by_structure': {
                structure: {
                    'runs': len(part),
                    'final_status': _counts(row['final_status'] for row in part),
                    'robust_pass_tasks': sum(
                        all(r['final_status'] == 'pass' for r in task_groups[task_id])
                        for task_id in sorted({r['task_id'] for r in part})
                    ),
                    'tasks': len({r['task_id'] for r in part}),
                }
                for structure in ('direct', 'parallel', 'sequential')
                if (part := [row for row in group if row['structure_stratum'] == structure])
            },
        }

    route_rows = [row for row in rows if row['arm'] == 'direct-or-dag']
    dag_rows = [row for row in route_rows if row['node_count'] > 1]
    routing = {
        'direct_or_dag_runs': len(route_rows),
        'single_node_runs': sum(row['node_count'] == 1 for row in route_rows),
        'multi_node_runs': len(dag_rows),
        'multi_node_run_ids': [row['run_id'] for row in dag_rows],
        'multi_node_final_status': _counts(row['final_status'] for row in dag_rows),
        'interpretation': ('当前 direct-or-dag 路线 36 次中几乎全部退化为单节点；'
                           '臂间差异不能归因于 DAG 拆分收益。'),
    }

    cost = _cost_analysis(result, rows, final_analysis)

    expected = {arm: final_analysis['arms'][arm]['run_counts'] for arm in ARMS}
    observed = {arm: arms[arm]['final_status'] for arm in ARMS}
    for arm in ARMS:
        normalized = {status: observed[arm].get(status, 0) for status in ('pass', 'fail', 'pending')}
        if normalized != expected[arm]:
            raise ValueError(f'{arm}: 归因结果与最终分析不一致：{normalized} != {expected[arm]}')

    return {
        'schema_version': 'quality-failure-attribution-v1',
        'scope': 'live-01 已冻结证据的零模型调用事后归因；不改变确认性结论。',
        'counting_rule': ('failure_layer 按首次决定最终状态的层互斥计数；'
                          'moa_consensus_all_runs 另列全部可评审输出，允许与交付门禁重叠。'),
        'arms': arms,
        'routing_behavior': routing,
        'cost_analysis': cost,
        'run_rows': rows,
        'decision': {
            'current_result': '三条路线均未达到 90% 质量门槛，当前确认性前沿为空。',
            'primary_bottleneck': ('低价路线虽然降低总 AFP，但质量损失使每个合格任务的'
                                   '成本反而上升；DAG 本身的成本效应尚不可识别。'),
            'next_actions': [
                '先修复结构化 findings 的来源传播、值校验与正文一致性。',
                '为 direct-or-dag 增加明确的路由决策证据，并保证正式实验覆盖足够的真实多节点运行。',
                '对失败输出做真人抽查，确认自动门槛没有系统性误杀后再冻结新实验。',
            ],
        },
    }


def markdown(report):
    lines = [
        '# live-01 质量失败归因', '',
        '本报告只复算既有证据，不产生模型调用，也不改变冻结协议与最终质量结论。', '',
        '## 结论', '',
        '三条路线都没有达到 90% 质量门槛。当前主要问题是输出质量，不是路由费用。',
        '更关键的是，`direct-or-dag` 的 36 次运行中只有 1 次真正产生多节点 DAG，',
        '因此本批数据不能证明 DAG 拆分带来质量、成本或时间收益。', '',
        '## 失败发生在哪一层', '',
        '| 路线 | 通过 | 执行失败 | 交付门禁失败 | 确定性检查失败 | MoA 语义失败 |',
        '| --- | ---: | ---: | ---: | ---: | ---: |',
    ]
    for arm, row in report['arms'].items():
        layer = row['failure_layer']
        lines.append(f'| `{arm}` | {row["final_status"].get("pass", 0)} | '
                     f'{layer.get("execution-failed", 0)} | {layer.get("delivery-gate", 0)} | '
                     f'{layer.get("deterministic-check", 0)} | {layer.get("moa-semantic", 0)} |')
    lines += [
        '',
        '交付门禁失败也是内容质量失败：它表示在线交付评审已发现正文矛盾、关键事实错误或',
        '硬约束遗漏。上表按首次决定最终状态的层互斥计数；被交付门禁扣留的输出仍可能在',
        '离线 MoA 中失败，因此不能把 `MoA 语义失败` 的 0 理解为模型共识全过。', '',
        '全部可评审输出的 MoA 共识为：', '',
        '| 路线 | pass | fail | pending | 无输出 |',
        '| --- | ---: | ---: | ---: | ---: |',
    ]
    for arm, row in report['arms'].items():
        moa = row['moa_consensus_all_runs']
        lines.append(f'| `{arm}` | {moa.get("pass", 0)} | {moa.get("fail", 0)} | '
                     f'{moa.get("pending", 0)} | {moa.get("no-output", 0)} |')
    lines += [
        '',
        '这解释了为什么单看 MoA 时 `direct-strong` 是 28 过、8 不过；这 8 次已经先被在线',
        '交付门禁扣留。最终质量还要合取运行状态与确定性检查，不能只看 MoA。', '',
        '确定性检查失败主要来自结构化值或 `sources` 引用。', '',
        '## 结构差异', '',
        '| 路线 | direct 稳定通过任务 | parallel 稳定通过任务 | sequential 稳定通过任务 |',
        '| --- | ---: | ---: | ---: | ---: |',
    ]
    for arm, row in report['arms'].items():
        structures = row['by_structure']
        lines.append(f'| `{arm}` | {structures["direct"]["robust_pass_tasks"]}/4 | '
                     f'{structures["parallel"]["robust_pass_tasks"]}/4 | '
                     f'{structures["sequential"]["robust_pass_tasks"]}/4 |')
    lines += [
        '',
        '`direct-strong` 在 direct 结构上 4/4 稳定通过，但 sequential 只有 1/4。其交付门禁',
        '失败集中在跨时区顺序、迁移关键路径和优先级瀑布：正文与 findings 不一致，或把',
        '有向顺序、加总值写错。', '',
        '`task-selector` 与 `direct-or-dag` 的主要损失来自确定性检查。两者分别有 14 次和',
        '10 次运行在值或引用上失败，说明当前便宜模型/组合链路没有可靠保留结构化事实与',
        '来源绑定。', '',
        '## 路由实验的关键限制', '',
        f'- `direct-or-dag` 单节点：{report["routing_behavior"]["single_node_runs"]}/36；',
        f'- 真正多节点：{report["routing_behavior"]["multi_node_runs"]}/36，运行 ID 为 '
        f'`{", ".join(report["routing_behavior"]["multi_node_run_ids"])}`；',
        '- 唯一多节点运行失败，所以现有路线名称不能当成“DAG 已被充分测试”的证据；',
        '- 目前观察到的成本差异主要来自选模与提示链路，无法隔离出拆分本身的因果贡献。', '',
        '## 为什么低价路线的单位合格成本反而更高', '',
        '现有证据没有证明“拆分天然比直跑贵”。实际结果是：两条路由路线都降低了总 AFP，',
        '但合格任务数量下降得更快，所以 `AFP / accepted task` 反而升高。', '',
        '| 路线 | 全部任务 AFP | 相对 direct-strong | 合格任务 | 每个合格任务 AFP | 相对 direct-strong |',
        '| --- | ---: | ---: | ---: | ---: | ---: |',
    ]
    for arm, row in report['cost_analysis']['arms'].items():
        lines.append(
            f'| `{arm}` | {row["total_afp_all_tasks"]:.3f} | '
            f'{row["gross_afp_change_vs_direct_strong"]:+.1%} | {row["accepted_tasks"]}/12 | '
            f'{row["afp_per_accepted_task"]:.3f} | '
            f'{row["afp_per_accepted_change_vs_direct_strong"]:+.1%} |'
        )
    lines += [
        '',
        '`direct-or-dag` 总 AFP 比 `direct-strong` 少约 10%，但合格任务从 7 个降到 5 个，',
        '因此每个合格任务的成本高约 26%。`task-selector` 的总 AFP 也少约 11%，但只剩',
        '3 个合格任务，每个合格任务的成本高约 109%。费用劣势主要来自质量门槛的分母',
        '缩水，不是账面调用总额上升。', '',
        '### 费用口径（记账说明）', '',
        '| 路线 | 选路/规划/工作/合流 AFP | 两类评审 AFP | 评审占总 AFP |',
        '| --- | ---: | ---: | ---: |',
    ]
    for arm, row in report['cost_analysis']['arms'].items():
        lines.append(f'| `{arm}` | {row["routing_execution_afp"]:.3f} | '
                     f'{row["evaluation_afp"]:.3f} | {row["evaluation_share"]:.1%} |')
    lines += [
        '',
        '上表只用于避免把研究评审算成部署路由费用，不作为拆分优劣的结论。只看路由与生成',
        '调用，`direct-or-dag` 为 5.805 AFP，低于全程强模型的 19.835 AFP；但其中 35/36',
        '是单节点，节省来自 cheap/mid 选模，不能归因于 DAG。', '',
        '### 唯一真实 DAG 暴露出的成本机制', '',
        '唯一多节点运行 `decision-05-r3-direct-or-dag` 使用 2 个 cheap worker 和 1 个',
        'strong final。排除两类 judge 后，它的路由执行成本为 0.768 AFP；同题同次的',
        '`direct-strong` 为 0.584 AFP，真实 DAG 高 31.6%。增加的 0.185 AFP 来自：', '',
        '- selector + planner + 两个 worker：0.138 AFP；',
        '- strong final 本身比直跑多 0.047 AFP，因为合流输入从 691 token 增至 884 token；',
        '- 整条 DAG 的路由调用共处理 3,904 个输入加输出 token，直跑为 1,061，约为 3.7 倍。', '',
        '这说明该样本的 cheap worker 单价虽低，新增调用和重复上下文仍超过其节省。该 DAG',
        '与同题两个直跑结果最终都未通过，因此只能用于定位成本机制，不能估计平均收益或',
        '比较质量。', '',
        '### 成本不占优的机制', '',
        '1. **固定调用开销。** 拆分新增 selector、planner 和 final synthesis；节点很小或只有',
        '   一两个时，省下的模型单价不足以覆盖这些固定成本。',
        '2. **上下文重复。** 多个节点若各自读取完整任务与材料，输入 token 随节点数重复增长。',
        '3. **强模型合流。** cheap worker 后仍固定使用 strong final，会吞掉大部分局部节省。',
        '4. **质量损失。** 值、来源和跨节点约束在传递与合流时丢失，导致任务不合格；全部失败',
        '   调用仍进入成本分子，但不能增加 accepted task 分母。',
        '5. **拆分覆盖不足。** 35/36 次 `direct-or-dag` 实际是单节点，观察到的节省主要来自',
        '   cheap/mid 选模，不能归因给 DAG。', '',
        '### 可执行的解决方案', '',
        '1. 下一轮分成 `strong-direct`、`routed-direct`、`forced/frozen-DAG`、`direct-or-dag`',
        '   四条路线，分别识别选模收益、拆分收益和策略选择收益；报告实际模式，不用路线名称',
        '   代替真实 DAG 覆盖。',
        '2. 在拆分前计算净节省门槛：只有预计 worker 节省大于 selector + planner + final +',
        '   质量保障开销，并且任务存在可并行、可压缩的独立子问题时才拆分。',
        '3. 先修复质量分母：对 findings 做字段级值、来源和约束传播；用确定性校验器处理算术、',
        '   有向顺序、预算和引用，失败时局部修复，避免整条任务报废。',
        '4. 按风险自适应合流模型：低风险且结构化校验通过时用 cheap/mid 合流；只有高风险、',
        '   高难度或校验失败时升级 strong。',
        '5. 节点只接收所需材料切片和结构化上游字段，避免复制完整上下文；对重复任务模板缓存',
        '   规划结果，摊薄 planner 固定成本。',
        '6. 同时报告部署口径和研究口径：部署口径排除离线 research judge，研究口径保留全部',
        '   评审；核心指标继续使用质量达标后的成本，不能只比较原始 AFP。', '',
        '## 下一步', '',
        '1. 修复质量侧：对节点输出到最终 findings 做字段级来源传播；在交付前校验值、引用、',
        '   有向顺序、共享预算与正文一致性。',
        '2. 加强实验可观测性：记录 `direct-or-dag` 的选择理由、选择 direct/DAG 的概率与',
        '   实际节点数，并为下一轮设置最低多节点覆盖门槛。',
        '3. 用现有失败样本做零成本回放测试，先证明 30 个确定性失败和 11 个交付门禁失败',
        '   能被新约束拦截或修正。',
        '4. 真人抽查失败输出与门禁理由；通过后再冻结小规模针对性实验，暂不扩张 A4 隐私',
        '   付费对照。', '',
        '## 解释边界', '',
        '本报告是 12 个构造留出任务的事后诊断，不能推出业务总体规律。它用于决定下一轮',
        '工程修正与实验设计，不把任务重复当作独立样本，也不改变既有 AFP 指标口径。', '',
    ]
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--tasks', type=Path, required=True)
    parser.add_argument('--moa-reviews', type=Path, required=True)
    parser.add_argument('--final-analysis', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error('必须使用空输出目录')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    result = json.loads(args.results.read_text())
    tasks = json.loads(args.tasks.read_text())['tasks']
    records = json.loads(args.moa_reviews.read_text())['records']
    final_analysis = json.loads(args.final_analysis.read_text())
    report = analyze(result, tasks, records, final_analysis)
    report['provenance'] = {
        'results_sha256': file_digest(args.results),
        'tasks_sha256': file_digest(args.tasks),
        'moa_reviews_sha256': file_digest(args.moa_reviews),
        'final_analysis_sha256': file_digest(args.final_analysis),
        'analysis_implementation_sha256': file_digest(Path(__file__)),
    }
    (args.output_dir / 'analysis.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    (args.output_dir / 'README.md').write_text(markdown(report))
    (args.output_dir / 'artifact-index.json').write_text(json.dumps({
        path.name: file_digest(path) for path in sorted(args.output_dir.iterdir())
    }, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'arms': report['arms'], 'routing_behavior': report['routing_behavior']},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
