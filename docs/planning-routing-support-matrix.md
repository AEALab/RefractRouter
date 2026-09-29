# 规划路由支持矩阵

## 状态定义

| 标记 | 含义 |
| --- | --- |
| 已验收 | 已使用实际客户端或真实模型完成所列流程 |
| 合同通过 | 状态机和客户端合同使用确定性夹具通过，未宣称自然任务收益 |
| 实验 | 接线存在，但 Judge 质量或宿主能力尚未达到日常使用门槛 |
| 未验收 | 尚无足够证据支持该组合 |

本表记录截至 2026-09-30 的证据。Router 只负责选模、审核候选和模型费用；工具执行、
权限、上下文、委派和任务推进仍由客户端负责。表中的“真实”表示真实客户端及上游路线，
不表示策略已证明优于固定模型。

## 策略与客户端

| 策略 | DSH | Codex CLI | Hermes |
| --- | --- | --- | --- |
| Static | 真实模型与原生工具往返已验收 | 实际 CLI 工具往返已验收；真实模型路线已验收 | 实际 Agent 循环与真实模型工具往返已验收 |
| Stage | 真实执行模型与 DSH 结构化失败证据完成切换、保持和恢复 6／6；正常路径另完成 24／24 | 真实无信号工具续接已验收；可选证据适配器通过隔离验收，日常 profile 尚未启用 | 真实无信号工具续接已验收；可选证据插件通过隔离验收，日常 profile 尚未启用 |
| Task | DSH 真实选模与工具续接已验收；当前 Laya 路线仍为实验 | 标准接口合同通过，尚未单独完成真实客户端矩阵 | 标准接口合同通过，尚未单独完成真实客户端矩阵 |
| Composite | 真实执行模型完成接管、保持和恢复 6／6；Task 初选使用受控夹具，真实初选正常路径另完成 24／24 | 真实初始选模与工具续接已验收；动态切换适配器未启用到日常 profile | 真实初始选模与工具续接已验收；动态切换插件未启用到日常 profile |
| Advisor | 真实 Judge 完成返工与复审 6／6，候选执行使用受控夹具；正常路径另完成 24／24 | 真实正常审核与工具续接已验收；返工复审合同通过 | 真实正常审核与工具续接已验收；返工复审合同通过 |
| Escalation | 真实 Judge 与强模型完成接管、工具续接和锁定 6／6，起始错误候选使用受控夹具；正常路径另完成 24／24 | 标准接口合同通过，尚未完成真实接管矩阵 | 标准接口合同通过，尚未完成真实接管矩阵 |

## Judge 与媒体

| 能力 | 当前状态 | 发布说明 |
| --- | --- | --- |
| 轻量 LLM Judge | Task、Advisor、Escalation 与 Composite 已接通；各自验收范围不同 | 只使用策略自己的判别合同，不跨策略解释分数 |
| 本地 Laya-MLX | Task、Stage、Composite、Advisor 和 Escalation 可配置 | 当前固定 revision 的质量未达到日常门槛，统一显示实验状态 |
| 图片输入 | DSH 有原生内容块，部分模型目录已声明能力 | 尚未完成规划路由的完整真实矩阵 |
| 图片生成／编辑 | Seedream 路线已保存接线与官方价格 | 尚未完成真实付费接口验收，不派发受管生成请求 |
| 影片输入／输出 | 未接通 | DSH 0.1.5 尚无完整影片内容块、上传、播放器和持久化合同 |
| 子 Agent 共享预算 | 未完成 | P6 独立验收，不计入当前主 Agent 硬预算覆盖范围 |

## Composite 完整序列

规则模式的冻结序列已经在 Python 核心、标准 Base URL 和 DSH 原生事件合同中通过：

1. Task Judge 只在任务开始时调用一次，并选出常用模型；
2. 第一次可信失败仍使用常用模型；
3. 第二次同指纹可信失败切换接管模型；
4. 下一次执行保持接管模型；
5. 没有新困难证据时返回常用模型。

冻结合同中的模型调用序列为 `judge → small → large → large → small`，执行决策依次为
`composite-task-selected → composite-repeated-failure → composite-takeover-hold →
composite-return-base`。DSH 关键分支已使用受控 Task 初选和真实执行模型重复完成 6 次；
这是功能证据，不用于证明成本或质量收益。

## 使用边界

- 纯 Base URL 的普通工具结果通常没有可信退出状态。Router 会标为无法分类，并保持安全的
  默认路线，不从正文里的“失败”猜测执行结果。
- Codex CLI 与 Hermes 的可选工具证据适配已经通过隔离无付费验收；本轮按用户要求没有写入
  两者的日常配置。
- DSH 当前 profile 的六种策略零调用诊断全部可用，默认策略为 Stage。媒体诊断仍明确显示
  尚未通过真实接口验收。

证据索引：

- [本轮产品就绪验收](../reports/planning-routing-product-readiness-20260929/README.md)
- [六策略正常路径稳定性验收](../reports/dsh-strategy-stability-20260929-v3/README.md)
- [复杂策略关键分支验收](../reports/dsh-strategy-branches-20260930-v3/README.md)
- [三客户端 Stage 验收](../reports/stage-three-client-acceptance-20260927/README.md)
- [Advisor 与 Composite 验收](../reports/advisor-composite-product-acceptance-20260929/README.md)
- [Escalation 验收](../reports/escalation-acceptance-20260927/README.md)
- [客户端工具证据适配](client-tool-evidence.md)
