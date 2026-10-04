# 规划路由产品收尾核对

核对日期：2026-10-04。范围为六策略现有验收证据、当前 DSH 配置、设置与运行说明。
这次不新增付费模型调用，不把旧实验结果改写成新后端的质量结论。

## 当前安装与配置

- DSH CLI 为 `0.1.5-rc.3`；本次源码核心为 `0.15.8`、插件为 `0.29.5`。
- 用户原有 `web` profile 继续使用链接到本仓库的插件；没有新建隔离 profile，也没有
  更改 provider、凭证、生产预算或已有会话。
- 规划路由已启用，默认策略为规则 Stage。Jev 渠道为 OpenRouter，使用已登记的可信云
  策略；Advisor／Escalation 的实验性分动作门槛未启用。
- 当前 Task Judge 为本地 Laya；Composite 为 LLM Task Judge 加规则 Stage；
  Advisor 和 Escalation 使用 OpenRouter Jev。
- 将 profile 配置经 JSON 序列化后交给 Python 零调用预检，六种策略均显示可执行。
  YAML 解析器把媒体价格的查证日期读作日期对象；序列化步骤与宿主传输一致，避免把
  本地解析类型差异误报为用户配置损坏。

## 已有验收与结论

2026-09-29 的六策略正常路径为 128／128，使用 215.58545 AFP；2026-09-30
的 Stage、Composite、Advisor、Escalation 关键分支另为 24／24，使用 6.25360 AFP。
关键分支包含受控工具故障或候选夹具，证明状态机与宿主接线，不证明自然任务收益。
本地 Laya 固定权重的 Task、Stage、Advisor、Escalation 专项判别质量未达日常门槛。

2026-10-03 的 OpenRouter Jev 真实 DSH 工具任务完成 Advisor 批准与 Escalation 接管；
两条任务合计 13.62995 AFP 与 0.004044504345 CNY。Escalation 的原始
`PROCEED` 概率为 0.70、Choice confidence 为 0.58，按当前 0.8 概率门槛接管。
这证明默认判定与轨迹一致，也暴露可能的不必要升级；一个任务不足以估计误升级率。
Jev 分动作实验门槛在 24 条有限留出题上与旧规则均有 22 条符合内部标签，
因此没有改变默认值。完整证据见[支持矩阵](../../docs/planning-routing-support-matrix.md)。

## 本次修正

- 设置页把「默认路由策略」与「正在编辑的策略」分开。核对实际 DSH 浏览器：
  编辑 Task、Advisor 时默认 Stage 保持选中，已有设置正常显示；未保存草稿。
- 零调用结果改称「配置可执行」，说明它不判断 Judge 质量；保存提示也指明默认策略。
- 预算单位摘要计入 Advisor 的独立执行模型和 LLM Judge，并注明它汇总的是已配置路线。
- Python 预检在 Advisor LLM Judge 被宿主移除或拒绝时报告具体宿主错误，
  而不错误地显示可执行。
- 更新日常指南、支持矩阵与过时的 Composite、Jev 描述。

## 边界

此次收尾没有证明任何策略在开放任务上普遍比 Static 更省钱，也没有把当前 Laya 权重
升为日常推荐。Stage／Composite 的规则换模依赖可信工具执行事实；没有结构化状态的
普通 Base URL 工具结果维持无法分类。图片／影片完整路线、跨客户端自然动态切换和
P6 子 Agent 共享预算仍按各自范围独立验收。
