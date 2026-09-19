# MoA 输出评审（moa-output-01）

留出实验 live-01 的官方质量门槛：对 107 个已有输出的运行执行 #79 的多模型共识评审。
预检已于 2026-09-19 冻结；实跑等待 Codex 额度恢复（预计 2026-09-21 晚重置），
不更换评审阵容。

## 冻结包络（preflight.json）

- 目标 107 个运行输出（108 次运行中 1 次失败无输出）；`maximum_calls` 428；
  单次超时 480 秒、超时总额 205440 秒；`real_model_calls` 0。
- `policy_sha256` 2ae5b345…（与材料评审、用途确认同一阵容，不更换）。

## 阻塞条件

- Codex 用量（7 天窗口）100% 用满、无剩余额度，冻结阵容中两名评审（初审判定 A、
  升级判定 A）走 codex CLI，当前不可用。
- 重置时间约 2026-09-21 23:30（CST）。恢复后按原阵容执行，不需要重跑材料门禁、
  用途确认与 19 例校准。

## 额度恢复后的执行

```bash
uv run python experiments/run_moa_review.py --kind output --live \
  --results reports/pareto-holdout-v1/live-01/evaluated-results.json \
  --output-dir reports/quality-study-v2/moa-output-01
```

评审结束后重新分析（新输出文件）：

```bash
uv run python experiments/analyze_bound_quality_study.py \
  --study-dir data/quality-study-v1 \
  --frozen reports/pareto-holdout-v1/live-01/frozen.json \
  --results reports/pareto-holdout-v1/live-01/evaluated-results.json \
  --output reports/pareto-holdout-v1/live-01-analysis-v2.json \
  --moa-material-reviews reports/quality-study-v2/moa-material-gate/moa-results.json \
  --moa-purpose-review reports/quality-study-v2/moa-purpose-06/moa-results.json \
  --moa-output-reviews reports/quality-study-v2/moa-output-01/moa-results.json
```

## 约束

- 零重试；评审不经过 Ark 账本，成本单独报告；origin=model、
  reviewer_identity_verified=false。
- 确定性检查先执行，fail 一票否决。
- 实跑若与冻结目标、超时或策略哈希不一致会被入口拒绝，必须重新预检。
