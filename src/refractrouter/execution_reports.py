"""执行方式对照的简体中文报告；只展示已有统计，不重新计算业务指标。"""


def display(value):
    return '不可用' if value is None else str(value)


def baseline_markdown(summary):
    lines = ['# 执行方式对照汇总', '',
             '质量、成本和延迟使用相同的成功且完成独立评审的任务／轮次集合。',
             '失败与缺失评审不会被静默丢弃，已发生的费用仍计入总账。', '',
             '| 策略 | 质量均值 | 路线费用均值（AFP） | 延迟中位数／95分位（毫秒） | 成功率 | 评审覆盖率 |',
             '|---|---:|---:|---:|---:|---:|']
    for name, row in summary.items():
        lines.append(f"| `{name}` | {display(row['quality_mean'])} | {display(row['production_cost_mean'])} | "
                     f"{display(row['critical_path_p50_ms'])}／{display(row['critical_path_p95_ms'])} | "
                     f"{row['success_rate']:.2%} | {row['judge_coverage']:.2%} |")
    lines.extend(['', '## 比较样本', ''])
    for name, row in summary.items():
        lines.append(f"- `{name}`：有效 {row['comparison_runs']}／预期 {row['expected_runs']}。")
        for block in row['cohort']['excluded']:
            lines.append(f"  排除 {block['task_id']}／{block['repeat']}；原因代码：{', '.join(block['reasons'])}。")
    return '\n'.join(lines) + '\n'


def comparisons_markdown(report):
    lines = ['# 配对策略比较', '', report['interpretation'], '',
             '| 对照 | 有效／排除对数 | 质量差均值 | 费用差均值（AFP） | 延迟差均值（毫秒） |',
             '|---|---:|---:|---:|---:|']
    for name, row in report['summaries'].items():
        lines.append(f"| {name.replace(' vs ', ' 对比 ')} | {row['pairs']}／{row['excluded_pairs']} | "
                     f"{display(row['quality_delta_mean'])} | {display(row['cost_delta_mean'])} | "
                     f"{display(row['latency_delta_ms_mean'])} |")
    lines.extend(['', '正的质量差表示前者质量更高；负的费用差或延迟差表示前者更省或更快。',
                  '路线费用不含选路探针和评审费用，实验总开销另计。', '', '## 同一配对集合', ''])
    for name, row in report['summaries'].items():
        blocks = '、'.join(f"{b['task_id']}／{b['repeat']}" for b in row['included_blocks']) or '无'
        lines.append(f"- {name.replace(' vs ', ' 对比 ')}：{blocks}。")
        for block in row['excluded_blocks']:
            lines.append(f"  排除 {block['task_id']}／{block['repeat']}；原因代码：{', '.join(block['reasons'])}。")
    return '\n'.join(lines) + '\n'


def failure_taxonomy_markdown(failures):
    lines = ['# 失败分类', '', '| 失败类型代码 | 记录数 |', '|---|---:|']
    lines += [f'| `{name}` | {count} |' for name, count in failures.items()] or ['| 无 | 0 |']
    return '\n'.join(lines) + '\n'


def node_matrix_markdown(rows):
    lines = ['# 节点质量矩阵', '', '分数来自独立语义评审，并受确定性契约检查约束；未评审不等于零分。', '',
             '| 轮次 | 节点 | 模型 | 评估状态 | 质量分 | 入选 |', '|---:|---|---|---|---:|---|']
    states = {'judged': '已评审', 'contract-rejected': '契约拒绝', 'unavailable': '不可用'}
    for row in rows:
        lines.append(f"| {row['repeat']} | `{row['node_id']}` | {row['api_model'] or row['model_id']} | "
                     f"{states.get(row['evaluation_state'], row['evaluation_state'])} | "
                     f"{display(row['evaluation']['final_score'])} | {'是' if row['selected'] else '否'} |")
    return '\n'.join(lines) + '\n'
