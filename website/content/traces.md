# 运行记录与图形

记录既用于排查一次任务，也用于核对模型路由是否符合策略。不同记录可以收合，
保留开始时间与执行耗时，避免多次任务混在一起难以查找。

DSH 界面把记录分成两个页签：**任务 DAG** 展示拆分计划与节点状态，
**路由轨迹** 展示每次模型调用的策略原因、判别、费用与停止原因。
它们通过宿主会话引用关联核心记录；任务图还可以回放宿主保存的节点事件。
因此图形可回放不代表完整核心账本仍在原目录。

## 两个页签

| 页签 | 主要内容 |
| --- | --- |
| 任务 DAG | 自动路由计划、节点与连线、依赖、模型分配和执行状态 |
| 路由轨迹 | 模型调用流程、策略原因、Judge、接受／丢弃、费用与停止原因 |

自动路由也有可审计的调用记录与轨迹。Direct 可以没有任务节点图；规划失败可能只有规划调用，
不能因为没有 DAG 就丢失费用或错误。

## 路由轨迹页详解

路由轨迹页区分 **Judge 原始答案** 与 **Router 最终动作**：任务运行状态不等于质量已通过
独立验收。下面的截图来自一次真实的自动路由任务。

### 规划路由：看每次调用，而非任务拆分

<figure class="doc-screenshot"><a href="/screenshots/planning-history.jpg" target="_blank" rel="noopener"><img src="/screenshots/planning-history.jpg" alt="历史真实 Advisor 路由轨迹：已完成、AFP 与 CNY 分开、执行候选等待审核"/></a><figcaption>2026-10-07 保存的系统截图，展示 10 月 3 日 OpenRouter Jev 的 Advisor 有限验收；属于历史真实记录。</figcaption></figure>

这项任务要求调用一次终端工具输出 `OPENROUTER_ADVISOR_OK`，再只回复标记。
读规划记录时先看策略与状态，再逐行检查 **模型／推理等级 → 用途 → 接受或丢弃 →
本次与累计金额 → 决策与证据**。同一个任务可有执行、工具续接后的执行和一次审核，
费用按这些真实调用分别记账。图中的执行候选尚待审核，不表示已交付；只有 Gate 批准后
宿主才释放最终回复。金额 `6.49575 AFP` 与 `0.00208954 CNY` 使用各自单位，不能相加。
完整边界见[历史 Jev 接线报告](https://github.com/AEALab/RefractRouter/blob/main/reports/jev-openrouter-20261003/README.md)。

Stage／Composite 要看新增证据、保持计数和恢复原因；Task 要看一次初选及后续模型是否保持；
Advisor 要看候选处置与复审；Escalation 要看接管是否发生及接管后未追加审核的标识。
两行相同模型不代表路由没工作，也不自动代表发生过切换。

### 自动路由：把结构判别与最终路线分开

<figure class="doc-diagram"><img src="/screenshots/auto-route-summary.jpg" alt="路由轨迹页：任务判断与最终执行路线"/><figcaption>路由轨迹页的“自动路由”卡片：记录 ID、宿主轮次、端到端耗时、任务判别与最终执行路线。</figcaption></figure>

从上到下依次核对四个区块：

1. **记录头**：记录 ID、宿主轮次、端到端耗时。记录 ID 是本机证据文件的名字，
   可以直接用来排查。
2. **任务判断与最终执行路线**：结构规则给出的结论（例如“DAG 拆分执行”）、
   最终选择的执行方式、候选计划节点数与选中节点数。
3. **Judge 信息**：判别后端（如 OpenRouter Jev）、原始分类、规则合并后的分类、
   判别耗时与排队时间。实验性路线会明确标注。
4. **路线预测与适用范围**：Direct 与 DAG 两条路线的预测成本、预测范围的边界说明。
   未选择的候选路线没有被执行，预测差额不能当作实测收益。

<figure class="doc-diagram"><img src="/screenshots/auto-trace-jev.jpg" alt="Jev 原始答案表格：依赖前一步输出、可独立开始、只有一项工作的概率"/><figcaption>Judge 原始答案区：三个结构问题的概率，由规则合成分类，不是模型直接给出的置信度。</figcaption></figure>

Jev 原始答案区列出每个结构问题的概率（例如“是否依赖前一步输出 0.08”）。页面同时说明：
这些分类概率由规则合成，不是模型直接给出的 Choice probability 或 confidence，
也不表示任务成功率。合同版本（如 `decomposition-decision-v2`）与规则版本
（如 `automatic-decomposition-hybrid-v5`）会一起展示。

### 工具证据与评审

<figure class="doc-diagram"><img src="/screenshots/auto-tool-receipts.jpg" alt="工具证据、评审与停止原因：宿主工具回执列表"/><figcaption>工具回执区：每条回执显示节点名、工具、completed 状态与调用 ID。completed 表示回执已返回，不自动证明命令成功。</figcaption></figure>

工具证据区列出宿主返回的结构化回执：节点（如 answer）、工具名（如 bash）、
状态（completed）和调用 ID。**completed 表示回执已返回，不自动证明测试成功或命令退出为零。**
评审行显示是否完成、分数、原始结论与门槛验收结果——最终运行状态与质量验收是两个概念。

### 费用与预算

<figure class="doc-diagram"><img src="/screenshots/auto-fee-ledger.jpg" alt="费用与预算表格：参考成本占用、现金结算、待核对预留"/><figcaption>费用与预算区：按用途区分参考成本占用与现金用量；参考估值不与现金占用相加。</figcaption></figure>

费用账本按用途（生产、规划、评审等）分列：参考成本占用、现金用量结算／待核对、
当时现金预算与剩余。逐模型的准入记录显示实际分配状态；旧记录未保存的检查项会提示
“通过准入不等于预算可执行”。

## 任务 DAG 页详解

<figure class="doc-diagram"><img src="/screenshots/auto-dag-nodes.jpg" alt="任务 DAG 页：执行节点卡片与角色节点说明"/><figcaption>DAG 视图：每个节点卡片显示节点 ID、正式类型、难度风险、职责说明、分配模型与状态。</figcaption></figure>

DAG 视图里每个节点卡片包含五类信息：

| 字段 | 说明 | 示例 |
| --- | --- | --- |
| 节点 ID | 规划器命名的标识，没有固定清单 | answer、forecast、risk |
| 正式类型 | planning／extraction／synthesis／generation／verification | 生成 · generation |
| 难度与风险 | 规划器估计的 low／medium／high | 难度 medium · 风险 high |
| 职责说明 | 这个节点要产出什么 | 完整回答当前用户任务 |
| 模型与状态 | 分配的 provider／模型（推理等级）与运行状态 | ark/deepseek-v4-flash (low) · 已完成 |

上图是单交付节点 Direct 的展示：即使有准入角色和 `answer` 连线，也不应称为多分支 DAG。
箭头表示下游需要上游结果；同层无依赖的节点在合法调度下可以并行调用模型。

<figure class="doc-screenshot"><a href="/screenshots/dsh-20261014/automatic-three-projects-dag.png" target="_blank" rel="noopener"><img src="/screenshots/dsh-20261014/automatic-three-projects-dag.png" alt="2026 年 10 月 14 日实际回放的三项目多节点 DAG"/></a><figcaption>三项目真实历史 DAG：proj_a、proj_b、proj_c 相互独立，answer 等待三者；虚线角色不计作交付节点。</figcaption></figure>

完整输入、每个分支的输出合同、依赖、实际模型与历史账单见
[三项目案例](automatic.md#真实案例二-三项目独立分析-执行多节点-dag)。
图中三个分支都使用 GLM 5.3，难度／风险为 low；汇总节点为 medium。
难度是规划器估计，不能由节点名或框的颜色推断任务质量。

<figure class="doc-screenshot"><a href="/screenshots/dsh-20261014/automatic-three-projects-nodes.png" target="_blank" rel="noopener"><img src="/screenshots/dsh-20261014/automatic-three-projects-nodes.png" alt="实际节点完整说明与依赖：三个 synthesis 节点与一个 generation 汇总节点"/></a><figcaption>展开详情核对“只使用本项目数据”的约束与 answer 的三个上游；长职责以详情为准。</figcaption></figure>

### 流程角色节点

DAG 页还有一类**虚线边框的角色节点**：它们表示控制与质量环节，不是普通交付节点。

| 角色 | 作用与出现条件 |
| --- | --- |
| 规划前输入分级 · role-classifier | 规划模型调用前检查任务输入的敏感级别与部署许可 |
| 节点放置准入 · role-placement | 规划完成后检查敏感级别与可用部署路线 |
| 最终评审 · final-judge | 按自适应审核规则决定是否需要独立评审 |

角色节点按核心进度显示运行、完成、阻断或跳过状态，帮助区分“流程没走到”和“执行失败”。

<figure class="doc-diagram"><img src="/screenshots/auto-dag-types.jpg" alt="任务节点正式类型表格：规划、提取、综合、生成、验证"/><figcaption>节点正式类型表：类型由实际执行节点的职责决定，不由节点名称决定。</figcaption></figure>

节点 ID（forecast、drivers、trend、answer）是规划器起的名字，没有固定清单；
正式类型（规划、提取、综合、生成、验证）描述职责。难度与风险由规划器估计，
模型分配还考虑预算、上下文与输出需求及核心配置，不由节点名称直接决定。

## 每次记录应该看什么

1. 展开本次记录，核对开始时间、总耗时与当前／最终状态。
2. 图形中选择节点或调用，查看真实 provider、模型、推理等级及用途。
3. 核对模型选择、保持、恢复、返工或接管的原因。
4. 查看实际工具证据、原始 Judge 结论、规则版本与实验标识。
5. 查看本次与累计参考／现金费用、未派发保护及待核对预留。

模型首字时间、审核等待与用户首次实际看到文字的时间不同：待审核候选已经有 token，
不表示用户已经获得可交付答案。图形与记录随运行事件更新，旧记录缺字段不使用今天的设置补写。

## 状态的含义

| 状态 | 解释 |
| --- | --- |
| 运行中／等待审核 | 路由尚未形成可交付终态 |
| 已完成 | 冻结执行流程完成；独立质量结果另看 |
| 跳过审核 | 命中策略跳过条件，不等于独立质量通过 |
| 已接受／已丢弃 | 候选是否交给宿主；丢弃调用仍记账 |
| 未审定停止 | 证据或审核不足，候选没有正常交付 |
| 待核对 | 已派发但结果／用量不明，保留预留 |

### 如何识别模拟与历史证据缺失

2026-10-14 我们实际在 DSH 选择 **自动路由（模拟）** 并提交一项文档演示，得到记录
`20261014T032055Z-1f592764c5ae`。这是系统真实运行的模拟路径，外部付费模型调用为零。

<figure class="doc-screenshot"><a href="/screenshots/dsh-20261014/automatic-simulated-trace.png" target="_blank" rel="noopener"><img src="/screenshots/dsh-20261014/automatic-simulated-trace.png" alt="本轮 DSH 模拟记录：状态 simulated、模板预览与一条交付节点"/></a><figcaption>本轮实际提交的模拟任务。simulated 与 template-preview 明确区分演示和真实模型执行。</figcaption></figure>

该记录使用安装验证模板，只产生一个交付节点。即使处理方式栏出现 DAG 字样，也不能把它
当成真实多分支计划。读取时应结合 `simulated`、规划原因与节点列表，真实拆分看上面的历史案例。

<figure class="doc-screenshot"><a href="/screenshots/dsh-20261014/automatic-simulated-ledger.png" target="_blank" rel="noopener"><img src="/screenshots/dsh-20261014/automatic-simulated-ledger.png" alt="本轮模拟费用账本：参考用量与模拟模型分配"/></a><figcaption>模拟账本演示费用字段；显示的 0.00028 CNY 是模拟计算值，不是实际支付。</figcaption></figure>

若历史页提示“运行证据不存在”，先核对 `runsDir` 与记录 ID。宿主可能仍保留节点图，
但账本与 Judge 原始答案已经无法在当前目录读取。应引用原公开报告或恢复原证据位置，
不要用今天的设置填充缺失的模型、预算、结果或价格。

## 费用看起来不对时

先区分参考估值与现金，再核对 token 计价单位、缓存互斥、推理 token 是否重复相加、
真实提供方、价目表版本和失败尝试。订阅参考值不能直接当作实际账单。
不要删除错误记录、清零待核对预留或只统计最终成功那次调用。

## 本地记录

DSH 插件保存到配置的 `runsDir`；默认工作目录中的 `.refractagent/runs`。
独立网关使用启动时指定的 `--runs-dir`。审计材料可能包含任务上下文，应保存在合适的本地权限下。
导出公开报告时不包含凭证或原始私有会话。
