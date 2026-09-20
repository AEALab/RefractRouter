"""对 MoA 评审中失败（非 reviewed）的调用做定向补审；输入、策略与评审者完全不变。

研究负责人授权的显式例外：冻结策略的零重试规则不追溯修改，本脚本只把「评审调用失败
导致 pending」的运行做基础设施恢复。原失败调用原样留痕在 targeted_review 里，补审结果
替换进 primary/escalation 并用同一 aggregate 函数重算共识；再次失败则保持原记录不动。
"""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

from refractrouter.dag_study_execution import write_json
from refractrouter.moa_review import (MOA_POLICY, aggregate, default_invoke, digest, judge,
    output_messages)
from refractrouter.quality_study import file_digest, load_study

ROOT = Path(__file__).resolve().parents[1]


def failed_calls(records):
    """返回 (record, row, stage) 中所有 status != reviewed 的调用。"""
    rows = []
    for record in records:
        for stage in ('primary', 'escalation'):
            for row in record.get(stage, []):
                if row.get('status') != 'reviewed':
                    rows.append((record, row, stage))
    return rows


def retry_records(tasks, refs, run_rows, records, invoke=default_invoke):
    """按 run_id 重建输入并只补审失败调用；返回 (新记录列表, 补审明细)。"""
    by_id = {t['task_id']: t for t in tasks}
    by_run = {row['run_id']: row for row in run_rows}
    output_records = []
    audit = []
    for record in records:
        if not any(row.get('status') != 'reviewed'
                   for stage in ('primary', 'escalation') for row in record.get(stage, [])):
            output_records.append(deepcopy(record))
            continue
        run_id = record['run_id']
        row = by_run[run_id]
        task = by_id[record['task_id']]
        messages, criteria = output_messages(task, row['output'])
        reviewed_prompt = next(
            (r['prompt_sha256'] for stage in ('primary', 'escalation')
             for r in record.get(stage, []) if r.get('status') == 'reviewed'), None)
        if reviewed_prompt is not None and digest(messages) != reviewed_prompt:
            raise ValueError(f'输入重建不一致：{run_id}')
        updated = deepcopy(record)
        replaced = []
        for stage in ('primary', 'escalation'):
            for index, judge_row in enumerate(updated.get(stage, [])):
                if judge_row.get('status') == 'reviewed':
                    continue
                reviewer = next(deepcopy(r) for r in MOA_POLICY[stage]
                                if r['reviewer_id'] == judge_row['reviewer_id'])
                print(f'  补审 {run_id} {judge_row["reviewer_id"]} …', flush=True)
                new_row = judge(reviewer, messages, criteria, invoke)
                replaced.append({'stage': stage, 'original': judge_row, 'new': new_row,
                                 'prompt_sha256': digest(messages)})
                if new_row.get('status') == 'reviewed':
                    updated[stage][index] = new_row
        updated['consensus'] = aggregate(updated['primary'], updated['escalation'], criteria)
        updated['targeted_review'] = {
            'note': ('研究负责人授权的显式例外：对评审失败调用做定向补审，'
                     '输入、策略与评审者不变；原失败调用逐条留痕。'),
            'replaced_failed_calls': replaced,
        }
        output_records.append(updated)
        audit.append({'run_id': run_id, 'task_id': record['task_id'],
                      'replaced': [r['original']['reviewer_id'] for r in replaced],
                      'new_status': [r['new'].get('status') for r in replaced],
                      'overall': updated['consensus']['overall']})
    return output_records, audit


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study-dir', type=Path, default=ROOT / 'data/quality-study-v1')
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--reviews', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error('必须使用全新输出目录')
    args.output_dir.mkdir(parents=True)
    _, tasks, refs, *_ = load_study(args.study_dir)
    result = json.loads(args.results.read_text())
    run_rows = [r for r in result['runs'] if 'output' in r]
    records = json.loads(args.reviews.read_text())['records']
    failures = failed_calls(records)
    if not failures:
        raise SystemExit('没有需要补审的失败调用')
    print('失败调用 ' + str(len(failures)) + ' 次：' + ', '.join(
        f"{record['run_id']}/{row['reviewer_id']}" for record, row, _ in failures), flush=True)
    updated, audit = retry_records(tasks, refs, run_rows, records, default_invoke)
    write_json(args.output_dir / 'moa-results.json',
               {'kind': 'output', 'policy_sha256': digest(MOA_POLICY),
                'records': updated, 'targeted_review_audit': audit,
                'source': str(args.reviews),
                'note': ('定向补审归档：原失败调用与补审结果逐条留痕；'
                         '这是对冻结零重试规则的显式例外，不修改策略。')})
    readme = ('# MoA 输出评审定向补审（moa-output-01-retry）\n\n'
              '研究负责人授权的显式例外：对 moa-output-01 中 status 不是 reviewed 的评审调用'
              '做定向补审，输入、策略与评审者完全不变。\n\n'
              '- 原失败调用原样保留在每条记录的 targeted_review.replaced_failed_calls；\n'
              '- 补审成功的新行替换进 primary/escalation，并用同一 aggregate 重算共识；\n'
              '- 再次失败的调用保持原记录不动，如实保留 pending。\n')
    (args.output_dir / 'README.md').write_text(readme, encoding='utf-8')
    write_json(args.output_dir / 'artifact-index.json',
               {p.name: file_digest(p) for p in sorted(args.output_dir.iterdir())
                if p.name != 'artifact-index.json'})
    print(json.dumps({'mode': 'targeted-retry', 'failed_before': len(failures),
                      'audit': audit}, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
