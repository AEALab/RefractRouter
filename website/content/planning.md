# 规划路由

规划路由保留接入方 Agent 的原生执行循环。模型回复、工具调用与结果配对、实际来源和
已接受历史随请求保留；Router 负责策略、模型准入、Judge 和受管模型费用。

## 六种策略

| 策略 | 决策边界 | 执行器的变化 |
| --- | --- | --- |
| Static | 新任务选一次 | 固定角色，或按权重随机一次并保持 |
| Stage | 新的可信工具证据 | 高效起步、困难时临时接管、保持后可恢复 |
| Task | 新任务开始 | 从自选模型池选择主模型，任务内保持 |
| Composite | Task 初选 + 后续 Stage | 常用模型与指定接管模型之间切换 |
| Advisor Gate | 最终候选边界 | 固定执行器，最多一次返工并复审 |
| Escalation | 起始模型的未交付候选 | 一次接管后固定使用接管模型 |

具体行为见[策略概览](strategies/index.md)。

## 在 DSH 中设置

设置位于独立的 **RefractAgent 规划路由** 卡片，不与自动路由的 DAG 配置混放。

1. 配置共用模型资料、预算和数据域。
2. 选择正在编辑的策略，填写该策略真正需要的模型与 Judge。
3. 核对价格与能力诊断，运行零调用检查。
4. 保存后，在对话模型菜单的“路由模式”中选择。

“正在编辑的策略”不等于“默认路由策略”。保存设置从下个任务生效；正在运行的任务使用
已冻结配置。默认策略不应强行覆盖会话已经选择的模式。

## 界面与设置

规划路由的设置位于 DSH 设置窗口的 **插件** 区域，与自动路由各自独立卡片：

<figure class="doc-screenshot"><a href="/screenshots/dsh-20261014/settings-cards.png" target="_blank" rel="noopener"><img src="/screenshots/dsh-20261014/settings-cards.png" alt="实际插件设置页中的两个 RefractAgent 路由卡片"/></a><figcaption>2026-10-14 实际 DSH 设置窗口：分别展开规划路由与自动路由。</figcaption></figure>

展开 **RefractAgent 规划路由** 卡片后，按正在编辑的策略配置模型角色、Judge、预算与数据域，
运行零调用检查后保存。在对话输入框的模型菜单中选择“路由模式”即可使用。

六个策略页面都提供本轮实际设置截图、字段解释、流程图及案例：
[Static](strategies/static.md)、[Stage](strategies/stage.md)、[Task](strategies/task.md)、
[Composite](strategies/composite.md)、[Advisor](strategies/advisor.md)、
[Escalation](strategies/escalation.md)。截图由 Playwright 打开实际 DSH 页面并滚动捕获，
使用已安装插件 `0.33.25`；仓库下载包为 `0.33.21`，版本区别见[入口说明](routing.md)。

截图中“默认路由策略”始终保持 Stage，只切换“正在编辑的策略”来查看字段，未保存配置。
例如在 Task 页看见上方 Stage、下方 Task，表示正在编辑 Task；不能据此说当前任务已经使用 Task。

### 一个工具任务如何经过规划路由

以“调用一次终端工具执行 `printf %s STAGE_01_OK`，读取 stdout 后只回复该标记”为例：

1. DSH 把用户要求与可用工具传给 Python 核心；Stage 首轮没有工具证据，选择高效执行器。
2. 执行器产生工具请求，DSH 按自己的权限规则执行终端命令并保存回执。
3. DSH 携带已接受历史、工具请求和匹配结果续接；核心消费新增证据，选择下一轮模型。
4. 执行器回复标记，费用按真实模型调用结算；该任务没有拆成 DAG。

换成 Composite 时，在第 1 步之前多一次 Task 初选；换成 Advisor 时，在最终文字交付前
增加审核 Gate。工具的执行方与权限方仍是 DSH。

## 六策略真实运行案例

下表来自 2026-09-29 的 128 项正式验收（`reports/dsh-strategy-stability-20260929-v3`），
每个策略抽取第一个任务作为示例。模型为 `deepseek-v4-flash`（DSF）、
`deepseek-v4.1-flash`（V4.1）与 `glm-5.3-flash`（GLM）。

| 策略 | 调用序列 | 决策原因 | 费用（AFP） | 首字 | 总延迟 |
| --- | --- | --- | --- | --- | --- |
| Static | V4.1 | static-random-selected | 3.116 | 1.79s | 1.80s |
| Stage | DSF → DSF | no-signal → ambiguous | 1.254 | 1.24s | 4.38s |
| Task | GLM(判) → DSF | task-llm-judge → quality-then-first-call-cost | 0.774 | 3.13s | 5.60s |
| Composite | GLM(判) → DSF → DSF | task-llm-judge → selected → ambiguous-base | 1.408 | 3.21s | 7.66s |
| Advisor | V4.1 → DSF(审) | advisor-initial → advisor-approved | 3.670 | 1.41s | 4.50s |
| Escalation | DSF → GLM(审) | escalation-initial → escalation-proceed | 1.170 | 2.33s | 4.75s |

几个值得注意的行为：

- **Static** 的冻结随机在两条执行路线间抽取，同一批次 12 项任务同时覆盖了 DSF 与 V4.1。
- **Stage** 第一轮无信号用高效模型，工具回执 ambiguous 后保持同一模型；同批次 24 项
  每项恰好一次宿主工具调用。
- **Task** 的 Judge（GLM）只调用一次完成分类，之后固定选择质量达标且首调用成本更低的 DSF。
- **Composite** 比 Task 多一次执行调用：Task 选出常用模型后，后续轮次由 Stage 规则
  判断是否需要临时接管。
- **Advisor** 的执行与审核分开计费（V4.1 执行 + DSF 审核），候选经审核批准后才交付。
- **Escalation** 的 Judge 检查起始候选后放行（PROCEED），同批次 24 项全部一次通过，
  未触发接管。

这些是当时插件 `0.29.0`、核心 `0.15.4` 的受控文本／工具案例，Judge 使用冻结的 LLM
配置，与本轮部分截图中的官方 Jev 配置分开看。AFP 使用历史订阅口径，不能折算成 CNY。
128 项成功证明对应路径可完成，不证明六策略在开放任务上普遍优于 Static。
完整任务、模型分布与失败批次见
[验收报告](https://github.com/AEALab/RefractRouter/blob/main/reports/dsh-strategy-stability-20260929-v3/README.md)、
[逐任务记录](https://github.com/AEALab/RefractRouter/blob/main/reports/dsh-strategy-stability-20260929-v3/records.jsonl)。

## 新任务与续接

新用户轮次建立新任务状态。工具续接、进行中的追加指导和宿主压缩沿用当前状态，
不重新取得预算、不重复 Task 分类、不清零审核或升级计数。

标准模型接口需要可靠关联任务身份与历史。不能把首条消息的 hash 当成通用真实任务 ID；
身份无法确定的接入方式按其支持边界限制，不猜测兼容。

## 输出与取消

Static、Stage、Task、Composite 在选模后允许正常流式文本。
Advisor 和 Escalation 的待判别候选需要缓冲；未接受的文本与工具调用不会交付。
已经释放的文本不能被策略悄悄替换。接管后的 Escalation 可以流式输出，并注明未追加审核。

取消释放未派发的保护额度；已经派发的调用继续结算或保留待核对预留。
模型用量未知、认证／传输故障、账本或证据写入失败时停止后续受管调用。

## 配置可执行不等于质量已通过

零调用诊断核对模型、能力、价格、预算、信任和接口要求，不评价实际任务质量。
Judge 是辅助信号，最终仍需要你的验收条件。所有失败尝试、判别和被丢弃回复均需计入费用。
