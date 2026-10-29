"""只读生成三路线研究图表；缺失结果不补零，不改冻结主判据，不调用模型。"""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path

ARMS = ("one-shot", "node-as-tool", "dag")
NAMES = ("一次性回答", "按需专家", "规划路径")
TASKS = {"procurement-versions": "采购", "release-dependencies": "发布排程", "ledger-idempotency": "流水核对"}
LABELS = {"pass": "字段及来源\n覆盖通过", "sources": "来源覆盖\n未达", "values": "字段值\n错误",
          "format": "JSON 合同\n未通过", "execution": "执行\n未完成", "unassessed": "字段检查\n未评", "missing": "未收录"}
COLORS = {"pass": "#D5EDDC", "sources": "#FFF0C9", "values": "#F8D5D3", "format": "#E8DDF5",
          "execution": "#F8D5D3", "unassessed": "#E1E6EB", "missing": "#F1F3F5"}


def category(row):
    if row is None:
        return "missing"
    if row["status"] != "completed":
        return "execution"
    if row.get("qualityError"):
        return "format"
    checks = row.get("checks", [])
    values = [c for c in checks if not c["check"].endswith(":sources")]
    if not values:
        return "unassessed"
    if any(c["status"] == "fail" for c in values):
        return "values"
    if any(c["status"] != "pass" for c in values):
        return "unassessed"
    if row["factStatus"] == "pass":
        return "pass"
    if any(c["status"] == "fail" and c["check"].endswith(":sources") for c in checks):
        return "sources"
    return "unassessed"


def collect(summary, frozen, *, allow_partial=False):
    if summary.get("simulated") is not False:
        raise ValueError("真实结果图不能接受演练样本")
    if summary["protocolSha256"] != frozen["protocolSha256"] or set(frozen["tasks"]) != set(TASKS):
        raise ValueError("结果与冻结协议或任务身份不符")
    rows = {}; expected = {(tid, repeat, arm) for tid in TASKS for repeat in range(1, 4) for arm in ARMS}
    for row in summary["runs"]:
        if row["phase"] != "comparison":
            continue
        key = (row["taskId"], row["repeat"], row["arm"])
        if key not in expected or key in rows:
            raise ValueError("比较样本身份重复或超出冻结矩阵")
        rows[key] = row
    complete = (summary["status"] == "completed-development-pilot" and set(rows) == expected
                and len(summary["runs"]) == 45 and len(summary.get("pairs", [])) == 18
                and sum(r["phase"] == "prompt-audit" for r in summary["runs"]) == 18)
    if not complete and not allow_partial:
        raise ValueError("完整研究尚未完成；阶段图须显式使用 --allow-partial")
    return rows, complete


def metric(row, key):
    value = row.get(key) if row else None
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("图表指标须为有限非负数，不能把未知值画成零")
    return value / 1000 if key in ("taskElapsedMs", "outerElapsedMs") else value


def render(result_dir, output_dir, *, snapshot=None, allow_partial=False, font=None):
    source = Path(snapshot) if snapshot else Path(result_dir) / "summary.json"
    raw = source.read_bytes(); summary = json.loads(raw)
    frozen = json.loads((Path(result_dir) / "frozen.json").read_text())
    rows, complete = collect(summary, frozen, allow_partial=allow_partial)
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt, font_manager, patches
    candidates = [Path(font)] if font else [Path(p) for p in (
        "/System/Library/Fonts/STHeiti Medium.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")]
    font_path = next((p for p in candidates if p.is_file()), None)
    if font_path is None:
        raise ValueError("图表需要中文字体，请用 --font 指定可用字体；原始实验结果不受影响")
    font_manager.fontManager.addfont(str(font_path))
    plt.rcParams["font.family"] = font_manager.FontProperties(fname=font_path).get_name()
    plt.rcParams.update({"font.size": 11, "axes.unicode_minus": False, "savefig.facecolor": "white"})
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=False)
    (out / "summary.snapshot.json").write_bytes(raw)
    stage = "完整开发先导" if complete else f"阶段图：{len(rows)}/27，尚未完成"
    route_colors = ("#2874A6", "#15856D", "#C06A26")
    fig, axes = plt.subplots(2, 3, figsize=(16, 8), sharey="row")
    for column, (tid, title) in enumerate(TASKS.items()):
        for line, key in enumerate(("chargedOrReserved", "taskElapsedMs")):
            ax = axes[line, column]
            for arm_index, arm in enumerate(ARMS):
                for repeat in range(1, 4):
                    row = rows.get((tid, repeat, arm)); value = metric(row, key)
                    x = repeat + (arm_index - 1) * .24
                    if value is None:
                        ax.text(x, .025, "—" if row is None else "×", transform=ax.get_xaxis_transform(), ha="center", color="#9098A2")
                        continue
                    ax.bar(x, value, .22, color=route_colors[arm_index],
                           hatch="//" if key == "chargedOrReserved" and not row.get("costKnown", False) else None)
                    ax.annotate(f"{value:.2f}" if line == 0 else f"{value:.0f}", (x, value),
                                xytext=(0, 4), textcoords="offset points", ha="center", fontsize=9)
            ax.set_xticks((1, 2, 3), ("第 1 轮", "第 2 轮", "第 3 轮"))
            ax.set_xlim(.5, 3.5); ax.spines[["top", "right"]].set_visible(False)
            ax.grid(axis="y", alpha=.15); ax.set_axisbelow(True)
            if line == 0:
                ax.set_title(title)
            if column == 0:
                ax.set_ylabel("AFP：结算或未知预留" if line == 0 else "完整任务秒数")
    rendered_bounds = {}
    # 全部柱子加入后再统一共享坐标轴；逐子图提前 set_ylim 会关闭后续自动扩展，截掉高柱。
    for line, key in enumerate(("chargedOrReserved", "taskElapsedMs")):
        values = [metric(row, key) for row in rows.values() if metric(row, key) is not None]
        maximum = max(values, default=0)
        for ax in axes[line]:
            ax.set_ylim(0, max(1, maximum * 1.2))
        actual_upper = [ax.get_ylim()[1] for ax in axes[line]]
        if any(upper < maximum for upper in actual_upper):
            raise ValueError("共享坐标轴截断了原始数值，拒绝导出")
        rendered_bounds[key] = {"原始数据最大值": maximum, "各子图实际纵轴上界": actual_upper}
    fig.suptitle("三路线费用与耗时｜" + stage, fontsize=17, y=.985)
    fig.legend([patches.Patch(color=c) for c in route_colors], NAMES, loc="upper center", ncol=3, bbox_to_anchor=(.5, .95))
    fig.text(.5, .025, "包含检查未过样本，不表示同等质量收益；时长含规划和专家。—未收录；×已收录但无可比指标，详见原账本。斜线为费用预留。", ha="center", fontsize=10)
    fig.subplots_adjust(top=.84, bottom=.10, hspace=.27, wspace=.12)
    for suffix in ("png", "svg"):
        fig.savefig(out / ("cost-latency." + suffix), dpi=160)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(11, 8))
    groups = [(tid, repeat) for tid in TASKS for repeat in range(1, 4)]
    for y, (tid, repeat) in enumerate(groups):
        for x, arm in enumerate(ARMS):
            kind = category(rows.get((tid, repeat, arm)))
            ax.add_patch(patches.Rectangle((x - .5, y - .5), 1, 1, facecolor=COLORS[kind], edgecolor="white", linewidth=3))
            ax.text(x, y, LABELS[kind], ha="center", va="center", fontsize=11, color="#243545")
    ax.set(xlim=(-.5, 2.5), ylim=(8.5, -.5))
    ax.set_xticks(range(3), NAMES); ax.xaxis.tick_top(); ax.tick_params(length=0)
    ax.set_yticks(range(9), [f"{TASKS[tid]} · 第 {repeat} 轮" for tid, repeat in groups])
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.suptitle("冻结检查结果｜" + stage, fontsize=17, y=.98)
    fig.text(.5, .025, "字段值、来源覆盖与 JSON 合同分别显示；不等于自由正文或独立语义审查通过。三个任务的重复不是独立任务。", ha="center", fontsize=10)
    fig.subplots_adjust(top=.87, bottom=.08, left=.23, right=.97)
    for suffix in ("png", "svg"):
        fig.savefig(out / ("quality-matrix." + suffix), dpi=160)
    plt.close(fig)
    with (out / "plotted-data.csv").open("w") as stream:
        writer = csv.writer(stream); writer.writerow(["任务", "轮次", "路线", "显示类别", "AFP结算或预留", "完整任务秒数", "费用已知", "外层秒数含冷启动", "执行状态"])
        for tid, repeat in groups:
            for arm in ARMS:
                row = rows.get((tid, repeat, arm))
                writer.writerow([tid, repeat, arm, category(row), metric(row, "chargedOrReserved"),
                                 metric(row, "taskElapsedMs"), row.get("costKnown") if row else None,
                                 metric(row, "outerElapsedMs"), row.get("status") if row else None])
    metadata = {"说明": "只读可视化；类别只解释原检查，不重新评分。", "完整研究": complete,
                "比较样本": len(rows), "缺失比较样本": 27 - len(rows), "原摘要Sha256": hashlib.sha256(raw).hexdigest(),
                "协议Sha256": summary["protocolSha256"], "Matplotlib版本": matplotlib.__version__,
                "生成脚本Sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "中文字体": str(font_path) if font_path.is_file() else "系统默认字体",
                "实际坐标轴核对": rendered_bounds,
                "时长口径": "仅绘制 taskElapsedMs，缺失不补零；失败外层等待在 CSV 单列，不伪装成完成时长",
                "类别计数": dict(Counter(category(rows.get((tid, repeat, arm))) for tid, repeat in groups for arm in ARMS))}
    (out / "plot-metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-dir", type=Path, required=True); parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--summary-snapshot", type=Path); parser.add_argument("--font", type=Path)
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    print(json.dumps(render(args.result_dir, args.output_dir, snapshot=args.summary_snapshot,
                           allow_partial=args.allow_partial, font=args.font), ensure_ascii=False))


if __name__ == "__main__":
    main()
