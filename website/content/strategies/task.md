# Task · 任务

Task 在新任务开始时，从用户自选模型池选择主执行模型，任务内保持。
工具续接、追加指导和上下文压缩不重新执行分类。

<figure class="doc-diagram"><img src="/strategy-task.svg" alt="Task 的能力过滤、单候选直选、多候选 Judge 与备援路径"/><figcaption>Task 只在任务开始做一次决策；之后无论多少轮工具续接，都不重新分类。</figcaption></figure>

## 一次选模流程

1. 冻结模型池、优先顺序、Judge、备援、参数、价格和预算。
2. Python 检查输入、上下文、工具能力、数据域和历史兼容，排除不合格候选。
3. 单一合格候选直接使用；多个候选执行一次任务级 Judge 判别。
4. 依据已验证合同与门槛选出主模型；平分按池的优先顺序处理。
5. 正常无法确定时使用指定备援，备援也必须通过准入和预算。

没有合格候选时停止并列出缺项。认证、传输或未知用量是故障，不作为正常“不确定”
轮流尝试其他模型。

## Judge 可以选什么

- 轻量 LLM：使用已配置路线，严格检查结构化结果，不追加修复调用。
- 官方 Jev：任务级 Choice，候选与“信息不足”选项明确分开。
- 本地 Laya：常驻、批次结构化判别，不要求生成理由；当前质量标为实验。

不能把候选适合度或 Choice 概率称为任务成功率，也不直接比较不同后端的分数。
完整输入超出本地容量时按正常容量回退处理，不隐式截断或调用摘要模型。

## 必要设置

主模型池及各模型推理等级、池优先顺序、Judge 类型、指定备援。
默认要求备援在池内。媒体能力按实际接口记录，专门生成图片或影片的模型不充当主 Agent。

## 系统设置示范

打开 **规划路由 → 正在编辑的策略：Task**。上半区维护模型池，向下滚动选择备援与 Judge。

<figure class="doc-screenshot"><a href="/screenshots/dsh-20261014/strategy-task-settings.png" target="_blank" rel="noopener"><img src="/screenshots/dsh-20261014/strategy-task-settings.png" alt="实际 Task 设置上半区：加入执行模型、池优先顺序与模型推理等级"/></a><figcaption>2026-10-14 实际界面上半区：从 DSH 目录加入模型，按上移／下移调整平分时的优先顺序。</figcaption></figure>

<figure class="doc-screenshot"><a href="/screenshots/dsh-20261014/strategy-task-judge.png" target="_blank" rel="noopener"><img src="/screenshots/dsh-20261014/strategy-task-judge.png" alt="实际 Task 设置下半区：强执行备援、官方 Jev Judge 与高级参数"/></a><figcaption>同一设置卡片向下滚动：备援指向已登记的 V4.1 Flash；官方 Jev 是 Judge 类型，渠道在共用设置中配置。</figcaption></figure>

截图第一候选是 `ark/deepseek-v4-flash`（Low），另一候选是
`ark/deepseek-v4.1-flash`（High）。先检查能力与数据域，多个合格候选才调用 Judge。
界面说明的“首次调用费用上界”用于这次初选，不是整任务最终费用预测；
同单位参考价、现金计费与池顺序也有各自比较条件，不能只拿一个数字混排所有 provider。

业务场景是任务类型不同但工具链固定：短文本提取与复杂代码分析可以在任务开始选不同
执行器。选择后，即便任务继续多轮工具调用也保持该模型；需要途中接管时考虑 Composite。

## 费用与轨迹

付费 Judge 前保护一次必要执行额度；互斥候选不把全部模型上下文费用相加。
记录候选排除原因、一次初选／单候选／备援原因、原始答案、实际执行器、费用和耗时。
Task 固定选择不是全局成本最优保证。

### 真实案例

task-01 任务：Judge `glm-5.3-flash` 先完成一次分类（`task-llm-judge`），随后在合格候选中
判断的是“计算 `17×19`，只回复阿拉伯数字，不要调用工具”这个任务，正确答案为 `323`。
按“质量达标后选首调用成本更低”的规则（`quality-then-first-call-cost`）固定选择
`deepseek-v4-flash` 执行。共 2 次受管调用（1 次判别 + 1 次执行），费用 0.774 AFP，
首字 3.13 秒，总延迟 5.60 秒。同批次 20 项 Task 任务全部一次分类后固定执行器。
该[历史案例](../planning.md#六策略真实运行案例)使用 LLM Judge，与截图的官方 Jev 配置不同。
