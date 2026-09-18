"""合流 MoA 材料评审分片：把定向重跑结果与既有分片合成门禁唯一输入。

门禁（`moa_gate`）只读取一个 records 文件，因此本脚本负责校验分片口径一致、
按冻结任务顺序重排、剔除不在目标集合内的记录，并输出可复核的摘要与 README。
脚本不发起任何模型调用，也不改写任何评审记录。
"""
import argparse
import json
from copy import deepcopy
from pathlib import Path

from refractrouter.dag_study_execution import write_json
from refractrouter.moa_review import MOA_MATERIAL_CRITERIA, MOA_POLICY, digest
from refractrouter.quality_study import file_digest, load_study

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 'moa-merged-records-v1'
INDEX_NAME = 'artifact-index.json'


def read_shard(path):
    """读取单个 MoA 评审分片，返回 (kind, policy_sha256, records)。"""
    data = json.loads(Path(path).read_text())
    if not isinstance(data, dict) or not isinstance(data.get('records'), list):
        raise SystemExit(f'分片格式无效：{path}')
    return data.get('kind'), data.get('policy_sha256'), data['records']


def merge_records(shards, *, expected_kind='material', expected_policy=None,
                  allow_supersede=False):
    """校验分片口径一致后按来源顺序合流；同一任务跨分片重复默认报错。

    每条记录深拷贝保留，不做任何改写；返回 (按来源顺序排列的记录, 覆盖明细)。
    `allow_supersede=True` 时后出现的分片覆盖同一任务的旧记录，覆盖明细逐条留痕，
    用于「同一任务的定向重审取代旧结论」这一种明确情形；默认关闭，避免静默覆盖。
    """
    merged, order, superseded = {}, [], []
    for path, kind, policy, records in shards:
        if expected_kind is not None and kind != expected_kind:
            raise SystemExit(f'分片种类不符：{path} 为 {kind}，期望 {expected_kind}')
        if expected_policy is not None and policy != expected_policy:
            raise SystemExit(f'分片策略哈希不符：{path}')
        for record in records:
            task_id = record.get('task_id')
            if not task_id:
                raise SystemExit(f'分片记录缺少 task_id：{path}')
            if task_id in merged:
                if not allow_supersede:
                    raise SystemExit(f'同一任务在多个分片重复：{task_id}（{path}）')
                superseded.append({'task_id': task_id,
                                   'previous_source': str(merged[task_id]['_source']),
                                   'previous_overall': (merged[task_id]['record'].get('consensus') or {}).get('overall'),
                                   'source': str(path),
                                   'overall': (record.get('consensus') or {}).get('overall')})
            else:
                order.append(task_id)
            merged[task_id] = {'record': deepcopy(record), '_source': path}
    return [merged[task_id]['record'] for task_id in order], superseded


def order_records(records, task_ids):
    """按冻结任务顺序重排记录；返回 (有序记录, 目标集合外的任务 id)。"""
    by_id = {}
    for record in records:
        task_id = record.get('task_id')
        if task_id in by_id:
            raise SystemExit(f'合流记录内部重复任务：{task_id}')
        by_id[task_id] = record
    wanted = list(dict.fromkeys(task_ids))
    missing = [task_id for task_id in wanted if task_id not in by_id]
    if missing:
        raise SystemExit(f'目标任务缺少评审记录：{missing}')
    extras = [task_id for task_id in by_id if task_id not in set(wanted)]
    return [by_id[task_id] for task_id in wanted], extras


def summarize(records, criteria=MOA_MATERIAL_CRITERIA):
    """按门禁口径统计合流记录：全部 criterion 共识 pass 才算该题过门禁。"""
    ready, not_ready = [], []
    overall = {'pass': 0, 'fail': 0, 'pending': 0}
    failed, escalated = 0, 0
    for record in records:
        consensus = record.get('consensus') or {}
        verdicts = {row.get('criterion'): row.get('verdict')
                    for row in consensus.get('criteria', [])}
        status = consensus.get('overall')
        if status in overall:
            overall[status] += 1
        escalated += consensus.get('escalated_criteria') or 0
        failed += consensus.get('failed_records') or 0
        if len(verdicts) == len(criteria) and all(verdicts.get(c) == 'pass' for c in criteria):
            ready.append(record['task_id'])
        else:
            not_ready.append(record['task_id'])
    return {'records': len(records), 'gate_ready': len(ready),
            'not_gate_ready': len(not_ready), 'gate_ready_task_ids': ready,
            'not_gate_ready_task_ids': not_ready, 'overall_counts': overall,
            'failed_records': failed, 'escalated_criteria': escalated,
            'criteria': list(criteria)}


def render_readme(sources, summary, *, policy_sha256, note=None, dropped=(), superseded=()):
    """渲染中文 README；列出分片路径、哈希、门槛口径与统计。"""
    lines = [
        '# MoA 材料评审合流记录',
        '',
        '本目录由 `experiments/merge_moa_records.py` 生成，是付费留出实验 MoA 门槛的唯一读取文件。',
        '合流不发起模型调用，也不改写任何评审记录，只做口径校验、去重与冻结顺序重排。',
        '',
        f'- MoA 策略哈希：`{policy_sha256}`',
        f'- 记录数 {summary["records"]}：过门禁 {summary["gate_ready"]} 题，未过门禁 {summary["not_gate_ready"]} 题',
        f'- 共识分布：{summary["overall_counts"]}',
        f'- 未过门禁任务：{summary["not_gate_ready_task_ids"]}',
        f'- 无效评审记录数 {summary["failed_records"]}；升级 criterion 数 {summary["escalated_criteria"]}',
        '',
        '## 分片来源',
        '',
    ]
    for source in sources:
        lines.append(f'- `{source["path"]}`（sha256 `{source["sha256"]}`，'
                     f'{len(source["records"])} 条）')
    lines += [
        '',
        '## 门槛口径',
        '',
        '- 逐 criterion 两位初审一致则采用；不一致升级两位重审；升级后仍不一致记 pending。',
        '- 只有六项 criterion 全部共识 pass 的记录才算该题过门禁；pending 与 fail 都不放行。',
        '- 确定性关键检查仍然一票否决，MoA 共识不能覆盖确定性 fail。',
        '- 本门槛是本地多模型共识门槛，不是真人审查，也不能证明用户可接受性。',
    ]
    if dropped:
        lines += ['', '## 未纳入合流的记录', '', f'- {list(dropped)}（不在目标任务集合内）']
    if superseded:
        lines += ['', '## 被覆盖的旧记录', '',
                  '同一任务的定向重审会取代旧结论；下表逐条留痕，旧记录仍保留在分片文件中。', '']
        for row in superseded:
            lines.append(f'- {row["task_id"]}：`{row["previous_source"]}`（{row["previous_overall"]}）'
                         f' → `{row["source"]}`（{row["overall"]}）')
    if note:
        lines += ['', '## 备注', '', note]
    lines.append('')
    return chr(10).join(lines)


def write_index(output_dir):
    """写出目录哈希索引；索引自身不列入，避免自引用哈希。"""
    entries = {path.name: file_digest(path) for path in sorted(Path(output_dir).iterdir())
               if path.name != INDEX_NAME}
    write_json(Path(output_dir) / INDEX_NAME, entries)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study-dir', type=Path, default=ROOT / 'data/quality-study-v1')
    parser.add_argument('--source', type=Path, action='append', required=True,
                        help='待合流的 moa-results.json 分片，按给定顺序处理')
    parser.add_argument('--task-ids', nargs='+',
                        help='目标任务集合；给定后只保留这些任务并按此顺序输出')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--note')
    parser.add_argument('--allow-supersede', action='store_true',
                        help='允许后出现的分片覆盖同一任务的旧记录，并逐条留痕')
    args = parser.parse_args(argv)
    expected_policy = digest(MOA_POLICY)
    shards = []
    for path in args.source:
        kind, policy, records = read_shard(path)
        shards.append((path, kind, policy, records))
    merged, superseded = merge_records(shards, expected_kind='material',
                                       expected_policy=expected_policy,
                                       allow_supersede=args.allow_supersede)
    _, tasks, *_ = load_study(args.study_dir)
    task_ids = args.task_ids or [task['task_id'] for task in tasks]
    if len(task_ids) != len(set(task_ids)):
        raise SystemExit('--task-ids 存在重复任务')
    known = {task['task_id'] for task in tasks}
    unknown = [task_id for task_id in task_ids if task_id not in known]
    if unknown:
        raise SystemExit(f'--task-ids 含未知任务：{unknown}')
    records, dropped = order_records(merged, task_ids)
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise SystemExit('输出目录已存在且非空，请换新目录')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize(records)
    sources = [{'path': str(path), 'kind': kind, 'policy_sha256': policy,
                'sha256': file_digest(path),
                'records': [record.get('task_id') for record in records_list]}
               for path, kind, policy, records_list in shards]
    write_json(args.output_dir / 'moa-results.json',
               {'schema_version': SCHEMA_VERSION, 'kind': 'material',
                'policy_sha256': expected_policy, 'study_dir': str(args.study_dir),
                'task_ids': task_ids, 'dropped_task_ids': dropped, 'note': args.note,
                'superseded': superseded, 'sources': sources, 'summary': summary,
                'records': records})
    (args.output_dir / 'README.md').write_text(
        render_readme(sources, summary, policy_sha256=expected_policy, note=args.note,
                      dropped=dropped, superseded=superseded), encoding='utf-8')
    write_index(args.output_dir)
    print(json.dumps({'mode': 'merge', 'sources': len(shards), 'records': len(records),
                      'gate_ready': summary['gate_ready'],
                      'not_gate_ready': summary['not_gate_ready'],
                      'superseded': [row['task_id'] for row in superseded],
                      'real_model_calls': 0},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
