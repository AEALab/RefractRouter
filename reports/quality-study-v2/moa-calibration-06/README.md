# MoA 双初审逐 criterion 共识（Issue #79）

本目录由 `experiments/aggregate_moa_consensus.py` 从既有单侧初审证据聚合生成，聚合过程不发起任何模型调用。

## 来源

- primary：`reports/quality-study-v2/moa-calibration-03-claude-primary/claude-primary-first-run.jsonl`（19 例，sha256 `d208b64a8ff5daeb3bc8ded4be198d47fdd9f1457b549bd61736d33bc008ce6c`）
- primary：`reports/quality-study-v2/moa-calibration-05/deepseek-primary-first-run.jsonl`（19 例，sha256 `7f198ee1160def5facb78ca5f5e6ad5f55a2c0ed5df34b0f151be5d3a362b776`）

## 结果

- 案例：19 例（可接受 12、不可接受 7）。
- 共识判定：pass 9、fail 6、pending 4；最终门槛同为 pass 9、fail 6、pending 4。
- 误放行 0、误杀 0；待判定落在不可接受例 1 例、可接受例 3 例。
- 确定性检查与作者预期不一致：0 例。
- 升级状态：not-executed。未执行升级评审：当前没有升级证据，分歧 criterion 与缺少有效初审的 criterion 一律保留 pending，不推测升级结论。
- 分歧 criterion 5 项，无效初审记录 3 条，聚合使用调用记录 38 条。

## 分歧明细

- `prose-contradiction`（作者标签 unacceptable，初审 claude-opus=fail、ds-deepseek-v4-pro=fail，共识 fail）：
  - 必需结论完整、事实正确且各自引用足以支持主张
- `missing-required-rule`（作者标签 unacceptable，初审 claude-opus=fail、ds-deepseek-v4-pro=fail，共识 fail）：
  - 最终正文符合材料、任务要求与全部硬约束
  - 不可把口头归还视作已完成手续。
- `missing-sampling-limitation`（作者标签 unacceptable，初审 claude-opus=fail、ds-deepseek-v4-pro=pass，共识 pending）：
  - 最终正文符合材料、任务要求与全部硬约束
  - 不把工单当客户数；分别分析两来源并说明抽样与重叠限制。

## 口径

- 两位初审模型的逐 criterion 共识；分歧在缺少升级证据时保留 pending。不是真人审查，也不能证明真实用户接受度或独立留出任务质量。

- 升级评审（codex-gpt-astra 与 claude-fable）尚未执行：本机自动审批审查因上游 provider 报错无法放行外部 CLI 调用，因此 3 例分歧案例的 5 项 criterion 与 3 条 DeepSeek 解析失败记录保持 pending。
