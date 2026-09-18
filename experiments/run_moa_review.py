"""MoA 评审 CLI：--preflight 零调用冻结策略；--live 显式执行外部模型评审。

live 会通过本机 codex / claude CLI 产生外部模型费用，必须使用新的输出目录，
且先有对应 preflight 冻结文件。评审不经过 Ark 账本，成本单独报告。

--task-ids 只作用于 --kind material，用于门禁未通过题目的定向重跑；
--timeout-seconds 只覆盖单次调用超时，不改变 MOA_POLICY 摘要。
"""
import argparse
import json
import os
from pathlib import Path

from refractrouter.dag_study_execution import write_json
from refractrouter.moa_review import (MOA_POLICY, REVIEW_SCHEMA, digest,
    TIMEOUT_ENV_VAR, calibration_review, material_review, output_review,
    preflight_envelope, purpose_review, resolve_timeout_seconds, summarize_calibration)
from refractrouter.quality_study import file_digest, load_study

ROOT = Path(__file__).resolve().parents[1]


def select_material_tasks(tasks, task_ids):
    """按显式任务清单筛选材料评审目标；未指定时保持全部任务的既定顺序。"""
    if not task_ids:
        return list(tasks)
    if len(task_ids) != len(set(task_ids)):
        raise SystemExit('--task-ids 存在重复任务')
    by_id = {task['task_id']: task for task in tasks}
    unknown = [task_id for task_id in task_ids if task_id not in by_id]
    if unknown:
        raise SystemExit(f'--task-ids 含未知任务：{unknown}')
    return [by_id[task_id] for task_id in task_ids]


def _targets(args):
    if args.kind == 'calibration':
        _, tasks, refs, controls, *_ = load_study(args.study_dir)
        by_id = {t['task_id']: t for t in tasks}
        return [{'case_id': case['case_id'], 'task_id': case['task_id'],
                 'task_sha256': by_id[case['task_id']]['task_sha256'],
                 'output_sha256': digest(case['output']),
                 'author_semantic_label': case['author_semantic_label'],
                 'expected_check_status': case['expected_check_status']}
                for case in controls]
    if args.kind == 'material':
        _, tasks, refs, *_ = load_study(args.study_dir)
        tasks = select_material_tasks(tasks, args.task_ids)
        return [{'task_id': t['task_id'], 'task_sha256': t['task_sha256'],
                 'reference_sha256': digest(refs[t['task_id']])} for t in tasks]
    if args.kind == 'output':
        if args.results is None:
            raise SystemExit('--kind output 需要 --results 指向已评估结果文件')
        result = json.loads(args.results.read_text())
        return [{'run_id': r['run_id'], 'task_id': r['task_id'], 'output_sha256': digest(r['output'])}
                for r in result['runs'] if 'output' in r]
    if args.frozen is None:
        raise SystemExit('--kind purpose 需要 --frozen 指向冻结协议文件')
    frozen = json.loads(args.frozen.read_text())
    return [{'policy_sha256': digest(frozen['statistics_policy']),
             'task_bindings': frozen['task_bindings']}]
    raise SystemExit('unknown kind')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study-dir', type=Path, default=ROOT / 'data/quality-study-v1')
    parser.add_argument('--kind', choices=('material', 'output', 'purpose', 'calibration'),
                        required=True)
    parser.add_argument('--results', type=Path)
    parser.add_argument('--frozen', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--task-ids', nargs='+',
                        help='仅 --kind material：只评审指定任务，用于门禁定向重跑')
    parser.add_argument('--timeout-seconds', type=float,
                        help='单次调用超时覆盖；默认沿用冻结策略值，不改变策略摘要')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preflight', action='store_true')
    mode.add_argument('--live', action='store_true')
    args = parser.parse_args(argv)
    if args.task_ids and args.kind != 'material':
        parser.error('--task-ids 只适用于 --kind material')
    if args.timeout_seconds is not None:
        os.environ[TIMEOUT_ENV_VAR] = str(args.timeout_seconds)
    try:
        timeout_seconds = resolve_timeout_seconds()
    except ValueError as error:
        parser.error(str(error))
    if args.preflight and args.output_dir.exists():
        parser.error('output directory already exists')
    if args.live and not args.output_dir.is_dir():
        parser.error('--live requires an existing preflight output directory')
    if args.preflight:
        args.output_dir.mkdir(parents=True, exist_ok=False)
    targets = _targets(args)
    if args.preflight:
        write_json(args.output_dir / 'preflight.json',
                   {'envelope': preflight_envelope(args.kind, targets), 'targets': targets,
                    'policy': MOA_POLICY, 'review_schema': REVIEW_SCHEMA})
        print(json.dumps({'mode': 'preflight', 'real_model_calls': 0,
                          'targets': len(targets),
                          'timeout_seconds': timeout_seconds,
                          'policy_sha256': digest(MOA_POLICY)}, ensure_ascii=False))
        return
    preflight = json.loads((args.output_dir / 'preflight.json').read_text())
    if preflight['envelope']['policy_sha256'] != digest(MOA_POLICY):
        raise SystemExit('MOA 策略已改变，请重新运行 --preflight')
    # 旧冻结包络没有该字段时按当前生效值执行，避免让可续跑的目录失效。
    frozen_timeout = preflight['envelope'].get('timeout_seconds')
    if frozen_timeout is not None and frozen_timeout != timeout_seconds:
        raise SystemExit('冻结包络的超时与当前生效值不一致，请重新运行 --preflight')
    targets = _targets(args)
    if preflight['envelope']['kind'] != args.kind or preflight['targets'] != targets:
        raise SystemExit('冻结目标与当前输入不一致，请重新运行 --preflight')
    if args.kind == 'material':
        _, tasks, refs, *_ = load_study(args.study_dir)
        records = material_review(select_material_tasks(tasks, args.task_ids), refs)
    elif args.kind == 'output':
        _, tasks, refs, *_ = load_study(args.study_dir)
        result = json.loads(args.results.read_text())
        rows = [r for r in result['runs'] if 'output' in r]
        records = output_review(tasks, refs, rows)
    elif args.kind == 'calibration':
        _, tasks, refs, controls, *_ = load_study(args.study_dir)
        records = calibration_review(tasks, refs, controls)
    else:
        frozen = json.loads(args.frozen.read_text())
        records = [purpose_review(digest(frozen['statistics_policy']), frozen['task_bindings'],
                                  frozen['statistics_policy'])]
    results = {'kind': args.kind, 'policy_sha256': digest(MOA_POLICY), 'records': records}
    if args.kind == 'calibration':
        results['summary'] = summarize_calibration(records)
    write_json(args.output_dir / 'moa-results.json', results)
    write_json(args.output_dir / 'artifact-index.json',
               {p.name: file_digest(p) for p in sorted(args.output_dir.iterdir())})
    print(json.dumps({'mode': 'live', 'targets': len(targets),
                      'records': len(records),
                      'timeout_seconds': timeout_seconds,
                      'policy_sha256': digest(MOA_POLICY),
                      **({'summary': results['summary']} if args.kind == 'calibration' else {})},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
