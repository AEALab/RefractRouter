# MoA 输出评审（moa-output-01）

留出实验 live-01 的官方质量门槛：对 107 个已有输出的运行执行 #79 的多模型共识评审。
预检已于 2026-09-19 冻结并随升级阵容变更重新冻结；实跑在 Codex 额度恢复后执行。

## 冻结包络（preflight.json）

- 目标 107 个运行输出（108 次运行中 1 次失败无输出）；maximum_calls 428；
  单次超时 480 秒、超时总额 205440 秒；real_model_calls 0。
- policy_sha256 b591b0f8…（2026-09-19 变更：升级判定 A 由 ark/kimi-k3 改为
  moonshot/kimi-k3，原因是 Ark 方案额度用满；初审判定两位不变。
  此前材料门禁、用途确认与 19 例校准使用旧阵容（2ae5b345…）归档，不回改。）

## 阵容变更说明

- 初审：ds/deepseek-v4-pro（codex CLI）、claude opus（claude CLI）——不变。
- 升级：moonshot/kimi-k3（codex CLI，Moonshot 账户，替代 ark/kimi-k3）、
  claude opus max（claude CLI）——Ark 额度用满后按用户指示切换。
- 变更只影响输出评审的升级层；材料门禁与用途确认证据保持原样。

## 执行命令

uv run python experiments/run_moa_review.py --kind output --live   --results reports/pareto-holdout-v1/live-01/evaluated-results.json   --output-dir reports/quality-study-v2/moa-output-01

评审结束后重新分析（新输出文件）：

uv run python experiments/analyze_bound_quality_study.py   --study-dir data/quality-study-v1   --frozen reports/pareto-holdout-v1/live-01/frozen.json   --results reports/pareto-holdout-v1/live-01/evaluated-results.json   --output reports/pareto-holdout-v1/live-01-analysis-v2.json   --moa-material-reviews reports/quality-study-v2/moa-material-gate/moa-results.json   --moa-purpose-review reports/quality-study-v2/moa-purpose-06/moa-results.json   --moa-output-reviews reports/quality-study-v2/moa-output-01/moa-results.json

## 约束

- 零重试；评审不经过 Ark 账本，成本单独报告；origin=model、
  reviewer_identity_verified=false。
- 确定性检查先执行，fail 一票否决。
- 实跑若与冻结目标、超时或策略哈希不一致会被入口拒绝，必须重新预检。
