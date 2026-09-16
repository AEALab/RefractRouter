# MoA 升级评审（Issue #79）

本目录由 `experiments/run_moa_escalation.py` 生成；只覆盖已确认分歧的案例。

## 冻结包络

- 案例：`prose-contradiction`、`missing-required-rule`、`missing-sampling-limitation`（3 例）
- 调用上限：6 次（两位升级评审 × 案例数），超时之和 1440 秒。
- 策略哈希：`0f335a4bbcd02786e43e68fc1980fbf59b2ab9e01581ed9f1702ff855a43d55c`。

## 升级评审

- codex-ark-kimi-k3：codex CLI，模型 `ark/kimi-k3`，thinking effort `high`。
- claude-opus-max：claude CLI，模型 `opus`，thinking effort `max`。

## 结果

- 调用 6 次：reviewed 5、failed 1。
- 判定：pass 0、fail 5、pending 1。
  - `missing-required-rule`：claude-opus-max=fail（reviewed）、codex-ark-kimi-k3=fail（reviewed）
  - `missing-sampling-limitation`：claude-opus-max=fail（reviewed）、codex-ark-kimi-k3=pending（failed）
  - `prose-contradiction`：claude-opus-max=fail（reviewed）、codex-ark-kimi-k3=fail（reviewed）

## 口径

- 升级证据必须与两位初审一起经 `experiments/aggregate_moa_consensus.py` 聚合后才形成共识；单独看升级判定不构成结论。
- 升级评审是模型共识，不是真人审查，也不能证明真实用户接受度。
- 升级判定 B 由 fable 改为 opus max（2026-09-17 用户确认）；fable 因需要额外 usage credits 无法使用，失败证据留在 moa-calibration-08。
