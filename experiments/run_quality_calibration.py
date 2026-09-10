"""冻结或执行 #52 的有界辅助评审；默认零调用，--live 必须绑定既有冻结计划。"""
import argparse
import json
from pathlib import Path

from refractrouter.dag_study_execution import write_json
from refractrouter.quality_calibration import ROOT, build_plan, run_calibration


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study-dir', type=Path, default=ROOT / 'data/quality-study-v1')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--frozen-plan', type=Path)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--calibration-cases', nargs='*', help='预检时选定开发样例；不提供值则跳过校准')
    parser.add_argument('--material-tasks', nargs='*', help='预检时选定材料；不提供值则跳过材料检查')
    args = parser.parse_args(argv)
    if args.live:
        if args.calibration_cases is not None or args.material_tasks is not None:
            parser.error('live selection is fixed by --frozen-plan')
        if args.frozen_plan is None:
            parser.error('--live requires --frozen-plan')
        plan = json.loads(args.frozen_plan.read_text())
        summary = run_calibration(args.study_dir, plan, args.output_dir)
    else:
        if args.frozen_plan is not None:
            parser.error('--frozen-plan requires --live')
        plan = build_plan(args.study_dir, case_ids=args.calibration_cases, material_ids=args.material_tasks)
        args.output_dir.mkdir(parents=True, exist_ok=False)
        write_json(args.output_dir / 'frozen-plan.json', plan)
        summary = {k: plan[k] for k in ('real_model_calls', 'max_calls', 'afp_ceiling',
                   'timeout_seconds', 'call_timeout_sum_seconds', 'formal_run_ready')}
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
