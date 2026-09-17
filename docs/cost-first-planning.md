# 成本优先拆分：第三阶段

关联 [Issue #76](https://github.com/AEALab/RefractRouter/issues/76)，建立在
[必要拆分优化](minimal-dag-optimization.md)与[材料与字段交接优化](selective-context.md)之上。
质量门槛见 #52，端到端计量与对照见 #53，成本指标定义见 #76。

本阶段把「拆不拆」从结构判断改成成本判断：默认直接回答，只有成本依据在结构上成立时才保留 DAG，
并把依据写进证据，未校准前不给任何收益数字。

## 使用入口

沿用前两阶段的 Python 核心与已安装 `refractagent` 入口，仍不增加 DSH 设置项：

```json
{
  "task": "根据所附材料，逐条核对方案费用和适用条件，保留例外后给出建议。",
  "template": "auto",
  "plannerPolicy": "minimal-v2",
  "contextPolicy": "selective-v1",
  "maxConcurrency": 4,
  "acceptanceCriteria": ["覆盖所有费用和条件", "保留例外及来源依据"]
}
```

`minimal-v2` 仍是一次紧凑规划调用，不接受 `maxPlanRepairs: 1`；结构错误如实结算并失败。
`contextPolicy` 可选，`full` 表示所有节点收到完整材料，`selective-v1` 启用材料与字段选择。
预检不调用模型，不能验证规划器的实际选择；真实调用须另行冻结范围与输出路径。

## 默认直接回答

规划器在决策之外必须额外声明成本依据 `cost: {"drivers": [], "risks": []}`：

- `drivers` 只取 `parallel`、`cheap-model`、`compact-output`，且必须确实成立。
- `risks` 只取 `handoff-overhead`、`repeated-context`、`verbose-output`、`tight-coupling`。
- 决策为 `direct` 时 `drivers` 必须为空；拆分决策至少要有一个 `drivers`。
- `parallel` 决策必须声明 `parallel`；`tool`、`capacity`、`isolation` 沿用既有语义。

出现 `repeated-context`、`verbose-output` 或 `tight-coupling` 时规划被直接拒绝：这三项是「不拆」
条件，说明拆分本身要重复长上下文、输出冗长或工作强耦合，成本方向已经不成立。
缺失声明、字段越界、重复取值同样在任何节点派发前失败并如实结算。

## 成本门：只做结构核验

规划编译完成后、任何节点派发前，`cost-first-v1` 门对已声明的驱动做三项结构核验：

| 驱动 | 结构核验内容 |
| --- | --- |
| `parallel` | 图中确实存在可并发波次（`parallel_opportunities` 非空） |
| `cheap-model` | 至少一个非最终节点存在比最终节点候选更便宜且通过准入的候选 |
| `compact-output` | 所有非最终节点的输出字段取自 `facts`/`evidence`/`conclusion`/`uncertainty`，不是整篇正文 |

`cheap-model` 只说明「图里存在可以交给便宜模型的位置」，不代表运行时真的这样选模；
`compact-output` 只说明交接是结构化的，不代表输出真的更短。

声明了驱动但一个都没核实到时，不额外调用模型：把已声明的职责安全合并为一次直接回答（
`fallback: merged-to-direct`）。原有决策保留在 `proposed_decision`，合并分组写入 `merge_groups`，
`cost_gate.unverified_drivers` 说明哪些驱动没有成立。合并仍走既有的 `merge_before_execution`，
保留全部职责文本、内部推理依赖和验收覆盖；产生环路等非法结果时报错，不删边放行。

未校准前 `estimate` 恒为 `null`，`calibration` 为 `unregistered`，`benefit_verified` 与
`semantic_necessity_verified` 保持 `false`，`structure_only` 为 `true`。

## 输出压缩优先于前缀优化

`minimal-v2` 使用 `compact-v1` 交付措辞：中间节点只交付本职责产物，不复述材料原文或分支全文；
最终节点交付结论与必要依据，需要出处时引用来源 ID。措辞只改说明，不降低 `expected_output_tokens`，
不改变输出上限，也不截断任何内容。结构化交接字段的声明仍由 `selective-v1` 负责。

## 记录位置

- `result.json` 的 `compact_planning.decision` 保存 `policy_version`、`proposed_decision`、`decision`、
  `merge_groups`、`proposed_node_count`、`final_node_count` 与 `cost_basis`；
  `compact_planning.cost_gate` 保存同一次门判定，`attempts` 保存模型原始输出与解析错误。
- `summary.json` 暴露 `planning_policy` 与 `planning_decision`，与上述决策记录一致。
- `cost_basis` 形如 `{"policy": "minimal-v2", "declared_drivers": ["parallel"],
  "declared_risks": ["handoff-overhead"], "estimate": null, "calibration": "unregistered",
  "benefit_verified": false}`。
- 规划、节点执行与最终评审继续进入原账本；合并回直接回答不新增调用，因此不会多计 AFP。

## 边界与后续

结构核验不是收益证明，本阶段也不产生任何 AFP 或耗时结论。质量门槛仍归 #52；
#76 阶段四的独立留出实验才比较直接回答与成本优先 DAG，并计入失败、重试、备用模型与再拆成本。

## 本阶段验证记录

2026-09-17：`uv run pytest` 共 961 项通过（含 5 项 subtests，155.13 秒），其中新增
`tests/test_cost_first_planning.py` 13 项。本轮未进行真实模型调用，无新增 AFP 或真实响应时间结果。
