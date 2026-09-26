"""Task 小样本真实验收零调用预检；只读取冻结资料，不联系模型服务。"""

import argparse
import hashlib
import json
from pathlib import Path

from refractrouter.ark_plan import catalog


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "data/benchmarks/task-quality-pilot-v3.json"


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def preflight(protocol, tasks, pricing):
    if protocol.get("schemaVersion") != "task-quality-pilot-v3":
        raise ValueError("Task 小样本协议版本无效")
    by_id = {item["id"]: item for item in tasks["tasks"]}
    if len(by_id) != len(tasks["tasks"]):
        raise ValueError("冻结任务 ID 重复")
    calibration, holdout = protocol["calibration"], protocol["holdout"]
    if (not calibration or not holdout or len(set(calibration + holdout)) != len(calibration + holdout)
            or any(task_id not in by_id for task_id in calibration + holdout)):
        raise ValueError("校准与保留任务必须存在且互不重叠")
    limits = protocol["limits"]
    if limits["httpRetries"] != 0 or limits["delegation"] is not False:
        raise ValueError("本批次必须关闭 HTTP 重试和委派")
    model_rows = {item["model_id"]: item for item in pricing["models"]}
    models = protocol["models"]
    selected = {arm: models[arm]["model"] for arm in ("static-flash", "static-v4.1-flash")}
    if set(models["task-choice-v2"]["pool"]) != set(selected.values()):
        raise ValueError("Task 模型池必须与两条固定路线一致")
    if models["task-choice-v2"]["fallback"] not in selected.values():
        raise ValueError("指定备援不在池内")
    if models["task-choice-v2"]["method"] != "choice-v2":
        raise ValueError("判别方法与本批次不符")
    per_call = {}
    for model_id in selected.values():
        row = model_rows.get(model_id)
        if not row or row["pricing"]["unit"] != "afp-per-10000-tokens":
            raise ValueError(f"{model_id} 缺少可核对 AFP 价格")
        if limits["maxOutputTokensPerCall"] > row["max_output_tokens"]:
            raise ValueError(f"{model_id} 输出上限超过目录")
        # 运行时 request_input_bound 以完整 JSON 的 UTF-8 字节数 + 256 预留，
        # 不能把安全上限的字节数除以 4 当作真实 token 上界。
        input_bound = limits["maxRequestBytesPerCall"] + 256
        if input_bound + limits["maxOutputTokensPerCall"] > row["context_window_tokens"]:
            raise ValueError(f"{model_id} 请求上限超过上下文")
        price = row["pricing"]
        per_call[model_id] = round((input_bound * price["input_coefficient"]
                                    + limits["maxOutputTokensPerCall"] * price["output_coefficient"]) / 10000, 6)
    runs = []
    for split, task_ids in (("calibration", calibration), ("holdout", holdout)):
        for task_id in task_ids:
            for arm in protocol["arms"][split]:
                if arm not in (*selected, "task-choice-v2"):
                    raise ValueError(f"未知实验路线：{arm}")
                model = selected[arm] if arm in selected else max(
                    selected.values(), key=lambda item: per_call[item])
                runs.append({"split": split, "taskId": task_id, "taskDigest": digest(by_id[task_id]),
                             "arm": arm, "costUpperAfp": round(per_call[model] * limits["maxCallsPerRun"], 6)})
    production_upper = round(sum(row["costUpperAfp"] for row in runs), 6)
    prior_charged = protocol.get("priorChargedAfp", 0)
    if type(prior_charged) not in (int, float) or prior_charged < 0:
        raise ValueError("先前已结算 AFP 无效")
    frozen = {"schemaVersion": "task-quality-pilot-preflight-v3", "realModelCalls": 0,
              "protocolDigest": digest(protocol), "taskSourceDigest": digest(tasks),
              "pricingSnapshot": pricing["snapshot_date"], "pricingSource": pricing["pricing_url"],
              "modelCostUpperPerCallAfp": per_call, "runs": runs,
              "maximumRuns": len(runs), "maximumModelCalls": len(runs) * limits["maxCallsPerRun"],
              "maximumProductionAfp": production_upper,
              "priorChargedAfp": prior_charged,
              "maximumIncludingPriorAfp": round(production_upper + prior_charged, 6),
              "judgeApiAfp": 0,
              "limitations": ["按运行时完整请求 JSON 字节数 + 256 的输入预留公式计算，覆盖冻结输入和输出上限。",
                              "本地 Judge 不计 API AFP，另记推论时间和次数。",
                              "预检未授权或执行任何真实模型调用；质量结论须由结果记录支持。"]}
    return {**frozen, "preflightDigest": digest(frozen)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    protocol = json.loads(PROTOCOL.read_text())
    task_source = ROOT / protocol["taskSource"]
    if not task_source.resolve().is_relative_to(ROOT):
        raise ValueError("任务来源路径越界")
    result = preflight(protocol, json.loads(task_source.read_text()), catalog())
    content = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        if args.output.exists():
            raise ValueError("预检输出已存在，拒绝覆盖")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content)
    else:
        print(content, end="")


if __name__ == "__main__":
    main()
