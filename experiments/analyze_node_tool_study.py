"""把三路线原始账本与配对结果渲染为可复核报告，不调用模型。"""
import argparse
from collections import Counter
import json
from pathlib import Path
from statistics import median


def report(result):
    simulated=result["simulated"]
    rows=[r for r in result["runs"] if r["phase"]=="comparison"]
    title="三路线禁网演练报告" if simulated else "三路线开发先导结果"
    lines=[f"# {title}","", "**模拟回复只验证执行与统计链路，不能说明模型质量、成本或时延收益。**" if simulated else
        "本结果限于三个构造开发任务、同一 DeepSeek V4 Flash 和三次重复；不代表最佳单模型或留出泛化。", "",
        f"批次状态：`{result['status']}`；协议：`{result['protocolSha256']}`。",
        f"本目录新增真实模型请求：{result['realModelCalls']}；按用量计算及未知预留合计：{result['actualOrReservedAfp']:.6f} AFP。",
        f"跨批累计请求：{result.get("cumulativeRealModelCalls",result["realModelCalls"])} / 135；累计费用及预留：{result.get("cumulativeActualOrReservedAfp",result["actualOrReservedAfp"]):.6f} / 286 AFP。",
        "AFP 是套餐用量，非人民币实付；供应商账单未独立确认。", "",
        "## 路线结果", "", "| 路线 | 完成/计划 | 字段值及引用均通过 | AFP 合计 | 任务时长中位数 ms |",
        "|---|---:|---:|---:|---:|"]
    for arm in ("one-shot","node-as-tool","dag"):
        group=[r for r in rows if r["arm"]==arm]
        timing=[r["taskElapsedMs"] for r in group if r.get("taskElapsedMs") is not None]
        duration=f"{median(timing):.1f}" if timing else "未取得"
        lines.append(f"| {arm} | {sum(r['status']=='completed' for r in group)}/9 | {sum(r['factStatus']=='pass' for r in group)}/{len(group)} | {sum(r['chargedOrReserved'] for r in group):.6f} | {duration} |")
    lines += ["", "## 错误归因诊断", "", "主判据和提示选择规则保持冻结；以下只区分字段值错误与引用列举不足，不放宽通过门槛。", "",
        "| 路线 | 完整交付 | 字段值全部正确 | 仅因引用扣分 |", "|---|---:|---:|---:|"]
    for arm in ("one-shot","node-as-tool","dag"):
        group=[r for r in rows if r["arm"]==arm and r["status"]=="completed"]
        value_ok=[r for r in group if r.get("checks") and all(c["status"]=="pass"
            for c in r["checks"] if not c["check"].endswith(":sources"))]
        citation_only=[r for r in value_ok if r["factStatus"]!="pass" and any(c["check"].endswith(":sources")
            and c["status"]=="fail" for c in r["checks"])]
        lines.append(f"| {arm} | {len(group)} | {len(value_ok)} | {len(citation_only)} |")
    reused=[r for r in result["runs"] if r.get("importedFrom")]
    if reused:
        lines += ["",f"接续已完成且参数一致的提示开发样本：{len(reused)} 个；保留原始协议、个案哈希与账本，不重放模型请求。"]
    lines += ["", "关键事实及引用通过不等于自由正文或整体任务通过；语义审查仍为 pending。",
        "没有产出、输出失败和未知用量保留在分母与原始记录中。", "", "## 按任务配对", "",
        "| 任务 | one-shot 事实通过/3 | node-as-tool 事实通过/3 | DAG 事实通过/3 |",
        "|---|---:|---:|---:|"]
    ids=sorted({r["taskId"] for r in result["runs"]})
    for tid in ids:
        values=[sum(r["factStatus"]=="pass" for r in rows if r["taskId"]==tid and r["arm"]==arm) for arm in ("one-shot","node-as-tool","dag")]
        lines.append(f"| {tid} | "+" | ".join(str(v) for v in values)+" |")
    lines += ["", "重复不是独立任务样本；本批是 3 个任务，每个任务每路线 3 次。", "", "## 翻转与机制覆盖", ""]
    for arm in ("node-as-tool","dag"):
        pairs=[p for p in result.get("pairs",[]) if p["arm"]==arm]
        counts=dict(Counter(p["factTransition"] for p in pairs))
        lines.append(f"- one-shot → {arm}：{json.dumps(counts,ensure_ascii=False)}；完整配对 {len(pairs)}/9。")
    nodes=[r for r in rows if r["arm"]=="node-as-tool"]
    lines.append(f"- 专家工具实际被调用的样本：{sum(r.get('expertCalls',0)>0 for r in nodes)}/{len(nodes)}；专家调用总数：{sum(r.get('expertCalls',0) for r in nodes)}。")
    dags=[r for r in rows if r["arm"]=="dag"]
    lines.append(f"- DAG 实际多节点样本：{sum(r.get('graphNodes',0)>1 for r in dags)}/{len(dags)}。未触发专家或拆分的样本单独标记，不能当作机制收益。")
    tuning=[r for r in result["runs"] if r["phase"]=="prompt-audit"]
    lines += ["", "## 基线开发与结论限制", "",
        f"基线提示开发使用 {len(tuning)} 个样本，AFP 记账值 {sum(r['chargedOrReserved'] for r in tuning):.6f}；所选提示：`{result.get('selectedPrompt','未选择')}`。",
        "提示按预注册的关键事实检查和费用选择；不是已获独立语义认证的最佳提示。",
        "开发和路线比较均使用本批开发材料，不把结果称为未见测试集。DAG 包含实时规划费用与等待；三路线均保留原始请求和最终输出。",
        "", "本批不宣布质量等价、总体优越或正式 Pareto 优势；Go/No-Go 仍为 `Insufficient-evidence`。",
        "真实运行时可以据事实错误、额外费用、等待时间和未触发机制形成带范围的先导判断。", "",
        "原始证据见同目录 `summary.json`、`frozen.json`、各个案的账本、请求、产物与会话事件。", ""]
    return "\n".join(lines)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--result-dir",type=Path,required=True)
    a=p.parse_args();data=json.loads((a.result_dir/"summary.json").read_text())
    (a.result_dir/"README.md").write_text(report(data))


if __name__=="__main__":main()
