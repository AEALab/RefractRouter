"""零调用重放Advisor/Escalation完整费用与独立标签；无付费开关。"""
import argparse
import json
from pathlib import Path

from refractrouter.review_benefit_replay import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    summary = run(args.source, args.output_dir)
    print(json.dumps({k: summary[k] for k in ('fixtureTaskPairs', 'empiricalIndependentTasks',
                                            'paidModelCalls', 'actualModelBenefitProven')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
