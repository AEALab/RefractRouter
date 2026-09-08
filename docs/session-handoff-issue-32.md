# Issue #32 会话交接

本页记录 2026-09-08 的交付范围和续接入口。对应分支为
`codex/issue32-fair-baselines`，关联 [Issue #32](https://github.com/AEALab/RefractRouter/issues/32)。
本次用户要求提交 PR 后准备关闭 Session；PR 合并及后续实验仍需在后续任务中处理。

## 已完成内容

- 同一 DAG 的单模型 A/B 与节点 A/B 共用约束和归一化标尺，保留直接强模型及质量基准。
- 独立样本实验隔离已结算的节点错误，保留失败、费用和缺失评分；未知用量、认证、
  账本及证据故障停止整批。
- 修复缺失用量被默认零吞掉的问题，保留 HTTP 原始用量及字段有效性，不追改历史账本。
- v6 完成六种跨模型交接、八组×三任务×三重复的 72 次留出对照，252 次新增调用的
  用量审计及 117 条真实上游输入边核对通过。
- 核心及 DSH 入口支持 `maxNodeFallbacks`，默认 0，可设为 1 或 2。仅重做失败节点，
  排除该节点已尝试模型，保存所有尝试与成本；结构、空输出、截断可恢复，未知用量、
  基础设施故障、取消和截止不切换。
- 301 项完整回归通过；节点恢复的六种确定性故障注入通过，真实恢复调用为 0。

## 实验结论和限制

v6 节点 A 相对同一 DAG 单模型 A：配对平均质量差 -0.89 分、成本节省 17.98%、
时延增加 0.26%。节点 B 相对单模型 B：质量差 +0.56 分、成本节省 6.21%、
时延增加 13.92%。所有预设比较均未达到冻结的综合收益门槛。

Issue 第 4、6 项已经按三类能力/风险组合、一个输入预算区间、三个独立留出任务的
范围验收；完成实验不要求出现正收益。固定人工 DAG 不证明自动规划器质量；整图
统一模型分配也不是优化后的一次调用整任务路由。节点恢复目前仅完成机制验证。

## 证据入口

- [v6 真实实验及审计](../reports/dag-decomposition/issue-32-usage-verified-20260908/README.md)。
- [v5 用量异常及历史结果](../reports/dag-decomposition/issue-32-independent-samples-20260908/README.md)。
- [更早的对称基线及交接失败](../reports/dag-decomposition/issue-32-fair-baselines-20260908/README.md)。
- [节点恢复机制验收](../reports/dag-decomposition/issue-32-node-recovery-20260908/README.md)。
- [恢复参数与语义](text-task-routing.md#节点失败后切换模型)。
- [实验协议及解释](dag-study.md)。

报告中的「本地未提交」与源码索引描述归档当时的状态，保留作为历史快照，不代表本次
PR 的发布状态。实际执行源码绑定各轮 `implementation.tar.gz` 与内层指纹；当前源码
已变化，不能绕过指纹校验直接重跑旧冻结协议。新交接文档不追写到旧证据索引中。

## 下一任务的优先事项

1. 审阅并合并本分支 PR；检查 GitHub CI、源码与证据可追溯性，再决定关闭 Issue #32。
2. 若继续验证恢复收益，另行冻结无恢复、局部节点切换、全任务换模型重跑三类规则，
   预定模型、次数、调用包络、质量标准和停止条件。
3. 所有失败及重做费用、时延纳入比较。全任务重跑须包含被丢弃的成功分支费用；
   整图单模型只换一个节点后已经成为异构路线，不得沿用原单模型基线名称。
4. 扩大独立任务、输入范围或验证自动规划器时使用新任务划分，避免调参后复用已观察
   留出成绩。旧 v6 与恢复模拟均不能代替新真实收益对照。

## 本地复核

```bash
uv sync --frozen --extra dev --extra deepagents
npm ci --prefix validation/dsh/plugin
npm run --prefix validation/dsh/plugin typecheck
npm run --prefix validation/dsh/plugin build
uv run pytest
uv run python -m experiments.validate_node_recovery --output-dir /tmp/node-recovery-new
```

以上测试和故障注入不发起真实模型调用。Ark 必须使用 `/api/plan/v3`；用户已说明使用
Agent Plan 订阅，无需重复逐项确认 AFP 预算，但仍需冻结范围、上限和新输出路径。
中文文档与 GitHub 内容规范、Python 核心与 DSH 适配边界继续适用。DSH 使用新参数前
需更新匹配的 Python 源码并重新构建插件。

## 经验库状态

节点恢复中的不可变交接规则已有 Craft Wiki 主题覆盖，跳过重复写入。上一轮用量
存在性经验的外部知识库写入曾因自动权限审核超时未执行；项目内审计和报告已完整保存。
