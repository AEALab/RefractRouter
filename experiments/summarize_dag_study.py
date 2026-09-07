"""从完成或停止的冻结产物生成中文报告；不修改原始证据、不调用模型。"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import statistics


def summarize_study(directory):
    root=Path(directory).resolve()
    index=json.loads((root/'artifact-index.json').read_text())
    for relative,digest in index.items():
        source=(root/relative).resolve()
        if not source.is_relative_to(root) or hashlib.sha256(source.read_bytes()).hexdigest()!=digest:
            raise ValueError('artifact index mismatch')
    result=json.loads((root/'study-result.json').read_text())
    protocol=json.loads((root/'protocol.json').read_text())
    if result['status'] not in ('failed','simulated','completed'):
        raise ValueError('study is still running')
    tasks=[t for t in protocol['tasks'] if t['split']=='test']
    expected={(t['task_id'],repeat,method) for t in tasks
              for repeat in range(1,protocol['test_repeats']+1) for method in protocol['methods']}
    tests=[r for r in result['runs'] if r['split']=='test']
    keys=[(r['task_id'],r['repeat'],r['method']) for r in tests]
    if len(keys)!=len(set(keys)) or not set(keys)<=expected:
        raise ValueError('unexpected or duplicate test result')
    attempted = {}
    for relative in index:
        parts = relative.split('/')
        if len(parts) != 2 or parts[1] != 'result.json':
            continue
        fields = parts[0].split('--')
        if len(fields) < 3 or not fields[1].isdigit():
            continue
        key = (fields[0], int(fields[1]), fields[2])
        if key in expected:
            if key in attempted:
                raise ValueError('duplicate attempted test result')
            attempted[key] = json.loads((root/relative).read_text())
    def percentile(values,q):
        values=sorted(values)
        pos=(len(values)-1)*q
        low=int(pos); high=min(low+1,len(values)-1)
        return values[low]+(values[high]-values[low])*(pos-low)
    groups=[]
    for method in protocol['methods']:
        rows=[r for r in tests if r['method']==method]
        heterogeneous=0
        for row in rows:
            if row['result_path'] not in index:
                raise ValueError('unindexed run result')
            artifact=json.loads((root/row['result_path']).read_text())
            heterogeneous+=len(set(artifact['assignments'].values()))>1
        groups.append({'method':method,'planned':len(tasks)*protocol['test_repeats'],
            'failed':sum(a.get('status') == 'failed' for k,a in attempted.items() if k[2] == method),
            'graded':len(rows),'passed':sum(r['passed'] for r in rows),'heterogeneous':heterogeneous,
            'quality_mean':statistics.mean(r['score'] for r in rows) if rows else None,
            'deployment_cost_mean':statistics.mean(r['deployment_cost'] for r in rows) if rows else None,
            'wall_time_p50_ms':percentile([r['wall_time_ms'] for r in rows],.5) if rows else None,
            'wall_time_p95_ms':percentile([r['wall_time_ms'] for r in rows],.95) if rows else None})
    # 全量账本包括失败调用；不能用成功任务均值替代总消耗。
    costs={category:{'confirmed':sum(c['charged'] for c in result['calls'] if c['category']==category and c['status']=='billed'),
        'unconfirmed':sum(c['charged'] for c in result['calls'] if c['category']==category and c['status'] in ('reserved','unknown-usage'))}
        for category in ('production','evaluation')}
    complete=(set(keys)==expected and result['status'] in ('completed','simulated'))
    comparisons=(result.get('comparison') or {}).get('comparisons',[]) if complete else []
    lines=['# '+('模拟' if result['simulated'] else '真实')+' DAG 对照结果','',
        f"运行状态：`{result['status']}`。已取得评分的测试运行 {len(tests)}/{len(expected)}；已评分的独立测试任务 {len({r['task_id'] for r in tests})}/{len(tasks)} 个。",
        f"已保存结果的测试运行 {len(attempted)} 次，其中执行失败 {sum(a.get('status') == 'failed' for a in attempted.values())} 次。",
        '未完成或模拟数据不能用于宣称真实路由收益。','',
        '## 测试完整性与描述性指标','',
        '| 方法 | 已评分/计划 | 执行失败 | 验收通过 | 异构运行 | 平均质量 | 平均部署 AFP | 墙钟 p50 毫秒 | 墙钟 p95 毫秒 |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    def display(value):return '不可用' if value is None else f'{value:.4f}'
    for g in groups:
        lines.append(f"| {g['method']} | {g['graded']}/{g['planned']} | {g['failed']} | {g['passed']} | {g['heterogeneous']} | "+' | '.join(display(g[k]) for k in ('quality_mean','deployment_cost_mean','wall_time_p50_ms','wall_time_p95_ms'))+' |')
    lines+=['','这些均值仅描述各组已评分样本；若样本不完整，不得跨行直接比较。部署成本包括节点和最终评审；',
            '小样本 p95 使用线性插值，只是本批样本的描述，不构成时延 SLA。','',
            '## 同样本配对比较','']
    if not comparisons:
        lines+=['配对证据不足，未输出路由收益判断。']
    for c in comparisons:
        intervals=c['task_cluster_bootstrap_interval_95']
        signal=c['exploratory_signal']
        label='模拟，不判定' if result['simulated'] else ('达到探索性门槛' if signal else '未达到探索性门槛')
        lines+=[f"- `{c['candidate']}` 对 `{c['baseline']}`：{len(c['pairs'])} 对，{label}。",
            f"  质量差 95% 区间 {intervals['quality_delta']}；成本节省比例区间 {intervals['cost_saving']}；时延比区间 {intervals['latency_ratio']}。"]
    lines+=['','区间按任务聚类重采样；同一任务的重复不是独立任务。这里只有 3 个任务，结果不支持泛化证明。','',
            '## 全量用量账本','',
            '| 类别 | 已确认 AFP 估算 | 未确认预留 AFP |','|---|---:|---:|']
    for category,name in [('production','生产'),('evaluation','评审')]:
        lines.append(f"| {name} | {costs[category]['confirmed']:.8f} | {costs[category]['unconfirmed']:.8f} |")
    lines+=['','AFP 按服务返回用量和冻结费率估算，用于比较与记账；订阅制下不应直接解释为新增现金账单。',
            '失败调用保留在全量账本中，缺失质量不填零；本表不含其他修复轮次或 DSH 外层用量。','',
            '## 证据与边界','',
            f"协议 SHA-256：`{result['preflight']['protocol_sha256']}`。原始产物哈希已逐项核对。",
            f"原始问题状态：`{json.dumps(result['issues'],ensure_ascii=False)}`。",
            '固定人工 DAG 不验证自动规划器的拆分质量；实际任务入口需另看 DSH 会话和核心产物。','']
    lines+=['校准单模型基线按本任务族的校准质量优先选择；本轮没有对单模型路由进行对称的 A/B 优化。',
            '因此只能判断相对这些冻结基线的结果，不能直接宣称优于成本或加权评分最优的整任务路由。',
            '当节点 A/B 的实际分配全部为同一模型时，其差异也不能归因于异构交接。','']
    return '\n'.join(lines)


def main():
    parser=argparse.ArgumentParser(description='校验原始证据并生成中文 DAG 对照报告')
    parser.add_argument('directory',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.resolve().is_relative_to(args.directory.resolve()):
        parser.error('报告必须放在原始运行目录之外')
    report=summarize_study(args.directory)
    with args.output.open('x') as stream:stream.write(report)


if __name__=='__main__':
    main()
