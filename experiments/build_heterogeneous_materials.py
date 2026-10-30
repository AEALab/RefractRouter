"""生成六臂研究的构造材料与可复算参考；不调用模型，不认证独立材料质量。"""
from pathlib import Path
import json
from decimal import Decimal

from refractrouter.quality_study import digest

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'data/node-tool-heterogeneous-v1'


def make(family, index, title, instruction, texts, values, supports, criteria):
    split = 'development' if index == 0 else 'candidate-holdout'
    task = {'task_id': f'{family}-{index}', 'title': title, 'split': split,
        'family': family, 'provenance': {'kind': 'constructed', 'creator': 'Codex',
            'date': '2026-10-30', 'limits': '同族共用生成逻辑；未获独立材料审查，不声称语义独立或真实业务代表性。'},
        'instruction': instruction, 'materials': [{'source_id': f's{i+1}', 'title': f'材料{i+1}', 'text': text}
            for i, text in enumerate(texts)],
        'requested_findings': {key: description for key, (_, description) in values.items()},
        'semantic_criteria': criteria,
        'output_contract': {'answer': '完整中文正文，解释计算、依据、限制和不确定性。只分析材料，不执行外部工具。',
            'findings': '列表；每项恰有 id/value/sources，覆盖全部 requested_findings，保留类型；引用支持该结论的 source_id。'}}
    task['task_sha256'] = digest(task)
    reference = {'task_id': task['task_id'], 'task_sha256': task['task_sha256'], 'findings': {}}
    for key, (value, _) in values.items():
        reference['findings'][key] = {'value': value, 'kind': 'set' if isinstance(value, list) else 'scalar',
            'support_options': supports[key]}
    return task, reference


def materials():
    rows = []
    for i in range(3):
        n = [175, 260, 335][i]; unit = [71, 57, 43][i]
        a = round(float(Decimal(n*unit)*Decimal('1.09')+460), 2)
        b = round(n*(unit+5)*.94+820, 2); c = n*(unit+4)+610
        rows.append(make('purchase', i, ['仪器采购复核', '实验室备用件采购', '维护终端采购'][i],
            f'采购 {n} 件。比较三个供应商最新含税到货总价，选已确认符合全部硬条件的最低价者；解释未确认事项。',
            [f'数量 {n}，预算 {max(a,b,c)+1000:.2f} 元，交期不晚于11-24，保修至少24个月，证书须已确认有效。',
             f'A：单价 {unit} 元未税，税率9%，运费460元已含税；数量达到400才打95折。保修18个月，证书有效，11-22到货。',
             f'B旧报价：含税单价 {unit+3}，运费300；新通知替代价格：含税单价 {unit+5}，运费820。货款数量达到150打94折，运费不折扣；保修24个月，11-24到货，证书待确认。',
             f'C：含税单价 {unit+4}，运费610；500元优惠券仅11-01及以前付款，本任务11-05付款。保修30个月，证书有效，11-24到货。'],
            {'cost_a': (a, 'A总价'), 'cost_b': (b, 'B最新总价'), 'cost_c': (c, 'C总价'),
             'selected': ('C', '已确认合格的最低价者'), 'b_confirmed': (False, 'B是否已确认合格')},
            {'cost_a': [['s1','s2']], 'cost_b': [['s1','s3']], 'cost_c': [['s1','s4']],
             'selected': [['s1','s2','s3','s4']], 'b_confirmed': [['s1','s3']]},
            ['复算税费和折扣，不叠加旧报价；资格未确认不能当通过。', '正文与字段一致；不能把价格最低等同资格合格。']))

        ad, bd, cd, fd, gd = [(4,6,3,4,2),(2,7,5,3,2),(5,4,6,5,1)][i]
        ready = ad+bd+fd; technical = ready+gd; window = ready+4
        rows.append(make('schedule', i, ['批处理上线安排', '数据管道切换安排', '区域服务迁移安排'][i],
            '给出最多两项并发、任务不可拆分的最早排程；区分前置齐备、技术完工、窗口完工及等待时长。',
            [f'有效清单：A {ad}小时无前置；B {bd}小时依赖A；C {cd}小时依赖A；D 1小时无前置；E 2小时依赖B和C；F {fd}小时依赖B；G {gd}小时依赖D/E/F。每项独占一个槽，最多两个槽。',
             f'旧文档曾写F=1小时、C依赖B，均被有效清单替代。G必须完整位于[{window},{window+gd+2}]；其他任务无窗口。',
             't=0全部任务未开始；D只有预计时长，尚无签字或测试完成记录。等待从G前置齐备时算到G实际开始。'],
            {'ready': (ready,'G前置最早齐备'), 'technical_finish': (technical,'忽略窗口的最早G结束'),
             'window_finish': (window+gd,'考虑窗口的最早G结束'), 'window_wait': (4,'窗口排程的实际等待时长'),
             'approval_confirmed': (False,'现在是否已有批准')},
            {'ready': [['s1']], 'technical_finish': [['s1']], 'window_finish': [['s1','s2']],
             'window_wait': [['s1','s2','s3']], 'approval_confirmed': [['s3']]},
            ['给出满足依赖和两槽限制的完整排程。', '不能用技术完工到窗口开始之差冒充实际等待；预计完成不等于已批准。']))

        paid, refund, extra = [(900,140,75),(1200,260,105),(1800,330,125)][i]
        events = [{'id':'p1','kind':'paid','amount':paid}, {'id':'p1','kind':'paid','amount':paid},
            {'id':'p2','kind':'paid','amount':extra}, {'id':'p2','kind':'paid','amount':extra+1},
            {'id':'r1','kind':'refund','amount':refund}, {'id':'r2','kind':'refund','amount':paid+extra},
            {'id':'q1','kind':'pending','amount':500}]
        rows.append(make('ledger', i, ['结算事件去重', '订阅退款流水核验', '票务回调流水核验'][i],
            '按顺序复算账本，并指出“所有事件直接加总、按整个载荷去重”的实现为什么错误。',
            ['规则：初始余额0。相同id且载荷相同是重复；相同id载荷不同是冲突，保留首次、不覆盖；冲突不入账。paid入账，refund仅在不超过当前余额时扣减，否则拒绝；pending不入账。',
             json.dumps(events, ensure_ascii=False), '金额单位为元；拒绝退款不允许把余额变负；不能假定pending以后会成功。'],
            {'balance': (paid+extra-refund,'已确认余额'), 'duplicates': (['p1'],'重复id'),
             'conflicts': (['p2'],'冲突id'), 'rejected_refunds': (['r2'],'拒绝退款id'), 'pending': (['q1'],'未确认id')},
            {key: [['s1','s2']] for key in ('balance','duplicates','conflicts','rejected_refunds','pending')},
            ['区分重复与冲突，按首次有效载荷入账。', '给出修正的处理顺序或伪代码，不把pending算成已收款。']))

        parts = [(137,28,9,36,5),(182,47,11,25,7),(219,31,17,48,9)][i]
        stock,reserved,blocked,inbound,used = parts; available = stock-reserved-blocked+inbound-used
        second = [89,120,103][i]; maximum = min(available//3,second//2)
        rows.append(make('inventory', i, ['双仓装配可用量', '备件套装交付能力', '传感器套件库存核验'][i],
            '计算截止11-12可用零件和最多可组装套数，说明为什么不能使用全口径库存。',
            [f'两个仓库汇总X在库 {stock}，已预留 {reserved}，质检冻结 {blocked}；预留与冻结互不重叠。',
             f'已确认11-11到货X {inbound}；11-10已确认另消耗X {used}；还有预计11-14到货50和未确认到货80，均不在本次可用范围。Y在上述扣除后截止11-12可用 {second}。',
             '每套用X三件、Y两件，不能拆分套装。不允许解除预留或冻结，且已消耗数量尚未从在库汇总扣除。'],
            {'available_x': (available,'截止日可用X'), 'available_y': (second,'截止日可用Y'),
             'max_kits': (maximum,'最多完整套数'), 'unconfirmed_included': (False,'是否纳入未确认到货')},
            {'available_x': [['s1','s2','s3']], 'available_y': [['s2']], 'max_kits': [['s1','s2','s3']],
             'unconfirmed_included': [['s2']]},
            ['不重复扣除、不使用截止日之后或未确认到货；给出整数套装的瓶颈。']))

        n1,n2,x1,x2 = [(120,880,108,836),(75,925,60,888),(240,760,204,737)][i]
        total=n1+n2; good=x1+x2; rate=round(good/total*100,4)
        rows.append(make('metrics', i, ['服务达标率汇总', '客服队列加权复核', '处理时限日报核验'][i],
            '复核全局达标率和门槛判断，解释分组平均值不能代替全局比率，并说明能否得出P95。',
            [f'甲组样本 {n1}，其中达标 {x1}；乙组样本 {n2}，其中达标 {x2}。两个分组互斥且穷尽本期全部已完成样本。',
             '内部报告门槛：全局已完成样本达标率至少94%才通过。不将未完成样本纳入这个分母；另有90件未完成，不能视为达标。',
             '未提供逐件耗时、分位数或耗时分布；两个组仅给了各自平均耗时，不允许由均值推出P95。'],
            {'completed': (total,'已完成样本总数'), 'on_time': (good,'达标总数'),
             'rate_percent': (rate,'全局达标百分数，至少四位小数'), 'threshold_met': (rate>=94,'是否达到94%'),
             'p95_identified': (False,'材料是否足以确定P95')},
            {'completed': [['s1']], 'on_time': [['s1']], 'rate_percent': [['s1']],
             'threshold_met': [['s1','s2']], 'p95_identified': [['s3']]},
            ['用总达标数除总完成数，不能直接平均两个组的百分比。', '未完成与未知耗时不冒充成功或已知P95。']))

        rows.append(make('approval', i, ['数据变更审批资格', '维护操作批准复核', '配置发布授权材料复核'][i],
            '只判断材料中三项申请是否已经获准，不执行任何操作；列出阻止确认的条件。',
            [f'现行规则R{i+1}替代旧规则：每项申请至少两名不同审查人签字，均不得是申请人；至少一名属于合规组。过期签字无效，到期日当天有效。缺材料记未确认，不能推定补齐。',
             f'观察日11-{10+i:02d}。申请A由u1发起，签字u2（合规，有效到11-20）、u3（工程，有效到11-20）；申请B由u4发起，签字u4（合规，有效到11-20）、u5（工程，有效到11-20）。',
             f'申请C由u6发起，签字u7（合规，有效到11-{9+i:02d}）、u8（工程，有效到11-20）；还有一份待核实签字，不知道身份和有效期。',
             '旧规则只要求一个签字，已经失效。计划中的补签和审批排程不能作为已经批准的证据。'],
            {'approved': (['A'],'已确认批准集合'), 'b_approved': (False,'B是否已获批准'),
             'c_approved': (False,'C是否已获批准'), 'old_rule_used': (False,'是否可以沿用旧规则')},
            {'approved': [['s1','s2','s3']], 'b_approved': [['s1','s2']], 'c_approved': [['s1','s3']],
             'old_rule_used': [['s1'],['s4']]},
            ['不能把申请人签字计入、过期签字计入或未知签字当有效。', '引用现行规则并逐项解释，不声称已经执行外部操作。']))
    return rows


def main():
    DEST.mkdir(parents=True, exist_ok=False)
    rows=materials()
    for name,value in [('tasks.json',{'schema':'heterogeneous-materials-v1','tasks':[t for t,_ in rows]}),
                       ('references.json',{'schema':'heterogeneous-references-v1','references':{t['task_id']:r for t,r in rows}})]:
        (DEST/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


if __name__ == '__main__':
    main()
