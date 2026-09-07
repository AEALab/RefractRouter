"""基于归档失败反例的评审校准，阈值是待验证的准入规则，不是人类金标准。"""
import json

from .blind_review import packet, import_reviews


def build_calibration(task, root):
    archive = root/'reports/v0.4-execution-modes/admission-agent-plan-zh-cn/runs/report_001/repeat-1'
    cases = [('missing-comparison', 'dag:cheap.json'), ('substantive-report', 'one-shot:mid.json')]
    records = [dict(record_id=kind, output=json.loads((archive/name).read_text())['result']['final_output'])
               for kind,name in cases]
    public, private = packet(task, records, kind='calibration')
    return {'public': public, 'private': private,
            'criteria': {'rejected_case_max': 50, 'positive_case_min': 80, 'minimum_gap': 20},
            '说明': '校准控制来自已审阅归档；预期边界不是人工金标准。仅两例通过仍不足以证明评审可靠。'}


def check_calibration(bundle, response, *, forbidden_models, simulation=False):
    reviews = import_reviews(bundle['public'], response, forbidden_models=forbidden_models, simulation=simulation)
    mapped = {bundle['private']['sample_records'][sid]: row for sid,row in reviews.items()}
    bad, good = mapped['missing-comparison'], mapped['substantive-report']
    # 固定代码门槛，不能通过编辑材料中的 criteria 绕过。
    passed = (bad['task_checks']['substantive_comparison'] is False and bad['final_score'] <= 50
              and good['final_score'] >= 80 and good['final_score']-bad['final_score'] >= 20)
    return {'passed': passed, 'reviewer': response['reviewer'],
            'negative_score': bad['final_score'], 'positive_score': good['final_score'],
            'simulation': simulation, '说明': '必须识别缺乏实质比较；保留原始分数与有效分数。'}
