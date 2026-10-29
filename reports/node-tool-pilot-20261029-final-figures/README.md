# 完整结果图表

两张图覆盖全部 27 个比较位置，没有缺失或补零。
费用和耗时保留未通过检查的样本，不表示同等质量下的资源收益。
检查矩阵区分字段及来源覆盖、来源未达和原 JSON 合同失败，不等于独立语义质量审查。

![费用与耗时](cost-latency.png)

![冻结检查矩阵](quality-matrix.png)

`plot-metadata.json` 绑定输入摘要、生成脚本哈希、Matplotlib 版本、全部坐标轴上界及计数。
`plotted-data.csv` 是完整 27 行绘图数据，原始摘要副本为 `summary.snapshot.json`。
中文、图例和全部柱高已目视验收，最大 3.500650 AFP、812.347 秒均完整可见，PNG/SVG 均保留。
若未来数据含失败且没有可比任务时间，用 × 显示，外层等待单列；不伪装为零秒。

使用同版本独立分析依赖，可在仓库根目录零模型调用复现：

```bash
uv run --no-project \
  --with-requirements reports/node-tool-pilot-20261029-final-figures/analysis-requirements.txt \
  python experiments/plot_node_tool_pilot.py \
  --result-dir reports/node-tool-pilot-20261029-live-05 --output-dir reports/新的完整图目录
```

需要时用 `--font` 指定支持中文的字体。未指定 `--allow-partial`，因此完整矩阵、基线及配对
未齐时会拒绝标成完整研究。图表分析环境与模型运行环境分离，原始结果和项目依赖不改变。
