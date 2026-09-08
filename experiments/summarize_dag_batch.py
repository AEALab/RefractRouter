"""独立样本实验的交付率、失败与共同有效样本报告；不调用模型。"""
from collections import Counter
import json


def summarize_batch(root, result, protocol):
    tests=[r for r in result['runs'] if r['split']=='test']
    handoffs=[r for r in result['runs'] if r['split']=='handoff']
    comp=result['comparison']
    calls=result['calls']
    # 兼容旧解析器丢失 usage 缺失信息的归档：异常零值不能仅凭 billed 状态确认费用。
    suspect=[c for c in calls if c['status']=='billed' and
             (c.get('input_tokens',0)<=0 or c.get('output_tokens',0)<=0)]
    suspect_labels={c['label'] for c in suspect}
    unknown=[c for c in calls if c['status'] in ('reserved','unknown-usage') or c['label'] in suspect_labels]
    lines=['# 独立样本 DAG 实验结果','',
        f"状态：`{result['status']}`；模拟：`{result['simulated']}`。留出结果记录 {len(tests)}/72。",
        '实验采集完成不表示节点路由有收益，也不表示所有调用成功。','',
        '## 六种指定交接','',
        '| 排列 | 状态 | 最终质量 | 交付通过 |','|---|---|---:|---|']
    for r in handoffs:
        lines.append(f"| {r['repeat']} | {r['status']} | {r['score'] if r['score'] is not None else '不可用'} | {r['delivered']} |")
    lines+=['','指定排列只验证组合，不作为自动路由收益。','',
        '## 全部计划样本的交付结果','',
        '| 方法 | 记录/计划 | 交付/计划 | 已评分 | 状态分布 | 全量部署 AFP |',
        '|---|---:|---:|---:|---|---:|']
    for g in comp['groups']:
        prefixes=tuple(r['result_path'].split('/')[0]+':' for r in tests if r['method']==g['method'])
        uncertain=any(c['label'].startswith(prefixes) for c in unknown)
        cost='存在未确认用量' if uncertain else f"{g['total_deployment_cost']:.6f}"
        lines.append(f"| {g['method']} | {g['recorded']}/{g['planned']} | {g['delivered']}/{g['planned']} | {g['graded']} | {json.dumps(g['outcomes'],ensure_ascii=False)} | {cost} |")
    lines+=['','交付必须有有效的独立评审、逐项通过且总分达到冻结质量底线。未评分保持缺失；',
            '无可行路线按未交付计入全部计划样本，不因零调用而宣称节省成本。',
            '若实验中断，未运行的样本单列为未观察，不能当作真实失败；上表为进度而非最终成功率。','',
            '## 共同已评分样本的条件比较','']
    for c in comp['comparisons']:
        label=('存在计量审计异常，仅作描述，不作严格验收' if suspect else
               '模拟或未完成，不判定' if c['exploratory_signal'] is None else
               ('达到探索性门槛' if c['exploratory_signal'] else '未达到探索性门槛'))
        lines += [f"- {c['candidate']} 对 {c['baseline']}：交付结果 {len(c['outcome_pairs'])}/9 对，共同评分 {len(c['joint_graded_pairs'])}/9 对；{label}。",
                  f"  条件 95% 区间：`{json.dumps(c['conditional_interval_95'],ensure_ascii=False)}`。"]
    lines+=['','质量差、成本节省与时延比采用相同的共同评分样本。失败并非随机缺失，条件结果有选择偏差；',
            '冻结的正收益门槛还要求相关两组全部样本交付通过。没有达到门槛也可以完成实验。',
            '区间按任务聚类，三个独立任务仅用于探索；同一 DAG 单模型 A/B 不等于一次调用整任务优化。','',
            '## 全量调用与费用','']
    lines += [f"调用数 {len(calls)}；状态：`{json.dumps(dict(Counter(c['status'] for c in calls)),ensure_ascii=False)}`。"]
    if suspect:
        lines += [f'审计更正：{len(suspect)} 次 billed 记录存在异常零用量，不能确认免费；原始记录不修改。',
                  '旧执行器可能未触发未知用量停止规则，不能据其 completed 状态宣布严格协议验收通过。']
    for category,title in [('production','生产'),('evaluation','评审')]:
        confirmed=sum(c['charged'] for c in calls if c['category']==category and c['status']=='billed' and c['label'] not in suspect_labels)
        reserved=sum(c['reserved'] if c['label'] in suspect_labels else c['charged'] for c in unknown if c['category']==category)
        lines.append(f'- {title}已确认 AFP 估算 {confirmed:.8f}；未知用量预留 {reserved:.8f}。')
    lines+=['','包含失败、校准、探针、交接与留出调用；订阅比较记账不是新增现金账单。','',
            '## 协议与限制','',
            f"冻结协议 SHA-256：`{result['preflight']['protocol_sha256']}`。原始索引已核对。",
            f"整批停止问题：`{json.dumps(result['issues'],ensure_ascii=False)}`。",
            '探针共用历史校准任务中预先冻结的上游字段，既不是新留出输出，也不代表任意上游分布。',
            '分层有任一已知契约/语义失败或不可用评审即排除；不补造预测或强制产生混合路线。',
            '固定人工 DAG 不检验自动规划器；历史失败不改判，零重试，不清洗模型原始输出。','']
    return '\n'.join(lines)
