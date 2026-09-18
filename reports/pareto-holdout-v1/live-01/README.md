# 正式留出实跑（live-01）

2026-09-18 按用户明确授权、以 bound-02 冻结件执行；零重试，按冻结失败规则停止。

## 运行事实

- 108 次运行全部完成：12 题 × 3 臂（direct-strong / task-selector / direct-or-dag）× 3 重复。
- 397 次真实调用、312.7503 AFP（charged_or_reserved：production 171.3863、
  evaluation 141.364），墙钟约 52.6 分钟（3155 秒）。
- 状态：delivered-unconfirmed 95、withheld 11、failed 2
  （decision-05-r1-direct-or-dag、analysis-04-r3-task-selector；失败计入分母，未重试）。
- 运行内评审：quality_status pending 65、fail 43。

## 分臂汇总

| 臂 | 运行 | online AFP | offline AFP | 调用 | 交付 | 扣留 | 失败 |
|---|---|---|---|---|---|---|---|
| direct-strong | 36 | 65.80 | 46.21 | 108 | 28 | 8 | 0 |
| task-selector | 36 | 52.43 | 47.65 | 144 | 33 | 2 | 1 |
| direct-or-dag | 36 | 53.15 | 47.50 | 145 | 34 | 1 | 1 |

## 分析与门槛状态

- `live-01-analysis.json`：observed_runs 108；`quality_gate_pending=true`
  （MoA 输出评审尚未执行）、`human_review_pending=true`；三个臂
  `afp_per_accepted_task` 暂为 null；`confirmed_pareto_frontier` 为空。
- 扣留与运行内 fail 是评审器的初步判定，不是官方质量结论；官方门槛以 MoA 输出评审为准。
- 下一步：对 95 个交付输出执行 MoA 输出评审（本地 CLI，不走 Ark 账本），再重新分析。
