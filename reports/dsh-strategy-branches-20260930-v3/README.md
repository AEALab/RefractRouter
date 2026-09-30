# DSH 复杂策略关键分支验收报告

## 验收目标

前一批稳定性验收已覆盖六种策略的日常正常路径。本批补充 Stage、Composite、Advisor
和 Escalation 的关键分支，确认策略会按各自规则完成切换、保持、恢复、返工或接管，
而不只完成普通回复。

本批于 2026-09-30 使用实际 DSH 客户端、RefractRouter 标准 Base URL 入口和 Ark Agent
Plan 路线执行。所有派发均保持零 HTTP 自动重试、关闭委派，并在冻结摘要变化时拒绝运行。

## 冻结范围

| 策略 | 次数 | 关键路径 | 真实模型调用 | 受控夹具调用 |
| --- | ---: | --- | ---: | ---: |
| Stage | 6 | 高效模型开始、重复失败升级、保持、恢复高效模型 | 30 | 0 |
| Composite | 6 | Task 初选一次、Stage 接管、保持、返回常用模型 | 30 | 6 |
| Advisor | 6 | 错误候选、真实审核要求返工、工具续接、复审通过 | 12 | 18 |
| Escalation | 6 | 错误候选、真实 Judge 判定、强模型接管并锁定 | 18 | 6 |
| **合计** | **24** |  | **90** | **30** |

实际模型为 `ark/deepseek-v4-flash` 和 `ark/deepseek-v4.1-flash`。Composite 的 Task
初选使用明确标记的本地夹具，以固定常用模型并稳定验证后续切换；前一批 24 条 Composite
正常路径已经保留真实 Task Judge 证据。Advisor 的执行候选和 Escalation 的起始错误候选
使用明确标记夹具，审核、接管及接管后的工具续接均调用真实模型。

## 结果

24 条流程全部完成，90 次真实模型调用均取得可核对用量，未出现未知用量、自动重试或
重复派发。

| 策略 | 通过 | 实际 AFP | 关键结果 |
| --- | ---: | ---: | --- |
| Stage | 6／6 | 2.16005 | 六次均完成升级、保持和恢复 |
| Composite | 6／6 | 2.17475 | 六次均只分类一次并完成接管循环 |
| Advisor | 6／6 | 0.45115 | 六次均完成两次真实审核和一次返工 |
| Escalation | 6／6 | 1.46765 | 六次均由真实 Judge 触发并锁定强模型 |
| **合计** | **24／24** | **6.25360** |  |

Stage 每次的实际执行模型序列均为：

```text
deepseek-v4-flash
→ deepseek-v4-flash
→ deepseek-v4.1-flash
→ deepseek-v4.1-flash
→ deepseek-v4-flash
```

对应决策为 `no-signal → ambiguous → repeated-failure → capable-hold → ambiguous`。

Composite 每次的执行模型序列与 Stage 相同，Task 分类只发生一次；后续决策依次为
`composite-task-selected → composite-ambiguous-base → composite-repeated-failure →
composite-takeover-hold → composite-return-base`。

Advisor 每次均经历执行候选、真实审核、返工、DSH 原生工具、修正回复及真实复审，
最终状态为 `approved`，审核次数为 2，返工次数为 1。Escalation 每次均丢弃错误候选，
由真实 Judge 触发接管，并由 `deepseek-v4.1-flash` 完成工具调用和续接；任务内接管锁定为真。

## 验收总量

与前一批正常路径合并后，六策略累计完成：

| 策略 | 正常路径 | 关键分支 | 合计 |
| --- | ---: | ---: | ---: |
| Static | 12 | 0 | 12 |
| Stage | 24 | 6 | 30 |
| Task | 20 | 0 | 20 |
| Composite | 24 | 6 | 30 |
| Advisor | 24 | 6 | 30 |
| Escalation | 24 | 6 | 30 |
| **合计** | **128** | **24** | **152** |

Static 与 Task 的核心行为发生在任务开始时，前一批已经分别覆盖固定模型和真实 Task
选模。四个逐轮或审核策略则增加了本批关键分支测试。

## 费用与停止记录

本批冻结预检按请求上界计算的新增最坏费用为 1898.2944 AFP，连同既有用量和待核对
预留的最坏累计值为 2136.0584 AFP，低于用户授权的累计 5000 AFP。

本批实际新增费用为 6.25360 AFP。纳入先前已确认费用后，累计已确认费用为
243.78275 AFP；另有 0.23485 AFP 待核对预留，合计占用 244.01760 AFP。

在正式 v3 批次前保留了两次停止记录：

- v1 在 Advisor 第二条流程发现夹具复用了工具调用 ID，Router 的防重放检查正确阻断；
  已发生真实费用为 4.59185 AFP。
- v2 的 Composite 真实 Task Judge 在 2／6 条任务中直接选择接管模型，行为符合策略，
  但无法覆盖预定的“高效到接管再恢复”分支，因此停止该批；已发生真实费用为
  5.32970 AFP。

两次停止记录均未覆盖或删除，费用已计入既有累计值。v3 通过任务级工具调用 ID 和受控
Task 初选，固定本次关键分支；这不会被解释为真实 Judge 的质量证据。

## 证据边界

- DSH 工具由宿主执行，Router 只消费结构化执行证据、选模、审核和结算模型费用。
- Stage 与 Composite 的重复失败由受控且带可信状态的宿主事实产生，不从工具正文猜测。
- 受控错误候选只用于验证 Advisor 和 Escalation 的状态机，不证明自然任务质量收益。
- 本报告证明已冻结分支的产品行为和费用可核对，不证明这些策略普遍优于 Static。
- Codex 与 Hermes 的普通 Base URL 路径仍不会从缺少可信状态的工具正文推断失败；两端的
  可选结构化证据适配另行验收。

## 证据文件

- [零调用预检](preflight.json)
- [汇总结果](summary.json)
- [六策略正常路径报告](../dsh-strategy-stability-20260929-v3/README.md)

