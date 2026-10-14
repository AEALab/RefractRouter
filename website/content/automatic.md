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

## 真实运行案例

下面是 2026-10-07 一次真实自动路由任务的完整记录（证据目录
`reports/automatic-routing-trace-20261007`），任务内容是独立审查三个互不依赖的文件。

**第一步：Jev 判别任务结构。** Judge 对“是否依赖前一步输出”“是否可独立开始”“是否只有
一项工作”三个问题给出概率，规则合并后分类为 SEPARABLE（可拆分）。

<figure class="doc-diagram"><img src="/screenshots/auto-trace-jev.jpg" alt="Jev 原始答案：三个结构问题的概率"/><figcaption>Jev 原始答案区：概率由规则合成分类，不是模型的置信度；实验路线明确标注。</figcaption></figure>

**第二步：比较两条路线后选择 Direct。** 直接路线预测 0.687 CNY，DAG 候选预测
1.385 CNY——拆分带来的并行收益不足以抵消规划、汇总与上下文重复的开销，最终整任务直接执行。

<figure class="doc-diagram"><img src="/screenshots/auto-route-decision.jpg" alt="任务判别与最终执行路线：SEPARABLE 但选择 Direct"/><figcaption>任务判别与最终执行路线：Jev 判为可拆分，但路线比较后选择 Direct，候选 4 节点计划只用 1 个。</figcaption></figure>

**第三步：执行、工具回执与费用结算。** 任务执行中宿主返回 bash 工具回执，费用账本按用途
分别记录参考成本与现金用量。

<figure class="doc-diagram"><img src="/screenshots/auto-tool-receipts.jpg" alt="工具回执与评审结果"/><figcaption>工具证据区：answer 节点的两条 bash 回执均为 completed；评审分数 100，门槛验收达到。</figcaption></figure>

同一个任务族里，另一次运行（2026-10-09，`reports/automatic-quality-20261009`）的 Jev
同样判为 SEPARABLE，但直接路线预测 0.126 CNY 低于 DAG 的 0.307 CNY，同样选择 Direct。
两次真实运行说明：**可拆分不等于应该拆分**，路线比较才是最终决策。

### 什么时候真的走 DAG

当任务确实包含多个可并行的独立子工作时，DAG 视图会显示分支结构与依赖连线：

<figure class="doc-diagram"><img src="/screenshots/auto-dag-full.jpg" alt="多节点 DAG：cost 与 risk 并行，answer 等待依赖"/><figcaption>多节点 DAG：cost 与 risk 无依赖关系可以并行调用模型，answer 等待两者完成。</figcaption></figure>

节点的正式类型（规划、提取、综合、生成、验证）与难度、风险由规划器估计；
每个节点可以分配不同模型与推理等级。

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
