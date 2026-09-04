# RefractRouter

> Task-Decomposition-Aware Heterogeneous Model Routing

RefractRouter 是一个面向 **任务分解感知的异构 LLM 路由** 的研究仓库。它关注的问题是：当一个复杂任务被表示为 DAG 后，如何在预算、延迟和执行历史约束下，为每个子任务节点选择合适的 agent、模型和计算量。

当前仓库处于 **研究文档与假设澄清阶段**，尚无可运行实现、数据集或实验代码。主要研究档案已迁移到 [GitHub Wiki](https://github.com/AEALab/RefractRouter/wiki)。

## 研究定位

RefractRouter 的核心研究对象不是「一个请求选择一个模型」的传统 LLM routing，而是：

```text
应用层提供初始任务 DAG
        ↓
路由层观察子任务状态、剩余预算和执行历史
        ↓
为每个节点选择 agent / model / compute
        ↓
必要时进行受控的动态再拆
```

形式化地，路由策略可以概括为：

```text
π : (s_i, B, H) → (a_i, m_i, c_i)
```

其中：

- `s_i`：第 `i` 个子任务的状态
- `B`：剩余预算
- `H`：前序执行历史
- `a_i`：Agent 或工具
- `m_i`：模型
- `c_i`：test-time compute

优化目标是：

```text
max_π E[Q(T) − λC − μL]
```

即在质量、成本和延迟之间寻找可证伪的 Pareto 改进，而不是默认「拆解一定更好」。

## 研究空白

现有工作已经覆盖了 query-level routing、multi-LLM ensemble、multi-agent configuration routing 和 benchmark 等方向，但仍留下六个关键空白：

1. **任务分解**：缺少从任务到计算结构 DAG 的系统化建模。
2. **子任务级异构路由**：MasRouter 等工作停留在 Agent 团队配置，尚未下沉到 DAG 节点级模型选择。
3. **条件难度估计**：缺少 `Q(subtask, model, compute)` 的节点级估计。
4. **动态模型池 × 任务分解**：两者各自有研究，但组合仍属空白。
5. **决策变量统一**：尚未联合优化 agent、模型、计算量、预算和历史。
6. **Benchmark 缺口**：现有评测多为 query-level，缺少任务分解感知的数据与指标。

## 当前状态

- 已完成 12 篇核心文献的谱系梳理与优先级排序。
- 已明确研究边界：静态拆解归应用层，动态再拆与节点路由归路由层。
- 已提出从最小数据集、Oracle 上限到 router v0 的实验路线。
- 已补充 WikiSkill 跨模型技能迁移视角，用于评估「技能生产」与「技能执行」分离的可行性。
- 尚未建立可运行代码、基准数据集或实验闭环。

## Wiki 导航

完整研究档案见 [RefractRouter Wiki](https://github.com/AEALab/RefractRouter/wiki)：

- [Related Work 与空白点分析](https://github.com/AEALab/RefractRouter/wiki/01-related-work与空白点分析)
- [文献笔记](https://github.com/AEALab/RefractRouter/wiki/02-文献笔记)
- [讨论纪要与概念厘清](https://github.com/AEALab/RefractRouter/wiki/03-讨论纪要-概念厘清)
- [研究讨论辩论档案](https://github.com/AEALab/RefractRouter/wiki/04-研究讨论辩论档案)
- [后续行动计划](https://github.com/AEALab/RefractRouter/wiki/05-后续行动计划)
- [WikiSkill 跨模型迁移与路由对齐](https://github.com/AEALab/RefractRouter/wiki/06-WikiSkill跨模型迁移与路由对齐)
- [WikiSkill 深度解析](https://github.com/AEALab/RefractRouter/wiki/WikiSkill-2026/WikiSkill深度解析)

## 推荐阅读路径

1. 先读 [Related Work 与空白点分析](https://github.com/AEALab/RefractRouter/wiki/01-related-work与空白点分析)，理解为什么现有 routing 不够。
2. 再读 [讨论纪要与概念厘清](https://github.com/AEALab/RefractRouter/wiki/03-讨论纪要-概念厘清)，明确 `Q(t,m)`、DAG 节点路由和成本边界。
3. 接着读 [后续行动计划](https://github.com/AEALab/RefractRouter/wiki/05-后续行动计划)，查看从数据到实验的推进顺序。
4. 最后读 [WikiSkill 跨模型迁移与路由对齐](https://github.com/AEALab/RefractRouter/wiki/06-WikiSkill跨模型迁移与路由对齐)，了解技能迁移如何影响路由决策。

## 仓库结构

```text
.
├── README.md
└── AGENTS.md
```

研究档案存放在 [GitHub Wiki](https://github.com/AEALab/RefractRouter/wiki)，它独立于主仓库目录。目前仓库还没有 `src/`、`tests/` 或构建脚本；当实现开始后，再按贡献指南补充目录与命令。
