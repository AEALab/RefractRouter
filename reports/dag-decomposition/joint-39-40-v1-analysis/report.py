"""将冻结会话转成中文复核摘要；不重新选模或修改评分。"""
from collections import Counter
import json
import html
from pathlib import Path
import statistics

HERE=Path(__file__).resolve().parent
RAW=HERE.parent/'joint-39-40-v1-actual'


def main():
    r=json.loads((RAW/'session.json').read_text());assert r['status']!='started'
    audit=json.loads((HERE/'audit.json').read_text())
    tests=[x for x in r['runs'] if x.get('split')=='test']
    tasks={t['task_id']:t for t in r['config']['tasks']}
    lines=['# 联合研究 v1 实测与关闭条件','',
        '此报告仅覆盖分别编写的虚构封闭案例，不代表线上任务分布；长表格中的每行不算独立任务。',
        '风险为冻结契约的场景标签，未测量现实机构损失；输入规模与风险相互关联，不能据此分离风险的因果作用。',
        '所有判定依据冻结协议，质量失败、无可行路由和缺评审均保留，不根据留出成绩重新校准。','',
        f"批次状态：`{r['status']}`。计划测试 104 条，实际记录 {len(tests)} 条，交付通过 {sum(x['delivered'] for x in tests)} 条。",
        f"独立审计核对 {audit['indexed_files_verified']} 份原始文件、{audit['billed_calls']} 次已结算调用；未知用量 {len(audit['unknown_usage_calls'])} 次。",'']
    costs=audit['verified_billed_afp']
    lines += [f"已确认 AFP：生产 {costs['production']:.4f}，评审 {costs['evaluation']:.4f}，合计 {sum(costs.values()):.4f}。",
        'AFP 为订阅用量计量，不等于额外现金付费；未知用量保留预留，不能计为零。','',
        '## 材料、校准与交接','']
    for cell,g in r.get('material_reviews',{}).items():
        lines += [f"- {cell}：独立材料评审 {g['score']} 分，{'通过' if g['passed'] else '不通过'}。{g['rationale']}"]
    profile=r.get('node_profile',{})
    lines += ['',f"节点 profile 可用 {len(profile.get('candidates',[]))} 项，排除 {len(profile.get('exclusions',[]))} 项。",
        '可用项只接受至少三个独立校准任务；不足或层外能力不强制匹配。','']
    if 'direct_calibration' in r:
        for cell,selections in r['direct_calibration']['selections'].items():
            lines += [f"- 整任务 {cell}："+'；'.join(f"{method} = {value.get('selected_model') or '无可用模型'}" for method,value in selections.items())]
    handoff=json.loads((HERE/'handoff-audit.json').read_text())['rows']
    lines += ['',f"逐边核对实际下游请求，共验证 {sum(h['verified_edges'] for h in handoff)} 条被消费依赖，其中跨模型 {sum(h['cross_model_edges'] for h in handoff)} 条。",
        '交接核验指字段确实进入下游请求；不能单凭传参成功证明模型充分理解或使用了内容。最终交付单独评审。','',
        '| 校准任务 / 模型 | 固定参考下最终节点独立分 | 同模型完整 DAG 最终分 | 完整交付 |',
        '| --- | ---: | ---: | --- |']
    observations=r.get('observations',{}).get('observations',[])
    for row in r['runs']:
        if row.get('arm')!='cal-dag':continue
        mid=next(iter(row['assignments'].values()))
        final=tasks[row['task_id']]['plan']['final_node_id']
        obs=next((x for x in observations if x['task_id']==row['task_id'] and x['model_id']==mid and x['node_id']==final),None)
        score=obs.get('evaluation',{}).get('score') if obs else None
        lines += [f"| {row['task_id']} / {mid} | {score} | {row['score']} | {'通过' if row['delivered'] else '不通过'} |"]
    lines += ['', '节点探测使用冻结参考上游，组合使用实际上游。上表不同调用的差异还包含生成随机性，不能单独归因于交接。', '',
        '## 全计划分母与主比较','',
        '下表均值仅描述已有评分或已执行记录，不替代共同配对结论；缺评审不补零。','',
        '| 条件 | 计划 | 记录 | 通过 | 有效评分数 / 均分 | 完整运行 AFP | 已记录尝试墙钟均值（秒） |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for arm in dict.fromkeys(x['arm'] for x in r['planned_runs']):
        rows=[x for x in tests if x['arm']==arm];graded=[x['score'] for x in rows if x['score'] is not None]
        complete=len(rows)==8 and all(x['deployment_cost'] is not None for x in rows)
        cost=f"{sum(x['deployment_cost'] for x in rows):.4f}" if complete else '未知 / 未完成'
        score=f'{len(graded)} / {statistics.mean(graded):.2f}' if graded else '0 / —'
        wall=f"{statistics.mean(x['wall_time_ms'] for x in rows)/1000:.2f}" if rows else '—'
        lines += [f"| {arm} | 8 | {len(rows)} | {sum(x['delivered'] for x in rows)} | {score} | {cost} | {wall} |"]
    for issue,analysis in r['analysis']['issues'].items():
        lines += ['',f'### #{issue} 主比较','']
        for cell,group in analysis['groups'].items():
            for c in group['primary_comparisons']:
                lines += [f"- {cell}，{c['left']} 对 {c['right']}：{c['paired_repeats']}/{c['expected_pairs']} 完整配对，"
                    f"{c['task_clusters']} 个任务；判定 `{c['benefit_verdict']}`。"]
                for name,m in c['metrics'].items():
                    lines += [f"  {name}：均值 {m['mean_delta']}，97.5% 区间 {m['interval_97_5']}。"]
    lines += ['', '质量差为左减右；节省比例为 1−左/右，时延比为左/右。',
        '三个单节点短任务中，同一方法的节点路由与同图单模型路线实际选模相同；整任务直接回答 A/B 也都选择 M3。',
        '这些重复调用仍有生成与评审波动，不能把分数差异都归因于选模策略。只有调查任务的节点路线形成不同于全图单模型的异构分配。',
        '确认性门槛为全部计划配对交付、质量下界 ≥ −3 分、费用节省下界 ≥ 20%、时延比上界 ≤ 1.1。',
        '分层样本仅四个，区间为目的性选题条件内的近似描述，不报告总体 p95。辅助比较见原始 analysis。','',
        '## 规划、失败与实际时序','']
    statuses=Counter(x['status'] for x in tests)
    lines += [f"测试状态计数：`{dict(statuses)}`。",
        '测试失败数不等于规划请求失败数；缓存计划失败会传播到复用条件，但没有重新发起规划。','']
    plans=[x for x in tests if x['arm'].startswith('auto-cold')]+r['plan_setups']
    counts=Counter(len(x['plan']['nodes']) for x in plans if x.get('plan'))
    lines += [f"自动冷计划与缓存设置共 {len(plans)} 条；结构合法计划节点数分布：`{dict(counts)}`。",
        f"有效语义评分 {sum('plan_review' in x for x in plans)} 条，通过 {sum(x.get('plan_review',{}).get('passed',False) for x in plans)} 条。",
        '缺失语义评审与语义不通过分开保留；缓存复用原评分不算新的独立计划评分。','']
    support=[]
    for row in plans:
        for n in row.get('plan',{}).get('nodes',[]):
            f=n['contract']['capability']
            matching=[p['model_id'] for p in profile.get('candidates',[]) if p['node_type']==n['node_type']
                and p['difficulty']==f['difficulty'] and p['risk']==f['risk']
                and p['input_min_tokens']<=f['input_budget_tokens']<p['input_max_tokens']]
            support.append({'plan_id':row.get('run_id',row.get('cache_id')),'node_id':n['node_id'],
                'node_type':n['node_type'],'capability':f,'calibrated_models_in_same_stratum':matching})
    (HERE/'automatic-capability-coverage.json').write_text(json.dumps(support,ensure_ascii=False,indent=2)+'\n')
    lines += [f"结构合法自动计划中，共 {sum(not x['calibrated_models_in_same_stratum'] for x in support)} 个节点没有同能力层的校准模型。",
        '详见 [automatic-capability-coverage.json](automatic-capability-coverage.json)。缺少匹配层说明准入证据不足，不能直接推断模型在该层能力差。','']
    timing=[]
    for x in tests:
        start=x['started_ms'];pf=x.get('planning_finished_ms');sf=x.get('structural_check_finished_ms');pr=x.get('plan_review_finished_ms')
        rf=x.get('routing_finished_ms');ef=x.get('execution_finished_ms')
        timing.append({'run_id':x['run_id'],'wall_time_ms':x['wall_time_ms'],
            'planning_ms':pf-start if pf is not None else 0 if x['mode']!='auto-cold' else None,
            'structural_check_ms':sf-pf if sf is not None and pf is not None else None,
            'plan_review_ms':pr-sf if pr is not None and sf is not None else None,
            'routing_and_persist_ms':rf-(pr or pf or start) if rf is not None else None,
            'execution_and_queue_ms':ef-rf if ef is not None and rf is not None else None,
            'final_review_and_persist_ms':x['finished_ms']-ef if ef is not None else None,
            'execution':x.get('execution'), 'nodes':[{k:v for k,v in n.items() if k not in ('output',)} for n in x['nodes']]})
    (HERE/'timing.json').write_text(json.dumps(timing,ensure_ascii=False,indent=2)+'\n')
    lines += ['实际阶段与节点排队 / 重叠记录见 [timing.json](timing.json)。失败前的部分阶段不补成完整执行。','',
        '## 完整成本','', '| 阶段 | AFP |','| --- | ---: |']
    for key,value in r['analysis']['cost_phases'].items():lines += [f'| {key} | {value:.4f} |']
    lines += ['', '| 分析范围 | 运行 AFP | 共享设置 AFP | 首次合计 AFP |', '| --- | ---: | ---: | ---: |']
    for issue,analysis in r['analysis']['issues'].items():
        lines += [f"| #{issue} | {analysis['runtime_cost']} | {analysis['setup_cost']} | {analysis['first_use_cost']} |"]
    allocation={'shared_material_node_and_handoff':0.,'issue39_whole_dag_calibration':0.,'issue40_direct_and_cache_setup':0.}
    for c in r['calls']:
        label=c['label']
        key=('shared_material_node_and_handoff' if label.startswith(('material-review:','probe:','handoff-')) else
            'issue39_whole_dag_calibration' if label.startswith('cal-dag-') else
            'issue40_direct_and_cache_setup' if label.startswith(('cal-direct-','setup:')) else None)
        if key and c['status']=='billed':allocation[key]+=c['charged']
    lines += ['', '上述首次合计使用联合批次全部设置费用，包含另一项研究专用开销，是完整实验视图，不是单项部署报价；两项设置不能相加。',
        '以下按原始调用用途拆解已确认设置费用，只作费用归属说明，不改变冻结的主比较或选择：','',
        '| 设置用途 | 已确认 AFP |','| --- | ---: |']
    for key,value in allocation.items():lines += [f'| {key} | {value:.4f} |']
    lines += ['',
        '| 缓存 | 一次设置 AFP | 复用执行 AFP | 该计划首次使用 AFP |', '| --- | ---: | ---: | ---: |']
    for setup in r['plan_setups']:
        trial=next((x for x in tests if x.get('cache_id')==setup['cache_id']),None)
        cost=trial.get('deployment_cost') if trial else None
        total=cost+setup['deployment_cost'] if cost is not None and setup['deployment_cost'] is not None else None
        lines += [f"| {setup['cache_id']} | {setup['deployment_cost']} | {cost} | {total} |"]
    lines += ['',r['analysis']['runtime_review_policy'],r['analysis']['setup_accounting'],
        '本地选模计算无模型 AFP；校准结束至首个缓存设置的间隔可作包含持久化的准备时间上界，不冒充纯 CPU 用时。',
        '没有调用 DSH 外层，费用为零。保留生产与评审原始分类，便于按其他部署口径另行分析。','',
        '## 人工复核与关闭状态','',
        '结项判断见[结项评估](结项评估.md)。真人复核未完成，可先阅读[按题目整理的阅读版](human-review.md)。',
        '[复核包](human-review-packet.json)按事前规则抽样，隐藏模型、路线和自动分数；',
        '映射另存，评审者须填写身份、日期、判断与理由，不能用模型评审代替。',
        '本报告不自动关闭 #39 或 #40：须分别核对采集完整性、合并交付及 #40 真人复核，再回填 #1，关联 #22、#8。']
    (HERE/'README.md').write_text('\n'.join(lines)+'\n')
    packet=json.loads((HERE/'human-review-packet.json').read_text())
    review=['# 真人复核阅读版','',
        '本页按题目集中材料，保留随机复核编号。阅读后在 JSON 复核包填写，或按编号提供判断与理由。',
        '模型、路线和自动分数已隐藏；节点命名与风格仍可能透露生成方式。空白项须由真人填写。','']
    for i,task in enumerate(dict.fromkeys(x['task'] for x in packet['rows']),1):
        samples=[x for x in packet['rows'] if x['task']==task]
        review += [f'## 题目 {i}','', '<details><summary>查看原始题目与材料</summary>',
            '<pre>'+html.escape(task)+'</pre>','</details>','',
            '**原始验收：** '+'；'.join(samples[0]['criteria']),'',
            '<details><summary>查看冻结参考（长材料已独立重算）</summary>',
            '<pre>'+html.escape(samples[0]['reference_for_review'])+'</pre>','</details>','']
        for row in samples:
            review += [f"### {row['review_id']}",'']
            if row['plan']:
                review += ['| 节点 | 类型 | 上游 | 职责 |','| --- | --- | --- | --- |']
                for node in row['plan']['nodes']:
                    clean=lambda v:str(v).replace('|','／').replace('\n',' ')
                    review += ['| '+' | '.join(map(clean,(node['node_id'],node['node_type'],','.join(node['parents']) or '无',node['contract']['objective'])))+' |']
            else:
                review += ['没有结构合法的计划；仍需记录缺失 / 失败及其理由。']
            details={'plan':row['plan'],'raw_plan_if_unparsed':row['raw_plan_if_unparsed'],
                'planner_response_status':row['planner_response_status'],
                'execution_trace':row['execution_trace'],'final_output':row['final_output']}
            review += ['', '<details><summary>查看完整契约、节点输出和最终交付</summary>',
                '<pre>'+html.escape(json.dumps(details,ensure_ascii=False,indent=2))+'</pre>','</details>','',
                '待填：拆分适当、计划覆盖原始要求、依赖正确、并行适当、交接风险、实际执行观察、计划总体判断、具体理由。','']
    (HERE/'human-review.md').write_text('\n'.join(review)+'\n')


if __name__=='__main__':main()
