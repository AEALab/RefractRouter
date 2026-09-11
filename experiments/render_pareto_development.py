"""绘制完整开发样本的资源点与阶段拆账；质量未确认时不画合格前沿。"""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    report = json.loads(args.analysis.read_text())
    heading = '模拟排版检查｜' if report['simulated'] else ''
    for name in ('PingFang SC', 'Heiti TC', 'Heiti SC', 'Noto Sans CJK SC', 'Arial Unicode MS'):
        try:
            path = font_manager.findfont(name, fallback_to_default=False)
            plt.rcParams['font.family'] = font_manager.FontProperties(fname=path).get_name()
            break
        except ValueError: continue
    plt.rcParams.update({'svg.fonttype': 'path', 'axes.unicode_minus': False, 'font.size': 10})
    arms = [a for a, r in report['summaries'].items() if r['complete']]
    def save(fig, name):
        for extension in ('png', 'svg'):
            fig.savefig(args.output_dir / f'{name}.{extension}', dpi=170, bbox_inches='tight')
        plt.close(fig)
    fig, (ax, legend) = plt.subplots(1, 2, figsize=(13, 6), gridspec_kw={'width_ratios': [1.2, 1]})
    for i, arm in enumerate(arms):
        row = report['summaries'][arm]
        ax.scatter(row['mean_online_ms']/1000, row['mean_online_afp'], s=100,
                   facecolors='none', edgecolors=plt.cm.tab10(i % 10), linewidths=2)
        ax.annotate(str(i+1), (row['mean_online_ms']/1000, row['mean_online_afp']), xytext=(6, 5), textcoords='offset points')
        legend.text(0, 1-i*.087, f"{i+1}. {arm}\n    字段检查 {row['fields'].get('pass', 0)}/{row['planned_runs']}；真人质量未确认", va='top', fontsize=10)
    ax.set(xlabel='平均在线等待时间（秒）', ylabel='平均在线 AFP', title='完整预定样本的资源开销')
    ax.grid(alpha=.2); legend.axis('off')
    fig.suptitle(heading + '开发诊断：这些点尚不构成质量合格的 Pareto 前沿', fontsize=15)
    fig.text(.08, .01, '含规划、执行、汇总、交付评审与失败；空心点表示缺真人质量确认。构造微任务不能代表业务总体。', fontsize=10)
    fig.tight_layout(rect=(0, .05, 1, .95)); save(fig, 'resource-points')
    fig, (time_ax, cost_ax) = plt.subplots(1, 2, figsize=(14, 6), sharey=True)
    y = list(range(len(arms))); left = [0.] * len(arms)
    for field, label in [('planning_ms','规划/选择与准备'), ('execution_ms','节点执行及汇总'), ('delivery_ms','解析及交付评审')]:
        values = [report['summaries'][a]['mean_'+field]/1000 for a in arms]
        time_ax.barh(y, values, left=left, label=label)
        left = [a+b for a,b in zip(left,values)]
    by_run = {r['run_id']: r['arm'] for r in report['rows']}; left = [0.] * len(arms)
    for stage, label in [('selector','选路'),('planner','规划'),('worker','中间节点'),('final','最终汇总'),('delivery-judge','交付评审')]:
        values = [sum(c['actual_afp'] for c in report['call_table'] if c['actual_afp'] is not None and c['run_id'] is not None
                      and by_run[c['run_id']]==arm and c['stage']==stage) / report['summaries'][arm]['planned_runs'] for arm in arms]
        cost_ax.barh(y, values, left=left, label=label)
        left = [a+b for a,b in zip(left,values)]
    time_ax.set_yticks(y, arms); time_ax.invert_yaxis()
    time_ax.set(xlabel='每次在线秒数', title='连续阶段墙钟拆分')
    cost_ax.set(xlabel='每次在线 AFP', title='实际调用费用拆分')
    for ax in (time_ax,cost_ax): ax.legend(loc='upper center', bbox_to_anchor=(.5,-.13), ncol=2, fontsize=9)
    fig.suptitle(heading + '费用与等待时间分别记账，研究评审另列', fontsize=15)
    fig.tight_layout(); save(fig, 'phase-accounting')
    metadata = {'matplotlib': matplotlib.__version__, 'simulated': report['simulated'], 'input_sha256': hashlib.sha256(args.analysis.read_bytes()).hexdigest(),
                'quality_frontier_plotted': False, 'scope': '开发资源诊断，未确认可接受质量'}
    (args.output_dir/'provenance.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
    (args.output_dir/'artifact-index.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(args.output_dir.iterdir())},indent=2)+'\n')


if __name__ == '__main__':
    main()
