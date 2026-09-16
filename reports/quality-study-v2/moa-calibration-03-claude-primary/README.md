# Claude 单侧初审证据（Issue #79）

本目录记录 Claude CLI 单侧完成的 19 例开发正负例初审。Codex 用量上限尚未解除，因此这不是完整 MoA 共识，只能作为单侧证据保留。

- claude-primary-first-run.jsonl：按 case_id 去重后的首轮 19 例结果。
- claude-primary-all-calls.jsonl：保留全部 31 次原始调用，包括误启动造成的重复调用。
- summary.json：首轮结果、重复调用与冲突统计。
- preflight.json：本轮使用的冻结预检。
- artifact-index.json：文件哈希索引。

结论口径：首轮 19 例中，12 例可接受、7 例不可接受；未出现误放行或误拒绝。重复调用中 rules-01-equivalent 出现一次 pass/fail 冲突，说明该用例对单模型判定存在敏感性；完整 MoA 仍需等待 Codex 恢复后补齐另一位初审。
