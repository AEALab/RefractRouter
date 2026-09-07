# Issue #29：统一比较样本与明确评估可用性

2026-09-07 检视 #1 及关联议题后，本轮完成 #29 的统计口径修复、候选状态报告和离线
回归。随后用户确认 v2 策略及实施计划，现已实现 `exclude-known-contract-rejections-v2`；
默认选择规则仍是 `all-candidates-required-v1`。本目录中的历史复核新增模型调用为 **0**。
历史 v0.3 证据、旧判定、模型／prompt／rubric 与价格清单均未改写。

## 议题状态与本轮范围

| 议题 | 已核对状态 | 后续依赖 |
|---|---|---|
| #4、#9、#19 | 已关闭；dry run 截断问题与插件发布基础工作已完成 | 保留旧失败与修复后的证据 |
| #25、#28 | 已关闭；中间契约修复和 Python／TypeScript 边界已合入 | 遵循现有语言分工 |
| #29 | 开放；本轮修复比较口径并补充状态报告 | v2 离线验收与单轮真实准入均完成，待 PR 合并 |
| #22 | 开放；已有 63 格矩阵、9 份单模型评审，仍缺一条组合路线评审 | 需要三轮完整、可解释的对照 |
| #5 | 未启动 pilot | 等待 #22 有效证据及 pilot 独立预算 |
| #6 → #7 → #8 | final、人工抽检、最终报告均未完成 | 按顺序依赖 pilot、final 冻结产物与人工审阅 |

实现与证据见 [PR #33](https://github.com/AEALab/RefractRouter/pull/33)。
[v2 单轮真实准入](../v0.4-known-rejections/admission-agent-plan/README.md)已通过，82/82 请求正常，
总计 143.6703 AFP。#22 仍待完整三轮；GitHub 议题尚未关闭。来源为
[主议题 #1](https://github.com/AEALab/RefractRouter/issues/1)、
[#22](https://github.com/AEALab/RefractRouter/issues/22)、
[#29](https://github.com/AEALab/RefractRouter/issues/29) 及其依赖议题，核对日期 2026-09-07。

## 修复后的统计语义

- 每个策略的质量、成本、延迟使用同一组成功且独立评审的任务／轮次。
  未执行、失败、缺评审或非法指标均有排除原因；空集合显示 N/A。
- `runs` 表示已记录数，`expected_runs` 表示预期块数，`comparison_runs` 表示比较集合大小。
  `cohort` 保存精确标识与排除原因。成功率与评审覆盖率仍以全部预期块为分母。
- `production_cost_total` 与 `evaluation_cost_total` 保留该策略全部已记录费用，包括排除的
  失败运行。策略可能复用单模型结果，跨策略相加会重复计费；总支出仍以原始运行账本为准。
- 配对比较按相同任务／轮次筛选全部指标，排除行的所有差值均为 null；不得跨轮次配对。
- 不完整比较集合或不匹配集合不能通过 oracle gate；完整性使用实际集合判断，避免覆盖率
  舍入到 100% 后误放行。Pareto 表仍排除不完整策略，配对比较仍是主要证据。
- 节点矩阵另列记录完整性、评估可用性、契约拒绝／未知、各节点合格候选、旧规则下路线
  可执行性，以及实际执行／评审状态。这个报告不改变选模行为。

## 冻结证据复核

[新复核目录](v0.3-offline-review/)独立于原始
[v0.3 归档](../v0.3-contract-recovery/repeated-agent-plan/README.md)。
36 个索引产物与 63 格输出／上游哈希通过校验；原始目录所有文件 SHA-256 保持不变。

| 指标 | 原通用汇总 | 本轮一致口径 |
|---|---|---|
| node-oracle 平均质量 | 91.5，轮次 2–3 | 91.5，轮次 2–3 |
| node-oracle 平均生产成本 | 3.57668333 AFP，轮次 1–3 | 5.365025 AFP，轮次 2–3 |
| node-oracle 有效比较数 | 显示口径不一致 | 2/3，明确排除首轮 |
| vs task-oracle 配对质量／成本差 | -4.5 分／+2.598275 AFP | 不变，同为轮次 2–3 |
| Go / No-Go | Insufficient-evidence | Insufficient-evidence |

成本修正直接来自 `(6.53065 + 4.19940) / 2 = 5.365025`。
首轮记录完整，所有评价均已知，其中一个是契约拒绝；每个节点仍有其他合格候选。
冻结 v1 因该候选执行状态为失败而跳过组合路线，所以“评价已知”不等于“旧规则可执行”。

复现时输出目录必须全新且位于历史证据目录之外；全部输入审核通过后才写入结果：

```bash
uv run python experiments/review_node_quality_evidence.py \
  reports/v0.3-contract-recovery/repeated-agent-plan \
  --output-dir /tmp/refractrouter-cohort-review-new
```

重点产物：
[一致口径 baseline](v0.3-offline-review/reviewed-baseline-table.md)、
[配对比较](v0.3-offline-review/reviewed-strategy-comparisons.md)、
[矩阵状态](v0.3-offline-review/reviewed-node-availability.json)、
[完整性审计](v0.3-offline-review/reviewed-audit.json)。

## 已确认策略及有界验证计划

用户已确认按本计划实施。v2 已接入 Python runner 与 DSH plugin 0.5.0；
传参、完整性判定与错误分类均经过离线验证。以下为单轮准入计划，执行产物须另行归档。

策略 ID：`exclude-known-contract-rejections-v2`。
仅允许排除已明确记录的契约不合格候选，保留输出、拒绝原因及零契约分。
传输失败、缺独立评审、缺候选记录、无效上游上下文仍阻断；某节点没有合格候选也阻断。
在其余候选间继续按独立节点质量分、实测节点成本决胜，不强制混合，不修改收益判据。
v2 显式选择，并在 preflight、矩阵、summary 与 DSH evidence 中保存版本；v1 默认保留。
`selection-<task>-<repeat>.json` 记录选择原因、资格状态和模型分配。
同分同成本时按模型 ID 排序，保证独立于输入记录顺序；新规则不重算旧结果。

v2 离线验收后，准备一轮 `report_001` 准入检查：

| 项目 | 计划 |
|---|---|
| 输入及模型 | 现有 v0.1 dataset、v0.3 prompt/checks、Agent Plan manifest；独立 Kimi judge |
| 轮次 | 1；全新目录，实验标识应包含 v2 策略 |
| 最大请求计划 | 56 生产 + 21 节点评审 + 5 最终评审 = 82 |
| 当前零费用预检估算 | 生产 238.96 AFP，评审 420.99 AFP，总计 659.96 AFP（总计独立舍入） |
| 拟议准入上限 | 生产 250 + 评审 430 + 外层 DSH 0.7 = 680.7 AFP |
| 执行约束 | 只用 `/api/plan/v3`，关闭 thinking，重试 0，输出上限 8192，完成后关闭 paid profile |
| 停止／验收 | 保留每个拒绝与未知；任何缺评估／无效上下文都不得补零放行；核对哈希及实际费用 |

预算依据旧账本：已知加未结算保留额 823.52815 AFP，2505 AFP 总授权剩余
1681.47185 AFP；外层原 5 AFP 额度尚余 0.77475 AFP。拟议 680.7 AFP 信封低于这两个余额，
实施前须核对期间新增支出及未结算状态。估算按每次生产输入 4000、评审输入 8000、输出
8192 token 的冻结假设，不能解释为 provider 账单硬上界。

单轮只用于验证新策略的运行完整性，**不能关闭 #22 或启动 pilot**。一次全新的三轮计划
估算约 1979.87 AFP，超过当前已知剩余额度；不得直接沿用旧 2505 AFP 总授权启动它。
应在准入检查后核算实际支出，再制定完整三轮计划并处理所需预算。

零费用调用计划复现命令（仍使用现行 v1，仅作为请求数与费用基础）：

```bash
uv run python experiments/run_real_v0_1.py --phase dry-run --repeats 1 \
  --manifest data/model-manifests/volcengine-agent-plan.json --max-retries 0 \
  --output-dir /tmp/refractrouter-issue29-preflight-new
```

## 验证与知识评估

全套 `uv run --offline --no-sync pytest`：141 passed。统计回归覆盖跳过／失败费用、
缺记录、空比较集合、非法指标、集合不匹配、已知拒绝、全候选拒绝、缺 judge、传输失败、
无效参考上下文，以及禁止网络的真实归档复核。新增 v2 回归验证保存的真实拒绝可被排除、
未知状态始终阻断，以及完整模拟准入：保留拒绝费用，21 格矩阵，执行替代路线并独立评审。
模型清单测试验证 19 模型／6 类能力、套餐筛选及冻结 manifest 不变。
TypeScript typecheck 与 build 通过。

craft-wiki 评估了一个候选：“不完整实验的多指标比较必须对齐样本”。现有知识页已完整
覆盖同一规则及同一反例，本轮跳过重复摄入。
