# 规划路由 Jev／Laya 固定题对照预检

## 范围

本批只重跑规划路由中的结构化 Judge 题集，沿用既有 Laya-MLX 的题目、问题描述、
阈值及逐题预期。不调用自动路由的 DAG 拆分，也不把判别题准确率等同于真实任务完成率。

| 用途 | 题集 | 案例数 | 既有 Laya 符合预期 |
| --- | --- | ---: | ---: |
| Task 开发题 | `data/task-judge-audit-20260926.json` | 6 | 3 |
| Task 留出题 | `data/task-judge-holdout-20260926.json` | 8 | 6 |
| Stage 逐轮选模 | `data/stage-judge-holdout-v2.json` | 16 | 4 |
| Advisor 回复审核 | `data/benchmarks/advisor-judge-v1.json` | 24 | 7 |
| Escalation 候选审核 | `data/benchmarks/escalation-judge-v1.json` | 24 | 5 |

共 78 条，最多 78 次 Jev 请求，HTTP 自动重试次数为零。
Jev 固定为 `jev-1.13.0`，不使用可能漂移的 `jev-latest` 别名。
原始 Laya 记录来自本项目 [PR #163](https://github.com/AEALab/RefractRouter/pull/163) 的
`reports/local-jev-multiscenario-20260930/`；比较按案例 ID 对齐。

## 费用与停止条件

[官方模型资料](https://docs.typesafe.ai/models)列出每百万输入 tokens 为
0.042 USD、输出 tokens 免费，并标注每请求 64k tokens 容量。按 78 次请求全部达到
64k 输入 tokens 的保守上界，本批为 **0.209664 USD**；运行程序要求显式提供
不低于此上界的 USD 限额。此项与既有 AFP 授权分账。

每条调用保存实际模型、输入和输出用量、USD 费用、耗时、原始结构化答案及映射结果。
认证、传输、模型版本、答案或用量异常时停止整批，不自动重发；未知用量保留该次
请求的费用上界待核对。Jev API 密钥仅在运行时从隐藏输入读取，不写入配置、命令行、
报告或仓库。

Jev 的 `confidence` 是概率分布的确定性，不是所选项概率，也不是任务成功率。
为保持同题可比，现有路由映射继续使用所选项概率和原有阈值，另行保留原始
`confidence`。接口字段见[官方 API](https://docs.typesafe.ai/api)与
[置信度说明](https://docs.typesafe.ai/confidence)。

## 验证状态

零调用预检确认 78 条固定案例及上述费用上界。Jev HTTP 合同、失败停止、
版本固定和比较格式的无网络测试已通过。用户随后授权本批最高 0.21 USD；
78 条真实调用已完成，逐题记录和分析见
[`planning-jev-comparison-20260930/`](planning-jev-comparison-20260930/README.md)。
