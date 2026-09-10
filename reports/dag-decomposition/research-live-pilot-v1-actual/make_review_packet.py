"""从先导原始证据生成未填写的人工复核包；不把 AI 评审当作人工结果。"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    assert (ROOT / 'output/artifact-index.json').exists(), '等待整批完成并归档'
    raw = json.loads((ROOT / 'output/session.json').read_text())
    tasks = {t['task_id']: t for t in raw['config']['tasks']}
    plans = []
    for task in tasks.values():
        plans.append((task['task_id'], 'manual-reference', task['plan']))
    for row in raw['runs']:
        if row['mode'] == 'auto-cold':
            plans.append((row['task_id'], row['run_id'], row.get('plan') or row.get('planner_output')))
    for row in raw['plan_setups']:
        plans.append((row['cache_id'], 'setup-' + row['cache_id'], row.get('plan') or row.get('planner_output')))
    rows, key = [], {}
    for task_id, origin, plan in plans:
        label = hashlib.sha256((task_id + ':' + origin).encode()).hexdigest()[:12]
        key[label] = origin
        rows.append({'review_id': label, 'task': tasks[task_id]['task'],
            'acceptance_criteria': tasks[task_id]['criteria'], 'plan': plan,
            'reviewer': None, 'reviewed_at': None, 'human_reviewed': False,
            'checks': [{'criterion': text, 'passed': None, 'rationale': None} for text in (
                '职责是否覆盖全部原始交付要求', '每条依赖是否有实际消费且必要依赖未遗漏',
                '上下文和来源是否充分、没有虚构材料', '是否存在重复或过度拆分、能否合理不拆分',
                '节点输入容量声明是否合理')], 'overall': None})
    rows.sort(key=lambda row: row['review_id'])
    for name, value in [('human-review-template.json', {'scope': '先导问题诊断，不充抵完整矩阵的人工抽检',
            'contains_model_grades': False, 'rows': rows}), ('review-origin-key.json', key)]:
        path = ROOT / name
        assert not path.exists(), '不覆盖已有复核材料'
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    print({'unreviewed_plans': len(rows), 'human_results': 0})


if __name__ == '__main__':
    main()
