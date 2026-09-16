# MoA 升级评审（Issue #79）

本目录由 `experiments/run_moa_escalation.py` 生成；只覆盖已确认分歧的案例。

## 冻结包络

- 案例：`prose-contradiction`、`missing-required-rule`、`missing-sampling-limitation`（3 例）
- 调用上限：6 次（两位升级评审 × 案例数），超时之和 1440 秒。
- 策略哈希：`1f620cbbb46c379fe4453596c3e83a85c66dba0d147d20b29e5a5e3a0ea7f0e3`。

## 升级评审

- codex-gpt-astra：codex CLI，模型 `gpt-6-astra`，thinking effort `high`。
- claude-fable：claude CLI，模型 `fable`，thinking effort `high`。

## 结果

- 尚未执行 `--live`，本目录目前只有零调用冻结。

## 口径

- 升级证据必须与两位初审一起经 `experiments/aggregate_moa_consensus.py` 聚合后才形成共识；单独看升级判定不构成结论。
- 升级评审是模型共识，不是真人审查，也不能证明真实用户接受度。
- 升级评审身份为 codex-gpt-astra（gpt-6-astra，high）与 claude-fable（fable，high）；本机 Codex 用量上限尚未解除，--live 前需确认两者可用。
