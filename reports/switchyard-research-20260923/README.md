# Switchyard 策略调研与独立开发建议

调研日期：2026-09-23。本文是源码与公开证据调研，未运行付费模型实验，也未安装或接入
Switchyard。文中的性能数字属于发布方的实验；本项目收益与兼容性均未实测。

## 核心判断

根据用户补充的七类策略图，本轮方向调整为：深入理解 Switchyard 的机制，在
RefractRouter 的 Python 核心内独立实现适用策略。LiteLLM 移出当前范围；
不以嵌入 Switchyard 算法库、合并项目或外部合作作为开发路线。

优先借鉴 Stage、Task/Capability、Composite 与 Advisor Gate；Fixed/Random 提供对照，
Escalation 后续验证，Prefill 暂缓。完整机制、代码改动位置与验收要求见
[执行策略开发提案](../../docs/trajectory-routing-strategies.md)。

RefractRouter 继续拥有 DAG、节点契约、模型准入、执行与预算。
新增轨迹策略既能用于不显式拆分的 Agent，也能用于 DAG 节点内部。
其研究问题是：动态换模本身能带来多少收益；在此基础上，显式任务结构、信息隔离、
依赖调度与并行执行还能增加多少收益。

## 证据与版本

- 公开仓库采用 Apache-2.0；调研时 API 返回约 3,204 stars，该数字只说明关注度。
- 最新 GitHub 正式发布为 v0.3.0，发布时间 2026-09-22 18:06:59 UTC，即北京时间
  2026-09-23 02:06:59；标签提交为 `336196f6fbfc97ddc71c1700f6092e564e9f23c2`。
- 本次源码快照为 `c6e5958a663a879541f4674744b52be6cb969fe6`，比发布标签多 4 次提交。
  差异包括 Stage 文档澄清、Anthropic 流式错误格式、MCP 工具名称识别，以及失败路由调用计数。
- README 部分安装提示仍提及“等 v0.3.0 发布”或 PyPI 0.2.0。因此发布标签、包发布结果、
  主分支文档应分别核对；本次没有验证 PyPI 各平台 wheel 的安装情况。
- 对照 RefractRouter 当前工作树提交 `256c1bd` 与 Issue #116，区分研究设计、已有函数
  和当前入口可执行范围，不将产品规划全部视为完成能力。

来源：[发布说明][release]、[固定源码][snapshot]、[发布后差异][release-diff]、
[RefractRouter #116][rr116]。源码文件与本地对照文件的摘要见 [证据索引](evidence-index.json)。

## 它实际实现了什么

Switchyard 的主要工作是根据请求和 Agent 轨迹决定下一次模型调用如何执行。一次决策可以
读取多个历史轮次，也可以在 session 内保留状态，因此不能把它理解为完全无状态的请求分类器。

| 策略 | 当前机制 | 对我们的价值与边界 |
| --- | --- | --- |
| Stage / Execution | 从工具历史识别错误、停滞、探索、写入等信号，选择 efficient 或 capable；可选 LLM 判别 | 优先比较的低额外调用基线；编码工具语义向研究、报告任务迁移需要验证 |
| Capability / Task | 让判别模型估计便宜模型能否完成任务，再按阈值选档；支持按请求、用户轮次、session 分类 | 与整任务选模直接重叠；预测概率尚不能直接当作本项目质量保证 |
| Escalation | 先生成便宜模型结果，再评审轨迹；连续升级判定后转强模型并保持 | 能处理持续卡住；一次升级可能产生便宜执行、评审、强模型三次调用 |
| Advisor Gate | 执行模型保持不变，强评审在结束声明或停滞时批准或要求重做 | 可以借鉴“按事件评审”，但它是在线干预者，不能兼任最终独立实验裁判 |
| Plan/Execute | 强模型先检查与规划，首次文件修改后切到便宜模型 | 没有生成节点依赖图；失败的修改也可触发切换，不等于规划质量已验证 |
| Composite / 子 Agent 路由 | 当前 Composite 固定组合分类器与 Stage；可为已存在的子 Agent 配独立模型池 | 证明它已覆盖更丰富的 Agent 路由，不能把“支持子 Agent”作为我们独有能力 |
| Prefill Router | 使用隐藏状态与训练好的分类器预测各模型成功情况 | 实验功能，未提供受支持的 checkpoint、导出器和编码器资产，近期不建议作为依赖 |

以上分别核对了 [Stage][stage]、[Capability][capability]、[Escalation][escalation]、
[Advisor][advisor]、[Plan/Execute][plan-execute]、[Composite][composite]、
[子 Agent 路由][subagents]与 [Prefill][prefill] 文档及对应实现。

两个特别容易误读的地方：

1. Stage 的 `confidence` 来自固定权重信号的 `tanh` 分数幅度；0.5 不是“任务成功率 50%”。
   Auto 当前也是一套 Stage 固定预设，没有运行时比较所有策略并求最优。
   [评分实现][stage-code]直接显示了该计算与强制升级规则。
2. “规划后执行”当前用工具轨迹中的首次 edit/write 判定切换；没有明确的 DAG 交接字段、
   跨节点预算优化和并行调度。源码中的 phase/latch 机制与文档一致。
   这是一种有价值的简化策略，但与显式结构规划是不同干预。[实现][plan-code]

## 官方数字应如何理解

README 中的 Terminal-Bench 2.1 表属于 **v0.2.0 的历史实验**，不能直接视为当前 v0.3.0
的完整性能验收。

| 历史路线 | 完成率 | 总费用 | 相对全 Opus 基线 |
| --- | ---: | ---: | --- |
| 全 Opus 4.8 | 76.0% | $98.06 | 基线 |
| Escalation | 75.7% | $85.00 | 费用低 13.3%，完成率低 0.3 个百分点 |
| Stage | 72.7% | $68.19 | 费用低 30.5%，完成率低 3.3 个百分点 |
| Capability | 71.2% | $79.32 | 费用低 19.1%，完成率低 4.8 个百分点 |
| 全 GLM 5.2 | 52.4% | $16.47 | 便宜很多，但完成率明显较低 |

来源：[固定版本 README 的基准说明][readme]。这些是所报告测试集的总费用，不是每任务价格。
原实验使用 NVIDIA 内部推理端点，公开配置替换为 OpenRouter；配置还明确要求使用历史兼容
版本才能复现该 escalation schema。[历史配置][tb-profile]

这里的 99.6% 是 75.7 / 76.0 的相对完成率，不能表述为“99.6% 的任务成功”，也没有仅凭
两个均值就证明统计等效。本项目若设定硬质量门槛，应先判断各路线是否满足门槛，再谈节省。

LangChain 提供了更值得关注的合作方实验：145 个多步骤任务中，全 Opus 的完成率与每轮费用
为 86.0% / $11.45，动态路由为 80.0% / $3.00，全 Nemotron 为 77.7% / $0.72。
其文章明确指出，路由相对便宜模型增加的 2.3 个百分点小于运行波动，尚不能确认优于便宜模型；
在线判别又占路由费用的 21.2%。这支持“必须比较便宜固定模型”的实验设计，并不证明所有
任务都应采用路由。[LangChain 原文][langchain]

v0.3.0 仓库还提供 DeepSWE v1.1 的复现配置：113 个任务，Advisor 与 Plan/Execute 为
3 次独立运行，Stage 的 76/113（67.3%）是单次严格分母结果。失败与缺失计入分母；
原始与公开配置的 serving stack 不同。不能把一轮 Stage 和三轮其他策略的均值直接当成
显著性排名。[资格条件][deepswe]、[复现入口][benchmark]

本次未取得并逐项复算上述所有原始任务轨迹，未独立复现实验；其效果属于公开报告证据，
并非本项目测量结果。Soak/performance 脚本衡量协议、吞吐与开销，也不能替代任务质量实验。

## 与本项目的共同点及差异

| 维度 | Switchyard 已审查实现 | RefractRouter 当前代码与研究方向 |
| --- | --- | --- |
| 共同目标 | 根据任务与执行状态使用不同模型 | 在可接受质量下优化费用与端到端时间 |
| 决策位置 | 请求、轮次、session 与已有子 Agent | 是否拆分、DAG 节点分配、执行与恢复 |
| 结构所有权 | 接收宿主已发生的工具与子 Agent 轨迹 | 显式规划和校验 DAG、依赖与交接字段 |
| 主要信息 | 工具行为、错误、进展、LLM 判别 | 节点契约、候选画像、输入包络、图结构与部署域 |
| 优化方式 | 主流策略是启发式或分类阈值；支持自定义多模型分类 | 有节点组合求解与 direct/DAG 费用比较；预测有效性仍需实测 |
| 并行 | 可以承接宿主并发工作；所审查路由未规划整个任务图的关键路径 | 有 DAG 依赖调度、并发限制与关键路径估计 |
| 数据边界 | 协议和凭据边界较丰富；未在所审查策略中发现本项目式节点数据分级约束 | 本项目有模型部署域、信任策略及运行期输入检查 |
| 评审 | 可以作为在线决策或修复的一部分 | 同时需要交付门禁与独立研究评估，必须区分角色 |

RefractRouter 的对照依据包括 [架构](../../docs/architecture.md)、
[节点选模](../../src/refractrouter/node_routing.py)、
[自动选路](../../src/refractrouter/automatic_routing.py)、
[原生工具循环](../../docs/native-tool-execution.md)与
[单任务真实执行门禁](../../src/refractrouter/live_execution.py)。

代码存在并不意味着任意入口均已开放全部能力。例如当前单任务真实执行入口有明确的工具
请求门禁，历史节点工具循环又有自己的范围；不能把这些入口统称为已完成的通用 Agent。
同样，Switchyard 支持子 Agent 策略并不意味着它负责创建子任务图。

本项目还应正视既有结果：[live-01 归因报告](../pareto-holdout-v1/failure-attribution-v1/README.md)
记录 direct-or-dag 的 36 次运行里只有一次真正多节点，且该次失败；三条路线均未达到该批
90% 门槛。这不是“DAG 必然无效”，但说明不能仅靠结构差异宣称研究贡献已成立。

## 对研究方向的建议

### 先把“不拆分”与“不换模型”拆开

一个不显式拆成 DAG 的 Agent，仍可能经过很多工具轮次，并在每轮使用不同模型。
因此 direct 至少应区分“一次答复”“单 Agent 多轮固定模型”“单 Agent 多轮动态模型”。

Switchyard 的价值在于提供第三种有现实竞争力的实现。若我们只打败“全程固定昂贵模型”，
尚无法判断收益来自 DAG，还是仅来自把部分调用交给便宜模型。

### 把结构收益作为需要验证的假设

值得继续验证的三个方向是：

- 可分离材料：节点只读取必要材料切片，减少重复长上下文；信息压缩不得丢失引用与约束。
- 独立分支：通过并行缩短关键路径，计入供应商并发限制与合流等待。
- 不同信任域：在全部合规路线之间比较，验证结构化分离是否让公开部分使用更便宜模型；
  本地推理不能无条件按真实总成本为零处理。

以上是研究假设，不是 Switchyard 已被证明缺乏的普遍能力，也不是 RefractRouter 已取得的收益。

### 优先借鉴事件驱动的升级与评审

Stage 可以在没有额外 LLM 评审调用时作决定；Advisor 则只在关键事件附近付出审核成本。
我们可以研究“有确定性错误、重复失败或结束声明时才升级/评审”，而非每个节点都固定增加
一次昂贵评审。但正常的失败测试和有效探索不应被一律解释为能力不足。

在线参与选择、给出纠正计划的 judge 已经影响执行结果；最终离线评测必须保持独立。
Advisor 的 APPROVE/REDO 也不等于一个已校准的质量分数。

### 统一拥有执行决策与预算

本项目独立实现借鉴策略，所有模型选择、判别与评审请求都经过 Python 核心的准入和账本。
若初始节点分配为便宜模型，后续 Stage 推荐强模型，应重新检查实际请求、允许候选、
剩余预算与历史兼容性，并记录实际模型；不能继续按初始分配描述最终执行。

检查对象也必须包含 Task、Escalation 和 Advisor 的中间调用。
最终模型合法不代表此前用于选模的判别调用可以读取同一份敏感材料。

## 独立开发路线

| 阶段 | 内容 | 原因 |
| --- | --- | --- |
| 第一批 | Fixed/Random 对照、Stage 规则、工具循环内的受限换模 | 先用已有轨迹获得可解释且无额外模型调用的决策 |
| 第二批 | Task/Capability 与 Task + Stage 的 Composite | 增加任务先验，避免工具信号不足时完全依赖默认值 |
| 第三批 | Advisor Gate | 按结束或停滞事件支付评审成本，验证有界续作价值 |
| 后续 | Escalation | 存在 weak + judge + strong 的费用和缓冲开销，独立评估 |
| 暂缓 | Prefill | 需要训练资产和针对本项目候选池的质量标签 |

借鉴的核心是事件、判定时机、状态和验证方法。
实现保留在本项目 Python 内，不添加 Switchyard 运行时依赖。
具体提案中的有限状态、异常处理与数据域约束属于本项目设计，
没有一致性验证时不能称为官方策略复现。

上游 CallModel / Done 的契约仍提供一个有价值的设计参考：
策略提出需要什么调用，宿主负责执行；已有回复可以直接交付，避免无意义的重复生成。
这里借鉴接口边界，而不计划调用其 Rust/PyO3 API。[核心契约][core]

## 借鉴时需要保留的适用边界

发布方将 `libsy` 标为 Beta、HTTP client/runner 标为 Alpha，独立 server 标为
Demo/评估用途；v0.3.0 明确是破坏性升级。不能由 NVIDIA 名称或正式 tag 推断所有组件已可
作为生产基础设施。[发布说明][release]、[组件表][readme]

主分支比 v0.3.0 多出的失败路由调用计数修复尤其相关：修复前，某些调用失败会先终止
算法，使高层调用次数指标漏记。该修复针对计数/时延观测，不等于已经证明全部费用账本完整。
此外 Relay 的内部 span 层次仍有未决集成议题。[提交对照][release-diff]、[#299][issue299]

本地独立实现仍须验证工具历史兼容、取消、缓存用量和执行状态连续性。
Advisor 的“评审次数预算”也不能替代金额或 AFP 硬预算。Stage 的工具词汇主要来自编码场景，
对报告写作、检索分析或城市规划任务不能直接沿用其阈值而声称已校准。

## 建议的最小实验

先定义任务类型，区分单次文本任务与多轮工具任务。对缺乏工具轨迹的任务，Stage 可能退化为
默认档位，不应强行拿它证明动态路由优劣；可采用 Capability 作为对应基线。

对多轮工具任务，优先采用如下对照：

| 实验臂 | 显式 DAG | 模型策略 | 主要回答的问题 |
| --- | --- | --- | --- |
| A | 无 | 固定便宜模型 | 简单便宜方案是否已足够 |
| B | 无 | 固定强模型 | 同模型池下质量参照 |
| C | 无 | 本项目借鉴实现的 Stage | 执行中换模能节省多少 |
| D | 固定同一张图 | 固定模型；分别与 A/B 配对 | 拆分结构本身有什么影响 |
| E | 与 D 相同图 | RefractRouter 节点选模 | 控制结构后，节点分配有什么增益 |
| F，后续可选 | 与 D/E 相同图 | 节点分配 + 节点内部 Stage | 两层策略是否互补 |

C/E 的端到端比较评价产品路线；D/E 控制同图比较分配效果。不能只凭 C/E 差异就把全部效果
归因于图结构。自动生成 DAG、自动决定拆不拆应在固定图实验后另设实验，以区分 planner、
结构和选择器各自的影响。

统一冻结模型/Provider/effort、工具权限、材料、总预算、失败规则和最终验收。
报告任务通过率、全部尝试费用除以成功交付数、端到端时间、在线路由/评审开销、实际换模次数、
真实多节点比例和未知用量；缓存 token、取消和丢弃回复都要记录。离线研究评审费用与部署
费用分别呈现。相同任务重复运行不是新的独立任务样本。

先用录制轨迹与模拟客户端做零付费回放，验证执行身份、模型选择、工具语义和账本。
回放不能证明换模后仍会出现原录制轨迹；收益须通过新的真实执行验证。
效果实验需要新的冻结样本、预检和明确调用范围；本次调研没有启动这一步。

## 本次判断的边界

本轮已明确独立借鉴模式的开发方向；本地方案与源码位置已形成文档。
尚未实现或启用新策略，未运行付费效果实验，不能据此声称本项目已取得收益。
没有充分证据支持立即放弃 DAG，也不能仅凭显式 DAG 就认定优于动态调用级路由。

按 craft-wiki 评估了一项候选：将动态但不显式拆分的路由纳入结构收益对照。
已有研究定位条目已经要求 cheap/strong、confidence-escalation 等基线和真实干预覆盖，
本次不重复新增知识条目；新查证的源码与公开实验保留在本报告及证据索引中。

[release]: https://github.com/NVIDIA-NeMo/Switchyard/releases/tag/v0.3.0
[snapshot]: https://github.com/NVIDIA-NeMo/Switchyard/tree/c6e5958a663a879541f4674744b52be6cb969fe6
[release-diff]: https://github.com/NVIDIA-NeMo/Switchyard/compare/336196f6fbfc97ddc71c1700f6092e564e9f23c2...c6e5958a663a879541f4674744b52be6cb969fe6
[rr116]: https://github.com/AEALab/RefractRouter/issues/116
[readme]: https://github.com/NVIDIA-NeMo/Switchyard/blob/c6e5958a663a879541f4674744b52be6cb969fe6/README.md
[stage]: https://github.com/NVIDIA-NeMo/Switchyard/blob/c6e5958a663a879541f4674744b52be6cb969fe6/docs/routing_algorithms/stage_router_routing.md
[capability]: https://github.com/NVIDIA-NeMo/Switchyard/blob/c6e5958a663a879541f4674744b52be6cb969fe6/docs/routing_algorithms/llm_classifier_routing.md
[escalation]: https://github.com/NVIDIA-NeMo/Switchyard/blob/c6e5958a663a879541f4674744b52be6cb969fe6/docs/routing_algorithms/escalation_router_routing.md
[advisor]: https://github.com/NVIDIA-NeMo/Switchyard/blob/c6e5958a663a879541f4674744b52be6cb969fe6/docs/routing_algorithms/advisor_gate_routing.md
[plan-execute]: https://github.com/NVIDIA-NeMo/Switchyard/blob/c6e5958a663a879541f4674744b52be6cb969fe6/docs/routing_algorithms/plan_execute_routing.md
[composite]: https://github.com/NVIDIA-NeMo/Switchyard/blob/c6e5958a663a879541f4674744b52be6cb969fe6/docs/routing_algorithms/composite_routing.md
[subagents]: https://github.com/NVIDIA-NeMo/Switchyard/blob/c6e5958a663a879541f4674744b52be6cb969fe6/docs/routing_algorithms/subagent_routing.md
[prefill]: https://github.com/NVIDIA-NeMo/Switchyard/blob/c6e5958a663a879541f4674744b52be6cb969fe6/docs/routing_algorithms/prefill_routing.md
[stage-code]: https://github.com/NVIDIA-NeMo/Switchyard/blob/c6e5958a663a879541f4674744b52be6cb969fe6/crates/libsy/src/algorithms/util/stage.rs#L329
[plan-code]: https://github.com/NVIDIA-NeMo/Switchyard/blob/c6e5958a663a879541f4674744b52be6cb969fe6/crates/libsy/src/algorithms/plan_execute.rs
[tb-profile]: https://github.com/NVIDIA-NeMo/Switchyard/blob/c6e5958a663a879541f4674744b52be6cb969fe6/benchmark/routing-profiles/tb21-escalation-opus-glm-deepseek.toml
[langchain]: https://www.langchain.com/blog/switchyard-agent-routing-benchmark
[deepswe]: https://github.com/NVIDIA-NeMo/Switchyard/blob/c6e5958a663a879541f4674744b52be6cb969fe6/benchmark/DEEPSWE_V11_QUALIFICATION.md
[benchmark]: https://github.com/NVIDIA-NeMo/Switchyard/blob/c6e5958a663a879541f4674744b52be6cb969fe6/benchmark/README.md
[core]: https://github.com/NVIDIA-NeMo/Switchyard/blob/c6e5958a663a879541f4674744b52be6cb969fe6/crates/libsy/src/core/algorithm.rs
[python-api]: https://github.com/NVIDIA-NeMo/Switchyard/blob/c6e5958a663a879541f4674744b52be6cb969fe6/switchyard_rust/libsy.py
[issue299]: https://github.com/NVIDIA-NeMo/Switchyard/issues/299
