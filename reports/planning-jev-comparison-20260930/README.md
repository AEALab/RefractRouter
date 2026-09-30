# 规划路由 Jev 与 Laya-MLX 固定题对照

官方 Jev 固定版本：`jev-1.13.0`；共 78 次请求，
依据回执输入 tokens 和官方公开单价估算费用 0.002090130 USD；账户账单尚未核对。
题集、问题描述与原先 Laya 验收相同；没有修改阈值或挑选案例。

| 用途 | 案例数 | Jev 符合预期 | Laya 符合预期 | Jev 单题中位耗时 | Laya 单题中位耗时 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Task 开发题 | 6 | 5 | 3 | 417.9 ms | 13.6 ms |
| Task 留出题 | 8 | 6 | 6 | 423.6 ms | 17.8 ms |
| Stage 逐轮选模 | 16 | 7 | 4 | 412.0 ms | 89.1 ms |
| Advisor 回复审核 | 24 | 20 | 7 | 409.5 ms | 28.4 ms |
| Escalation 候选审核 | 24 | 22 | 5 | 416.9 ms | 21.4 ms |

各用途判定语义不同，符合预期次数不能合计为统一准确率。
Jev 耗时包含网络往返，Laya 耗时是本机推论；两者可作为实际等待的参考，但不能仅凭这一批固定题证明完整任务质量或成本收益。

选择概率是当前选项的概率；Jev 返回的 `confidence` 是分布确定性。本批按原有选择概率与阈值映射，原始答案保存在 `calls.jsonl`。

本批只覆盖规划路由的 Task、Stage、Advisor、Escalation Judge。DAG 是否拆分属于自动路由，不在这次规划路由接线范围内。

Laya 对照原始记录见 [PR #163](https://github.com/AEALab/RefractRouter/pull/163) 的 `reports/local-jev-multiscenario-20260930/`。

参考：[官方 API](https://docs.typesafe.ai/api)、[模型、容量与价格](https://docs.typesafe.ai/models)、[置信度定义](https://docs.typesafe.ai/confidence)。
