"""为 #39/#40 编写有明确来源与边界的封闭场景；不复用历史留出。"""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from refractrouter.dag_study import implementation_fingerprint
from refractrouter.manifest import load_model_manifest
from refractrouter.research_protocol import digest, material_digest

ROOT = Path(__file__).resolve().parents[1]

# 每个场景单独定义问题及材料。表格行是同一个来源包内部的数据，不计作独立任务。
CASES = [
 ('cal_workshop', 'calibration', 'small', 'parallel', '图书馆活动排程',
  'L1：阅览室可用周二14至16时、周四14至17时，最多20人。L2：修复讲座需连续2小时及投影，报名18人。'
  'L3：摄影工作坊需连续3小时，报名24人，可分为两场且每场需3小时。L4：投影只在周二可用，不能延长开馆时间。',
  '分别核对时间与设备、容量与分场条件，形成可以执行及无法执行的安排；不要虚构额外场地。',
  '讲座可周二14至16时；摄影每场3小时，周四只容一场且超过20人不能单场完成，当前资源不能覆盖24人。'),
 ('cal_catalog', 'calibration', 'small', 'serial', '数据目录去重',
  'D1：记录a：来源X，版本1，样本100；记录b：来源X，版本2，样本120，明确替代版本1。'
  'D2：记录c：来源Y，样本80，其中30个样本与X版本2重叠。D3：内部规则只采用各来源最新版；'
  '允许按已知重叠计算去重总量，未知重叠不得推定为零。',
  '先决定保留哪些记录，再计算已知去重规模，解释删除旧版的依据及未知重叠的限制。',
  '保留b和c、排除a；已知并集120+80-30=170，不能加上旧版100，也不能扩展到其他未给来源。'),
 ('cal_recruit', 'calibration', 'small', 'coupled', '访谈招募审核',
  'R1：已报名36人，20人可线下、16人只能远程。R2：两种方式各有12个名额，剩余报名者可候补。'
  'R3：研究目标至少10位远程及10位线下，不允许为了满额改变研究目标。R4：名单只用匿名编号，'
  '待联系表由负责人本地保管，不应贴到公开报告；材料没有给出随机抽样或同意确认记录。',
  '形成名额分配与候补方案，核对能否满足目标，并写出匿名化与未核实前提。',
  '可线下12、远程12，总24；线下候补8、远程候补4；满足各至少10，但不能声称已随机抽样或取得同意。'),
 ('cal_transit', 'calibration', 'large', 'parallel', '校区接驳需求复核',
  'T1：每条记录是独立的一班需求，不是已上车人数。T2：供给容量固定，需求超出部分记为未满足需求。'
  'T3：不同线路可分别核验；不得把需求超过容量描述成车辆实际超载，也没有延误原因证据。',
  '汇总全部班次需求、容量及未满足需求，按线路列结果，再说明数据不能回答的运营问题。', ''),
 ('cal_sensor', 'calibration', 'large', 'serial', '实验环境测量质控',
  'Q1：内部质控区间为18至24摄氏度，端点合格。Q2：只按记录值判定，不推断设备故障原因。'
  'Q3：先汇总异常数量及分组分布，再判断是否满足至少90%记录合格的批次门槛；不能删除异常重算。',
  '逐组汇总合格与异常记录，计算整批合格比例，给出批次判断及不可推断的事项。', ''),
 ('cal_archive', 'calibration', 'large', 'handoff', '档案保留期限盘点',
  'A1：这是虚构机构的内部保留规则，不是法律意见。A类保留30天，B类90天，C类365天。'
  'A2：记录年龄严格大于期限且未锁定才可列入待审批清单。A3：超过期限不等于已经删除，'
  '任何锁定记录均不得列为可清理；输出只用匿名编号，不声称实施删除。',
  '按类别汇总总数、锁定数及符合待审批条件的数量，核对边界并给出审批建议，不执行外部动作。', ''),
 ('test_notice', 'test', 'small', 'short', '会议通知压缩',
  'N1：原通知：材料核对完成后，协调员应在下周三上午十点前将六份议程草稿交给会务组；'
  '若材料仍有冲突，应先标明冲突来源，并在同一截止时间提交待确认版本。',
  '改写成一段更简洁的通知，保留角色、数量、截止时间与两个条件分支，不增加理由或分析章节。',
  '必须保留协调员、六份、下周三上午十点前、会务组；核对完成提交草稿，有冲突标明来源并按时交待确认版本。'),
 ('test_minutes', 'test', 'small', 'oversplit', '会议行动项整理',
  'M1：周一例会决定：设备组负责在周五前给出检查清单。M2：运营组只负责汇总现场反馈，'
  '完成日期尚未确定。M3：某成员建议周三试运行，但会议未表决，不能列成已批准决定。',
  '仅输出一张简短行动项表和一条待确认事项；区分决定与建议，不把未知期限补成周五。',
  '设备组检查清单周五前；运营组现场反馈汇总期限待确认；周三试运行只是未表决建议。'),
 ('test_grant', 'test', 'small', 'coupled', '小型研究方案筛选',
  'G1：项目必须六周内完成、支出不超过40单位，并向所有参与者提供远程途径。'
  'G2：方案甲：五周、38单位、仅线下；方案乙：六周、40单位、提供远程；'
  '方案丙：四周、45单位、提供远程。G3：甲声称改成混合方式不用追加成本，但未提交排程或报价。',
  '同时检查三个硬条件，推荐当前有证据可行的方案；说明其他方案需要补什么证据或调整，不能把口头承诺当作既成事实。',
  '只有乙同时满足；甲缺远程且修改未经证明；丙超5单位，不能因更快就忽略预算。'),
 ('test_surveys', 'test', 'small', 'parallel', '调查结果可比性核验',
  'S1：甲站报告80%满意，来自50位到访者的自愿问卷。S2：乙站报告70%满意，来自200位会员的随机抽样。'
  'S3：调查时间分别为春季和秋季，问卷题目不同。S4：两份报告都没有给出未回应人数、总体规模或原始答卷。',
  '分别核验两份报告能支持的结论，再写一段比较结论和补充数据清单；不能据百分比直接认定甲服务更好。',
  '样本来源、抽样方法、时间、题目不同，不能直接比较服务质量；缺少总体规模、未回应及原始答卷，不编置信区间。'),
 ('test_seating', 'test', 'large', 'serial', '培训分班容量分析',
  'E1：每条记录给出申请人数和已完成前置课程人数，仅已完成课程者有资格安排。'
  'E2：先按组汇总有资格人数，再与甲70、乙90、丙110、丁130的组席位比较。'
  'E3：各组时段相互冲突，剩余席位不能跨组相抵；不能用总申请人数冒充有资格需求。'
  'E4：只建议补充席位或调整时段，没有授权替任何人报名。',
  '按组计算申请、有资格、无资格人数与席位缺口，形成两阶段分班建议；保留不能跨组调剂和未授权代报名的约束。', ''),
 ('test_workorders', 'test', 'large', 'bottleneck', '维护工单月报',
  'W1：每条工单给出计划分钟与实际分钟；正偏差为实际减计划，小于零表示提前。'
  'W2：最终报告必须同时包含各组总工时、全部工单的总偏差、超计划工单数及限制。'
  'W3：材料没有故障原因或人员绩效证据，不能因耗时推断责任；不能只复制一条分支摘要。',
  '综合全表形成完整月报，核对分组汇总与总计相等，分别报告净偏差及正超时量，不混淆两者。', ''),
 ('test_shipments', 'test', 'large', 'handoff', '物资到货交接报告',
  'H1：每条记录给出应交数量、签收数量和一份来源编号；差额为应交减签收。'
  'H2：多签不等于可以抵消另一批次少签，正缺口须逐批计算后汇总。'
  'H3：核对报告必须保留每组的来源范围，列出总应交、总签收、净差及正缺口；没有损毁或责任证据。',
  '将分组事实、来源和异常限制完整交接到最终报告，区别净差与未满足数量，不因另一批多签就宣称全部交齐。', ''),
 ('test_energy', 'test', 'large', 'parallel', '多校区用能记录分析',
  'P1：各行是独立单元的基准用量和本期用量，单位千瓦时。P2：按校区汇总，再报告整体净变化。'
  'P3：各校区可独立分析；总体减少不保证每个校区减少，材料没有气温、面积或人数。'
  'P4：不能根据用量变化直接认定措施有效，也不能按人均或面积归一化。',
  '并行核验各校区记录，汇总整体变化、增加单元数和减少单元数，给出有限结论与补充数据需求。', ''),
]


def ledger(key):
    rows, values = [], []
    for i in range(1, 101):
        group = '甲乙丙丁'[i % 4]
        if key == 'cal_transit':
            a, b = 30 + (i*7 % 43), 48
            text = f'第{i}条，{group}组，需求 {a} 人，可用容量 {b} 人；计数是单次需求，不与其他组抵消。'
        elif key == 'test_seating':
            a = 5+i%13; b = i*7%(a+1)
            text = f'第{i}项，{group}组，申请 {a} 人，其中完成前置课程 {b} 人；没有其他资格证明，先筛资格再分配。'
        elif key == 'cal_sensor':
            a, b = 17 + (i % 10), 0
            text = f'第{i}次，{group}组，测量 {a} 摄氏度；为原始读数，没有校正记录或原因说明。'
        elif key == 'cal_archive':
            group = 'ABC'[i % 3]; a, b = (15, 45, 120, 400)[i % 4], int(i % 9 == 0)
            text = f'第{i}件，类别 {group}，年龄 {a} 天，锁定 {"是" if b else "否"}；仅为盘点记录，不代表清理授权。'
        elif key == 'test_workorders':
            a, b = 30 + i % 20, 25 + i*3 % 35
            text = f'第{i}单，{group}组，计划 {a} 分钟，实际 {b} 分钟；无人员评价或故障归因材料。'
        elif key == 'test_shipments':
            a, b = 20 + i % 15, 18 + i*2 % 19
            text = f'第{i}批，{group}组，应交 {a} 件，签收 {b} 件；每批单独核验，未记录损毁或责任结论。'
        else:
            a, b = 80 + i % 31, 70 + i*5 % 47
            text = f'第{i}单元，{group}校区，基准 {a} 千瓦时，本期 {b} 千瓦时；未包含人数、面积与气温。'
        rows.append(f'来源 {key}-L{i:03d}：{text}')
        values.append((group, a, b))
    groups = {}
    for group in sorted({v[0] for v in values}):
        subset = [(a, b) for g, a, b in values if g == group]
        item = {'记录数': len(subset), '第一列总和': sum(a for a,b in subset), '第二列总和': sum(b for a,b in subset)}
        if key == 'cal_sensor':
            item.update(合格=sum(18<=a<=24 for a,b in subset), 异常=sum(not 18<=a<=24 for a,b in subset))
        elif key == 'cal_archive':
            item.update(锁定=sum(b for a,b in subset), 待审批=sum(a>{'A':30,'B':90,'C':365}[group] and not b for a,b in subset))
        elif key == 'test_seating':
            seats={'甲':70,'乙':90,'丙':110,'丁':130}[group]
            eligible=sum(b for a,b in subset)
            item.update(申请=sum(a for a,b in subset), 有资格=eligible, 无资格=sum(a-b for a,b in subset),
                        席位=seats, 缺口=max(0,eligible-seats))
        else:
            item.update(第一列减第二列=sum(a-b for a,b in subset), 正缺口=sum(max(0,a-b) for a,b in subset),
                        第二列较大记录数=sum(b>a for a,b in subset), 第一列较大记录数=sum(a>b for a,b in subset),
                        正超额=sum(max(0,b-a) for a,b in subset))
        groups[group] = item
    return '\n'.join(rows), groups


def prepare_tasks():
    result = []
    for key, split, size, challenge, title, facts, question, reference in CASES:
        table, gold = ledger(key) if size == 'large' else ('', {})
        if gold:
            reference = json.dumps(gold, ensure_ascii=False)
        criteria = ['完整满足本任务交付要求，事实和计算与材料一致，保留来源编号。',
                    '遵守材料约束，区分已知事实、建议和未知事项，不虚构原因、数据或已执行的操作。']
        if challenge == 'short':
            criteria[0] = '用一段简洁通知保留原角色、数量、截止时间、接收方和全部条件分支，不添加分析章节。'
        text = f'这是独立编写的虚构封闭场景「{title}」，不代表真实机构或法律规则。只用以下材料，不联网或执行工具。\n{facts}\n{table}\n交付要求：{question}'
        single = challenge in ('short', 'oversplit', 'coupled') and split == 'test'
        template = 'single-answer' if single else 'serial-analysis' if challenge == 'serial' else 'parallel-analysis'
        plan = json.loads((ROOT / f'data/task-plans/{template}-v2.json').read_text())
        plan['decomposition_reason'] = '短或强耦合交付不拆分。' if single else '计算结果是后续判断的必要输入。' if challenge == 'serial' else '事实汇总与约束核验可以独立进行，再完整交付。'
        plan['acceptance_criteria'] = criteria
        for node in plan['nodes']:
            cap = (65536 if node['node_id'] == plan['final_node_id'] else 32768) if size == 'large' else (32768 if node['node_id'] == plan['final_node_id'] else 8192)
            node['contract']['capability'].update(input_budget_tokens=cap, difficulty='medium', risk='high' if size=='large' else 'medium')
            instruction = ('完整完成原始任务，逐条核对所有交付要求。' if node['node_id']==plan['final_node_id'] else
                '汇总全部原始事实，完成所需计算并列出来源；只交付本节点分析，不虚构信息。' if node['node_id']=='cost' else
                '核验约束、信息缺口及可能的误判；如有上游结果必须据其完成判断，保留关键来源和限制。')
            node['prompt_template'] = node['contract']['objective'] = instruction
            node['node_type'] = 'generation' if node['node_id']==plan['final_node_id'] else 'synthesis' if node['node_id']=='cost' else 'verification'
            if node['node_id']==plan['final_node_id']:
                node['contract']['covers'] = [0,1]
        context = {n['node_id']: {'result': reference if n['node_id']=='cost' else facts,
            'evidence': '正文中所有来源编号；表格范围 '+key+'-L001 至 L100' if gold else facts,
            'assumptions': '仅依据给定的虚构材料；未知原因、外部情况和执行状态不作推断。'} for n in plan['nodes']}
        result.append({'task_id':key, 'cell':'large-high' if size=='large' else 'small-medium', 'split':split,
            'challenge':challenge, 'source_id':'authored-case:'+key, 'source_kind':'independently-authored-closed-scenario',
            'title':title,'task':text,'criteria':criteria,'plan':plan,'reference_context':context,'reference_facts':reference,
            'evaluation_reference':reference,
            'material_sha256':material_digest(text), 'minimum_material_bytes':9000 if size=='large' else 1})
    return result


def prepare():
    manifest = load_model_manifest(ROOT/'data/model-manifests/volcengine-agent-plan.json')
    return {'schema_version':'joint-research-v1', 'tasks':prepare_tasks(),
        'implementation_sha256':implementation_fingerprint(), 'manifest_sha256':digest(asdict(manifest)),
        'runner_sources':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
            (Path(__file__), ROOT/'experiments/run_joint_research.py')},
        'max_node_fallbacks':0,'planner_repairs':0,'planner_model':'strong',
        'planner_input_cap':65536,'auto_node_input_cap':65536,'judge_input_cap':131072,
        'execution_policy':{'maxConcurrency':2,'providerConcurrency':{'ark-plan':2},'providerMinIntervalMs':{'ark-plan':100}},
        'constraints':{'qualityMin':80,'costMax':400,'latencyMaxMs':300000,'weights':{'quality':.5,'cost':.25,'latency':.25}},
        'coverage_cells':['small-medium','large-high'], 'repeats':1, 'order_seed':394010,
        'failure_policy':'isolate-settled-stop-on-infrastructure',
        'acceptance':{'assumed_task_delta_sd':10,'target_mean_half_width':8,'minimum_test_tasks':8,
            'bootstrap_repeats':2000,'bootstrap_seed':394010,'maximum_quality_loss':3,'minimum_cost_saving':.2,'maximum_latency_ratio':1.1},
        'scope':'封闭机构运营资料核验与研究交付；两个输入/风险联合场景，不能分离输入与风险的单独因果效应。',
        'material_review':{'kind':'AI-authored-and-reviewed','human_verified':False,
            'limits':'案例为分别设计的虚构材料；不代表线上分布，表格行不当作独立任务。校准与测试主题不同但共享统计格式。'},
        'material_review_criteria':['校准与测试任务不是同一问题仅换数字或实体的副本，任务数按来源包计数。',
            '任务的事实、限制和交付要求明确且可评分，冻结参考没有明显计算或逻辑错误。',
            '所标挑战可从材料与交付要求检验；短任务允许不拆分，所有结论限于自编封闭案例。'],
        'human_review_rule':'每个挑战选 task_id 最前的测试任务，复核人工、两条自动冷启动及两份缓存计划；所有被拒计划加审。',
        'shared_evidence':'两 Issue 在同一冻结协议中共享校准和人工/整任务运行；查看一项结果后不调整另一项。'}
