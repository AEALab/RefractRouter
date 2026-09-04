# v0.1 原型实施计划：Fixed-DAG Node-Level Routing Harness

## 1. 已确认方向

v0.1 的目标不是做一个通用 Agent 平台，而是完成一个可复现、可证伪的节点级路由实验：

> 在“深度调研报告生成并输出 standalone HTML”这一固定工作域中，测量 `node-oracle` 是否比 `task-oracle` 在质量、成本、关键路径延迟上形成更好的 Pareto 解。

已确认的四条边界：

1. 输入固定 DAG，不做自动拆解。
2. `sampling_count = 1`，不做采样次数优化。
3. 主执行框架使用 **DeepAgents + LangGraph**，但不启用 DeepAgents 的自动规划或动态 sub-agent 生成。
4. 验证环境使用 **DeepSeek Harness / DSH**，DSH 只做外层验证与证据捕获，不参与核心路由决策。

## 2. 任务形态

v0.1 先做同一类任务，不跨太多领域：

```text
输入：主题 + 固定 source pack + 必需章节 + 输出约束
输出：一份结构完整、可离线打开的 HTML 深度调研报告
```

示例任务：

```text
report_001:
  主题：2026 年企业 LLM Agent 平台选型
  输出：standalone HTML
  必需章节：执行摘要、背景、选型标准、平台对比、风险、结论、参考资料
```

任务规模：

- 1 个 canonical task 做 dry run。
- 10 个任务做 pilot。
- 最终 20 个任务、约 120 个节点。
- 每个任务 7 个节点，保持总量在 `80-150 nodes` 范围内。

## 3. 固定 DAG

```text
parse_requirements
  -> build_outline
  -> extract_evidence
  -> synthesize_analysis
  -> write_report
  -> render_html
  -> verify_report
```

| 节点 | 类型 | 评分重点 |
|---|---|---|
| `parse_requirements` | planning | 需求覆盖、约束理解 |
| `build_outline` | planning | 章节完整性、逻辑结构 |
| `extract_evidence` | extraction | 引用准确性、信息召回 |
| `synthesize_analysis` | synthesis | 对比、推理、结论支撑 |
| `write_report` | generation | 叙述质量、结构、可读性 |
| `render_html` | rendering | HTML 有效性、版式 |
| `verify_report` | verification | 事实、引用、格式检查 |

## 4. 数据与模型

每个任务包含：

```text
task_id
domain
source_pack_id
required_sections
output_constraints
expected_claims
scoring_rubric_version
```

Source pack 规则：

- 每个任务 8-15 篇固定来源。
- 不做实时 web search，保证可复现。
- 每条证据带 `source_id`，报告中必须可追溯。
- 训练 / 测试按 `task_id` 切分，优先让 source pack 不重叠。

模型池要求：

- 至少 3 个模型，成本和能力差异明显。
- 通过 OpenAI-compatible adapter 注入，不硬编码 API key。
- M0 阶段冻结具体模型 ID、版本和价格表。
- DSH 不决定模型池，只承载验证环境。

## 5. 架构分工

### DeepAgents / LangGraph

- LangGraph 负责固定 `StateGraph` 执行。
- DeepAgents 作为上层 harness，用于节点隔离、artifact 传递和文件系统抽象。
- 不使用其动态 planning 能力。
- 锁定 DeepAgents 版本，避免 pre-1.0 breaking change。

### RefractRouter core

```text
src/refractrouter/
  schemas.py
  model_registry.py
  adapters.py
  routing.py
  graph_executor.py
  scoring.py
  metrics.py
  report_renderer.py
  cli.py
```

### DSH

DSH 只作为外层验证环境：

- 统一启动实验。
- 校验任务包、模型配置和 source hash。
- 捕获运行证据。
- 执行 HTML 与评分校验。
- 不参与核心路由决策，不替换 DeepAgents 主循环。

建议目录：

```text
validation/dsh/
  README.md
  runner.md
  checks/
```

## 6. 路由策略

v0.1 至少实现：

| 策略 | 说明 |
|---|---|
| `weak-all` | 全部节点用最便宜模型 |
| `strong-all` | 全部节点用最强模型 |
| `task-level-router` | 整个任务只用一个模型 |
| `node-type-rule` | 按节点类型固定映射模型 |
| `statistical-q` | 用训练集估计 `Q(node_type, model)` |
| `task-oracle` | 事后最优的单模型全流程 |
| `node-oracle` | 事后最优的逐节点模型选择 |

`statistical-q` 只在训练任务上估计，在测试任务上评估，避免泄漏。

## 7. 评分体系

最终任务分数采用 100 分制：

| 维度 | 权重 |
|---|---:|
| 需求覆盖 | 25 |
| 证据准确性 | 25 |
| 分析深度 | 20 |
| 结构与可读性 | 15 |
| HTML 有效性 | 15 |

验证方式：

- 确定性检查：HTML 解析、必需章节、引用编号、source trace。
- LLM-as-judge：使用不参与候选池的独立 judge model。
- 少量人工抽检：建议 10% 样本。
- 评分 prompt、rubric 和 judge 版本全部入库。

成本核算要区分：

- 生产执行成本：候选模型调用、渲染、验证节点。
- 评测开销：judge、人工审核、DSH 校验。
- 两者都记录，但 Pareto 主比较使用生产执行成本。

## 8. Oracle 实验流程

`task-oracle`：

1. 每个模型完整跑一遍 DAG。
2. 对每个任务选择最终效用最好的单一模型。
3. 汇总质量、成本、关键路径延迟。

`node-oracle`：

1. 对每个节点，在固定 upstream context 下运行全部候选模型。
2. 计算节点级得分。
3. 为每个节点选择事后最优模型。
4. 将选中模型组合成完整 DAG，重新端到端执行。
5. 用最终任务分数、总成本和关键路径延迟评估，而不是只把节点分数相加。

关键点：

- `node-oracle` 必须有 composed end-to-end run。
- 报告同时展示 isolated node score 和 composed task score。
- 若组合后质量下降，说明节点分数与最终任务目标不一致，这本身是重要发现。

## 9. Go / No-Go

v0.1 不预设 `node-oracle` 一定更好。判定规则：

1. **同成本看质量**
   成本差距小于 5% 时，`node-oracle` 质量至少高 5 分。

2. **同质量看成本**
   质量差距小于 2 分时，`node-oracle` 成本至少低 20%，且延迟不超过 120%。

3. **Pareto 前沿**
   `node-oracle` 在质量-成本曲线上应优于 `task-oracle`，并同时报告关键路径延迟。

4. **可部署性检查**
   如果只有 `node-oracle` 有收益，而 `statistical-q` 没有接近该收益，结论是“存在上限”，但还不能说明可部署路由有效。

## 10. 里程碑

| 阶段 | 内容 |
|---|---|
| M0 | 冻结任务域、模型池、rubric、DSH 边界 |
| M1 | 定义 schema、source pack 和任务文件 |
| M2 | 实现 fake adapter 和 DAG executor |
| M3 | 接入 DeepAgents/LangGraph 固定图 |
| M4 | 实现路由策略与 run record |
| M5 | 实现 HTML 校验、judge 和指标聚合 |
| M6 | 接入 DSH 验证环境 |
| M7 | 1 个 canonical task dry run |
| M8 | 10-task pilot |
| M9 | 20-task final benchmark |
| M10 | 生成 baseline 表、Pareto 图和 Go/No-Go 报告 |

## 11. 交付物

- `pytest` 全部通过。
- 不依赖真实 API 也能用 fake adapter 跑通端到端。
- 至少 20 个任务、3 个模型、每个节点 3 个模型结果。
- `reports/v0.1/` 中输出：
  - baseline table
  - Pareto front
  - oracle gap analysis
  - canonical HTML report
  - failure taxonomy
- README 增加 v0.1 快速开始命令。
- issue #1 更新为报告生成工作域，并补充 DeepAgents/DSH 架构决策。

## 12. 主要风险

- **报告评分主观**：固定 rubric、固定 source pack、独立 judge。
- **实时搜索不可复现**：v0.1 全部使用冻结 source pack。
- **DeepAgents 与 DSH 职责重叠**：DeepAgents 只执行，DSH 只验证。
- **节点分数不等于最终质量**：必须做 composed end-to-end run。
- **API 成本上升**：先 fake adapter，再 1-task dry run，再 10-task pilot。
- **HTML 结构不稳定**：加入 deterministic HTML checks。

## 13. 下一步

1. 实现 `task-dag.schema.json`、`run-record.schema.json` 和示例任务。
2. 实现 fake model adapter。
3. 实现固定 DAG topological executor。
4. 实现 baseline routing policies。
5. 接入 DeepAgents/LangGraph。
6. 接入 DSH 外层验证。
