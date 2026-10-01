# Jev Choice 分动作门槛有限留出验收

## 决策与范围

官方 [Confidence 说明](https://docs.typesafe.ai/confidence)指出：`confidence` 是由
Choice 的整组选项概率计算出的集中程度；它与获选项 `probabilities[choice]` 不是
独立的两次判别。文档建议依动作风险设不同门槛，具体数值应在自己的数据上校准。

本批只核对 `jev-1.13.0` 的 Advisor、Escalation Choice。实验规则
`jev-choice-action-gate-v1-experimental` 同时要求 `confidence >= 0.55`，并按动作
要求获选项概率：Advisor 最终批准和 Escalation 最终放行为 0.80；Advisor 返工、
Escalation 缺陷／停滞接管和工具探索为 0.70。明确选择 `UNRESOLVED` 或
`UNCERTAIN` 时保留弃权。旧 Jev 调用保持原有 0.8 单门槛；Laya 与现有在线路径
均不受这项实验规则影响。

## 冻结预检与实际调用

- 新建 24 条留出题，Advisor、Escalation 各 12 条；包含中英文、明确合格、
  明确缺陷、证据不足及停滞。题集 SHA-256 为
  `60ad1eb4f534d529188854b7e69a7d7e740e7d5a746c8acb23ed9cc505cfc496`。
- 题面与人工预期在首次调用前写入
  [冻结题集](../../data/benchmarks/jev-choice-action-gate-holdout-v1.json)。
  标签由项目内部制定，尚未经过独立人审；这些是有界分类题，不是完整 Agent 任务。
- 零调用预检冻结模型版本、24 次请求、每次至多 64,000 输入 tokens、
  **0.064512 USD** 的最坏输入计价上界和零 HTTP 自动重试。
- 实际完成 24 次，模型与用量均有回执，无重试或未知用量；按官方输入 token 单价
  估算 **0.000596022 USD**，未与帐户帐单核对。原始结果在
  [逐题回执](holdout-v1/calls.jsonl)，[预检](holdout-v1/preflight.json)和
  [汇总](holdout-v1/summary.json)分别保存。

## 结果与反例

| 规则 | 24 题标签符合 | 错误批准／放行 |
| --- | ---: | ---: |
| 旧规则：获选项概率至少 0.80 | 22 | 0 |
| 全动作统一：`confidence >= 0.55` 且概率至少 0.70 | 22 | **1** |
| 实验分动作规则 | 22 | 0 |

全动作统一规则的误放行是 `a-zh-wrong-sum`：用户要求回答 `7+5`，候选错误地回答
`13`；Jev 原始首选为 `APPROVE`，获选项概率 **0.77**、`confidence` **0.70**。
统一双门槛会批准错误答案；旧规则和分动作规则均将其保守归为 `UNRESOLVED`。
这说明新增 `confidence` 下限并不能补救过低的批准概率门槛。

两个未符合标签的案例为上述错误算式（安全停止，但期望 `REDO`）和一条
结束轮停滞（安全接管，但原始分类在门槛下为 `UNCERTAIN`）。实验分动作规则
在这批新题上**没有改善最终动作符合数**。此前六份 DSH 工具输入的事后重放
由 3／6 提升到 5／6，只是开发阶段已观察材料，不得与这批新题合并为独立收益证明。

## 后续发布边界

全动作统一 0.55／0.70 因明确误放行予以否决。分动作门槛继续只作为 Jev
适配器的显式实验选项；默认未启用，也未接入 DSH 在线 Judge 设置。新题样本有限，
不能据零误放行断言生产误放行率可接受。若将来正式接入，应先经独立标签复核与
真实 Agent 工具任务验收，再按动作分别报告误放行、保守回退、成本和时延。
