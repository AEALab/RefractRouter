# 自动路由 · Direct 与 DAG

<span class="doc-badge research">独立研究入口</span>

自动路由先判断任务结构，再比较整任务 Direct 与 DAG 候选。DAG 的节点可以使用不同模型
与推理等级；合法的独立分支可以并行调用模型。

<figure class="doc-diagram"><img src="/automatic-flow.svg" alt="自动路由完整决策流程：预检、拆分判别、规划、路线比较、执行与自适应审核"/><figcaption>能拆分、选择 DAG、候选通过审核，是三个不同判断；单节点规划结果仍归为 Direct。</figcaption></figure>

## 一次运行的过程

1. 冻结模型池、任务要求、数据域、价格、预算和期限。
2. 规则或可选 Jev 判断独立工作与依赖；微型任务可跳过额外判别。
3. 有必要时调用规划模型，生成计划并校验职责、依赖与输出合同。
4. Python 依据合法性、能力与质量依据、费用和时间预测选择 Direct 或 DAG。
5. 调用选定模型；DAG 按依赖执行，最终组合候选。
6. 检查实际工具与候选风险，按[自适应最终审核](adaptive-review.md)决定审核与交付。

## Jev 负责什么

Jev 适合回答是否存在值得分别处理的独立工作、分支间是否必须串行等有限问题。
它提供拆分信号，不负责生成完整 DAG、执行工具、结算费用或保证 DAG 更便宜。
节点计划仍由生成模型产出，Python 校验并作最终路线决策。

## 为什么可能继续选 Direct

可拆分任务也可能有较高的规划、上下文重复、汇总或审核开销。
预算、期限、数据域、节点准入与预测依据不足，都可能使 Direct 更合适。
选择理由应出现在实际记录，不只显示 Jev 的拆分答案。

## 模型池与节点分配

多个可用模型不表示每个节点必须使用不同模型。
节点类型、难度、风险、资料域、上下文、参数、质量依据和现金／参考成本共同影响候选。
缺少独立节点观测时显示使用全局先验；不能把排行榜分数当作该节点已经证明等质。

模型调用并行与工具执行并行分开处理：独立节点可以并行调用，宿主工具保持既有调度与审批。
汇总等待必要上游完成；节点失败按冻结停止或有界切换规则处理。

## 系统设置示范

进入 **设置 → 插件 → RefractAgent 自动路由**。以下均为 2026-10-14 打开实际 DSH 的截图，
使用已安装插件 `0.33.25`；仓库下载包为 `0.33.21`。截图值是当时配置，非通用推荐额度。

<figure class="doc-screenshot"><a href="/screenshots/dsh-20261014/automatic-settings.png" target="_blank" rel="noopener"><img src="/screenshots/dsh-20261014/automatic-settings.png" alt="实际自动路由设置：本地 Python 核心、真实执行开关、DSH 工具上限、自动判断与自适应评审"/></a><figcaption>连接方式、真实执行许可、工具上限与任务处理方式是不同设置；本地连接启动已安装的 Python 核心。</figcaption></figure>

| 控件 | 如何理解 | 对运行的影响 |
| --- | --- | --- |
| RefractRouter 连接 | 本地已安装核心或部署配置 | 本地模式不要求插件复制 Python 业务逻辑；远程路线以实际支持为准 |
| 启用开发真实执行 | 允许使用配置的真实模型 | 与模型菜单中的模拟／真实入口分别核对 |
| 单任务 DSH 工具调用 | Router 管理的工具调用上限 | 0 关闭；取消该上限仍受 DSH 权限、预算与期限约束 |
| 任务处理方式 | 自动判断或显式处理方式 | 决定是否比较 Direct 与 DAG，不负责最终质量审核 |
| 评审方式 | 截图为自适应 | 根据风险、工具事实与候选决定评审强度 |

<figure class="doc-screenshot"><a href="/screenshots/dsh-20261014/automatic-model-pool.png" target="_blank" rel="noopener"><img src="/screenshots/dsh-20261014/automatic-model-pool.png" alt="实际自动路由模型目录：现金上限、计费组、数据模式、模型价格与独立质量先验"/></a><figcaption>执行池按勾选模型进入候选；独立质量先验不是当前任务成功率，订阅参考成本与现金分别记录。</figcaption></figure>

先核对各模型真实 provider、上下文与输出容量、工具能力、价格单位、数据域和信任策略。
截图的生产现金上限 `5 CNY`、评审现金上限 `1 CNY` 是当前配置，不能拿来补写历史运行预算。

<figure class="doc-screenshot"><a href="/screenshots/dsh-20261014/automatic-decomposition-settings.png" target="_blank" rel="noopener"><img src="/screenshots/dsh-20261014/automatic-decomposition-settings.png" alt="实际拆分前判别设置：规则加 Judge 实验、Jev、0.01 CNY 上限和 0.65 是非门槛"/></a><figcaption>结构判别使用规则＋Judge（实验），每任务至多一次；Jev 提供有限答案，Python 决定最终路线。</figcaption></figure>

本例拆分 Judge 上限 `0.01 CNY` 独立记账；`0.65` 约束是／否答案概率，
不等于“DAG 成功率 65%”，也不是 Task、Advisor 或 Escalation 的 Choice 门槛。
界面中的“无限制”取消对应金额硬上限，不会让模型调用免费；任务实际预算与冻结证据仍须核对。

<figure class="doc-screenshot"><a href="/screenshots/dsh-20261014/automatic-review-settings.png" target="_blank" rel="noopener"><img src="/screenshots/dsh-20261014/automatic-review-settings.png" alt="实际最终回复审核：GLM 5.3 Low、180 秒期限、预留 60 秒、拒绝后纠正一次并复审"/></a><figcaption>最终回复审核与拆分 Judge 分开：审核检查候选，最多一次纠正并复审，不重跑已完成节点或工具。</figcaption></figure>

截图审核器为 `ark/glm-5.3`（Low），等待上限 180 秒、预留 60 秒，并勾选一次纠正。
等待上限仍受任务剩余期限限制；预留时间留给审核执行，不延长原任务。
更多跳过与升级条件见[自适应最终审核](adaptive-review.md)。

## 真实案例一：可拆分，最终选择 Direct

下面是 2026-10-07 一次真实自动路由任务的完整记录（证据目录
`reports/automatic-routing-trace-20261007`），任务内容是独立审查三个互不依赖的文件。

**第一步：Jev 判别任务结构。** Judge 对“是否依赖前一步输出”“是否可独立开始”“是否只有
一项工作”三个问题给出概率，规则合并后分类为 SEPARABLE（可拆分）。

<figure class="doc-diagram"><img src="/screenshots/auto-trace-jev.jpg" alt="Jev 原始答案：三个结构问题的概率"/><figcaption>Jev 原始答案区：概率由规则合成分类，不是模型的置信度；实验路线明确标注。</figcaption></figure>

**第二步：比较两条路线后选择 Direct。** 直接路线预测 0.687 CNY，DAG 候选预测
1.385 CNY。该次已知调用的预测成本中，直接路线更低，最终整任务直接执行；
未执行的 DAG 只保留预测，不能拿差额计算真实节省。

<figure class="doc-screenshot"><a href="/screenshots/auto-route-summary.jpg" target="_blank" rel="noopener"><img src="/screenshots/auto-route-summary.jpg" alt="2026 年 10 月 7 日运行 20261007T064138Z-0d3b7fd87479：可拆分但最终整任务执行"/></a><figcaption>同一次 2026-10-07 真实运行：候选计划 4 个节点，最终 Direct 选中 1 个交付节点。</figcaption></figure>

**第三步：执行、工具回执与费用结算。** 任务执行中宿主返回 bash 工具回执，费用账本按用途
分别记录参考成本与现金用量。

<figure class="doc-diagram"><img src="/screenshots/auto-tool-receipts.jpg" alt="工具回执与评审结果"/><figcaption>工具证据区：answer 节点的两条 bash 回执均为 completed；评审分数 100，门槛验收达到。</figcaption></figure>

同一个任务族里，另一次运行（2026-10-09，`reports/automatic-quality-20261009`）的 Jev
同样判为 SEPARABLE，但直接路线预测 0.126 CNY 低于 DAG 的 0.307 CNY，同样选择 Direct。
两次真实运行说明：**可拆分不等于应该拆分**，路线比较才是最终决策。

<figure class="doc-screenshot"><a href="/screenshots/auto-route-decision.jpg" target="_blank" rel="noopener"><img src="/screenshots/auto-route-decision.jpg" alt="另一次 2026 年 10 月 9 日真实运行：Direct 预测 0.12632293 CNY、DAG 预测 0.3070061687 CNY"/></a><figcaption>这是 2026-10-09 的另一条记录；它的预测数字与上面的 10 月 7 日案例分别读取。</figcaption></figure>

费用、Judge 与工具回执的完整口径见
[10 月 7 日公开报告](https://github.com/AEALab/RefractRouter/blob/main/reports/automatic-routing-trace-20261007/README.md)。

## 真实案例二：三项目独立分析，执行多节点 DAG

2026-10-05 的有限验收要求分别分析三个虚构项目，每项给出目标是否达成、两个量化依据、
一个风险和一项建议，最后汇总优先级，禁止混用数据，不要求工具。

| 项目 | 目标与输入事实 | 独立节点应核对的重点 |
| --- | --- | --- |
| 甲 | 响应目标 600 ms；实际 920 → 580 ms；故障率 0.4% → 0.8%；月成本 4 → 5 万 | 响应达标并下降 340 ms，同时保留故障翻倍与成本上升的风险 |
| 乙 | 成本目标 6 万；实际 8 → 5.8 万；响应 700 → 760 ms；故障率保持 0.2% | 成本达标并节省 2.2 万，同时说明响应变慢 |
| 丙 | 成功率目标 98%；实际 94% → 97.5%；响应 500 → 450 ms；成本 3 → 3.2 万 | 成功率提高但仍差 0.5 个百分点，不把进步写成已达标 |

核心实际生成 `proj_a`、`proj_b`、`proj_c` 三个独立分析节点，以及依赖三者的 `answer`。
2026-10-14 我们打开 DSH 已保存会话，重新截取了这次真实执行的图形：

<figure class="doc-screenshot"><a href="/screenshots/dsh-20261014/automatic-three-projects-dag.png" target="_blank" rel="noopener"><img src="/screenshots/dsh-20261014/automatic-three-projects-dag.png" alt="实际 DSH 历史回放：节点放置准入、三个项目分析分支、依赖三者的 answer，全部完成"/></a><figcaption>真实历史任务 20261005T144600Z-71362a2d5cc3 的 DSH 回放。上方虚线是准入流程角色，下方四个实线框是交付节点。</figcaption></figure>

读图时从上游向下看：准入完成后，三个项目分析之间没有相互依赖；
`answer` 必须等待三份结果才能汇总。这样的拓扑允许分支并行，但截图本身不能证明
实际调度有多大并发，或与 Direct 相比节省了多少时间。

<figure class="doc-screenshot"><a href="/screenshots/dsh-20261014/automatic-three-projects-nodes.png" target="_blank" rel="noopener"><img src="/screenshots/dsh-20261014/automatic-three-projects-nodes.png" alt="实际展开节点完整说明与依赖：每个项目只使用自身资料，answer 汇总并核对数据"/></a><figcaption>展开“节点完整说明与依赖”后读取完整职责；名称只是 ID，正式类型与依赖另列。</figcaption></figure>

| 节点 | 类型与依赖 | 实际分配及意义 |
| --- | --- | --- |
| `__role_placement__` | 流程角色 · 无上游 | 规则／分类器检查部署准入，不是一个付费生成节点 |
| `proj_a`／`proj_b`／`proj_c` | synthesis · 依赖准入 | 均为 `ark/glm-5.3`；分别分析自己的输入 |
| `answer` | generation · 依赖三个项目 | 同为 `ark/glm-5.3`；汇总与核对，不独立重算其他项目 |

图里是 **5 个流程节点、4 个交付节点、0 次工具调用**。所有节点使用同一模型也是合法 DAG；
DAG 表示任务依赖结构，不承诺异构模型分配。规划、判别与审核的额外模型费用另看调用账本。

原[公开验收报告](https://github.com/AEALab/RefractRouter/blob/main/reports/automatic-cost-trace-live-20261005.md)
记录本任务结算 **42.67125 AFP**，外部 Jev **0.000252162 CNY**，评审 96。
AFP 与 CNY 分开记账，模型评审分数也不替代独立质量验收。历史核心为 `0.15.17`、
插件为 `0.29.14`，不套用本轮设置页里的模型池、额度或参数。

本次回放读取 DSH 保存的节点事件；原核心运行目录已不在该位置，完整账本以原报告为准。
截图没有重新派发这项任务，也不构成新一轮收益实验。


## 在 DSH 中配置

使用独立的 **RefractAgent 自动路由** 卡片：选择执行模型池、数据域与信任策略，
核对规划／拆分／最终审核用途，设置任务预算、期限、调用与输出限制。
零调用诊断通过后，启用真实执行并选择 **自动路由（真实执行）**。

“省成本／均衡／质量优先”是历史三档入口，不代表新版两种路由的六策略。
旧模型 ID 为历史读取保留；新设置需要按当前模型目录显式初始化或升级。

## 已知边界

当前没有充分证据证明 DAG 在同等或可接受质量下普遍更便宜、更快。
规划、汇总、审核、丢弃和失败尝试均计入总体费用；只比较成功节点会低估总开销。
DSH 的接线通过也不是任意 Agent 的 DAG 协议兼容证据。标准模型网关不自动进入 DAG。
