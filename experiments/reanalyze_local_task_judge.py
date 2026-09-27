"""按修订后的验收语义重算已冻结的本地 Judge 记录，不改写原始输出。"""

import argparse
import json
from pathlib import Path


def analyze(labels, reports):
    by_id = {row["id"]: row for row in labels["cases"]}
    if len(by_id) != len(labels["cases"]):
        raise ValueError("验收标签含重复题目 ID")
    result = []
    for path in reports:
        report = json.loads(path.read_text())
        grouped = {name: {"total": 0, "acceptable": 0, "selected": 0}
                   for name in ("capability-probe", "judge-unclear", "judge-equal")}
        cases = []
        for row in report["cases"]:
            label = by_id.get(row["id"])
            if label is None:
                raise ValueError(f"缺少题目 {row['id']} 的修订标签")
            group = label["group"]
            outcome = row["outcome"]
            accepted = outcome in label["acceptable"]
            useful = outcome in label.get("usefulSelection", [])
            grouped[group]["total"] += 1
            grouped[group]["acceptable"] += int(accepted)
            grouped[group]["selected"] += int(useful)
            cases.append({"id": row["id"], "group": group, "outcome": outcome,
                          "acceptable": accepted, "usefulSelection": useful,
                          "reason": label["reason"]})
        result.append({"source": str(path), "mode": report.get("mode", "production"),
                       "groups": grouped, "cases": cases})
    return {"schemaVersion": labels["schemaVersion"], "analyses": result,
            "limits": "capability-probe 仅检验提问接口；其结果不计入产品选模质量。"
                      "judge-equal 的备用属于安全结果，有效选模另列。"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("reports", type=Path, nargs="+")
    args = parser.parse_args()
    output = analyze(json.loads(args.labels.read_text()), args.reports)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
