# MoA 升级评审（Issue #79）

本目录由 `experiments/run_moa_escalation.py` 生成；只覆盖已确认分歧的案例。

## 冻结包络

- 案例：`prose-contradiction`、`missing-required-rule`、`missing-sampling-limitation`（3 例）
- 调用上限：6 次（两位升级评审 × 案例数），超时之和 1440 秒。
- 策略哈希：`09f8cf8bb8ce8a81a34fff20735f8c0fd20f24177e22de4dee73a3823d515a7b`。

## 升级评审

- codex-ark-kimi-k3：codex CLI，模型 `ark/kimi-k3`，thinking effort `high`。
- claude-fable：claude CLI，模型 `fable`，thinking effort `high`。

## 结果

- 调用 6 次：reviewed 3、failed 3。
- 判定：pass 0、fail 3、pending 3。
  - `missing-required-rule`：claude-fable=pending（failed）、codex-ark-kimi-k3=fail（reviewed）
  - `missing-sampling-limitation`：claude-fable=pending（failed）、codex-ark-kimi-k3=fail（reviewed）
  - `prose-contradiction`：claude-fable=pending（failed）、codex-ark-kimi-k3=fail（reviewed）

## 口径

- 升级证据必须与两位初审一起经 `experiments/aggregate_moa_consensus.py` 聚合后才形成共识；单独看升级判定不构成结论。
- 升级评审是模型共识，不是真人审查，也不能证明真实用户接受度。
- 升级判定 A 由 gpt-6-astra 改为 ark/kimi-k3（2026-09-17 用户确认），因 Codex 用量未恢复；moa-calibration-07 保持原案冻结。ark/kimi-k3 不携带 --output-schema，与 DeepSeek 初审一致。
