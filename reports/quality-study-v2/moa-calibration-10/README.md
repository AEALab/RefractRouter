# MoA 双初审逐 criterion 共识（Issue #79）

本目录由 `experiments/aggregate_moa_consensus.py` 从既有单侧初审证据聚合生成，聚合过程不发起任何模型调用。

## 来源

- primary：`reports/quality-study-v2/moa-calibration-03-claude-primary/claude-primary-first-run.jsonl`（19 例，sha256 `d208b64a8ff5daeb3bc8ded4be198d47fdd9f1457b549bd61736d33bc008ce6c`）
- primary：`reports/quality-study-v2/moa-calibration-05/deepseek-primary-first-run.jsonl`（19 例，sha256 `7f198ee1160def5facb78ca5f5e6ad5f55a2c0ed5df34b0f151be5d3a362b776`）
- escalation：`reports/quality-study-v2/moa-calibration-09/escalation-calls.jsonl`（6 条调用记录，sha256 `0dd95f036589c311ccd0ba072360e103c640ac6d3c646ad1a7bfc5b520e21907`）

## 结果

- 案例：19 例（可接受 12、不可接受 7）。
- 共识判定：pass 9、fail 6、pending 4；最终门槛同为 pass 9、fail 6、pending 4。
- 误放行 0、误杀 0；待判定落在不可接受例 1 例、可接受例 3 例。
- 确定性检查与作者预期不一致：0 例。
- 升级状态：executed。已执行升级评审，分歧 criterion 由两位升级评审复评。
- 分歧 criterion 5 项，无效初审记录 4 条，聚合使用调用记录 44 条。

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

- 升级判定 A 使用 ark/kimi-k3（Codex 用量未恢复时经维护者确认的替代），升级判定 B 使用 opus / effort max（fable 因 usage credits 不可用）。两者与初审判定 B 同属 claude 侧时共识只能表述为同侧更高 effort 复核。
- 案例 missing-sampling-limitation 的升级判定 A 返回带代码围栏的 JSON，按严格 JSON 规则记为 failed / pending，零重试规则下未自动重发；该例分歧 criterion 因此保持 pending。
