# 规划路由产品就绪验收

## 范围

本轮按用户指定完成三项工作：DSH 实际界面与配置验收、Composite 完整切换验收、
DSH／Codex CLI／Hermes 支持矩阵。Codex CLI 和 Hermes 的日常工具证据适配安装留待后续，
本轮没有修改两者的 profile。

验收环境为 DSH `0.1.5-rc.3`、DSH 插件 `0.29.0`、已安装 Python 核心 `0.15.4`，
规划配置为 `refractagent-planning-v6`。本轮 Composite 验收使用确定性上游，真实模型调用数和
新增 AFP 均为 0。

## DSH 实际界面

实际浏览器确认：

- “对话、轨迹、任务 DAG、路由轨迹”四个页签同时存在；
- “RefractAgent 规划路由”和“RefractAgent 自动路由”是两张独立插件设置卡；
- 模型菜单可选择 Stage、Task、Composite、Advisor、Escalation、Static 六种路由模式；
- 路由轨迹显示模型、推理等级、用途、交付状态、单次与累计费用、时延、决策原因和证据；
- 默认策略保存并恢复为 Stage，现有会话仍使用任务启动时冻结的策略；
- 零调用诊断显示六种策略全部可用；媒体路线继续明确显示尚未通过真实接口验收。

首次诊断发现 DSH 的手工 Ark 模型 `glm-5.3-flash` 没有声明推理等级，而 provider 默认使用
`high`，导致 Composite 和 Escalation 在派发前被阻断。核对本地模型目录后，为该 DSH 模型
补充 `low / medium / high / xhigh / max`，没有修改模型、凭证、预算或信任策略。修复前的
DSH 设置已另存本机备份。此前插件 UI 与旧已安装核心的字段差异也通过重新安装当前核心解决。

## Composite 完整切换

三层确定性验收均通过：

| 层级 | 覆盖 | 结果 |
| --- | --- | --- |
| Python 策略核心 | Task 一次选模、重复失败、接管保持、返回常用模型 | 通过 |
| 标准 Base URL | 版本化可信工具证据及跨请求状态 | 通过 |
| DSH 插件 | 原生 `tool/call`、`tool/result`、退出码、消息配对及路由轨迹 | 通过 |

冻结调用序列为 `judge → small → large → large → small`；执行决策为
`composite-task-selected → composite-repeated-failure → composite-takeover-hold →
composite-return-base`。Task Judge 只发生一次。第一次同类失败没有立即升级，第二次同指纹
失败触发接管，接管保持一次，之后无新困难证据时返回常用模型。

定向测试结果：Python 核心与标准接口 `2 passed`；DSH Composite 契约 `3 passed`。
这些结果证明状态机与客户端合同，不证明自然任务质量或成本收益。

## 发布边界

完整支持状态见 [规划路由支持矩阵](../../docs/planning-routing-support-matrix.md)。当前可以明确发布：

- DSH 六种策略均可配置，零调用诊断通过；
- Composite 在 DSH 原生可信事件下可以完成完整动态切换；
- Codex CLI 与 Hermes 的普通 Base URL 工具续接可用；动态失败切换需要可选证据适配；
- 两个适配器已有隔离验收证据，但按本轮范围没有安装进日常 profile；
- 本地 Laya、媒体路线、Escalation 全真实接管矩阵和 P6 子 Agent 共享预算仍按支持矩阵标示。

机器可读摘要见 [验收记录](acceptance.json)。
