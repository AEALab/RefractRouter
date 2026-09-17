# MoA 用途确认评审第 4 轮（补入统计策略内容后仍缺研究用途原文）

本目录保留第 4 轮用途确认的原始证据，用于说明第 5 轮为何还要再补研究目的描述。

## 载荷与本轮差异

- 相对第 3 轮（`../moa-purpose-03/`）多出 `statistics_policy` 的实际内容，但缺少 Issue #52 的
  研究用途原文或摘要。
- 统计策略 sha256 `56694f60eec90621d45087ebe2da4318d574f318dd9a184abd6891ee1649e0d2`，
  与第 5 轮相同，说明本轮分歧来自载荷缺少用途原文，而不是策略内容变动。

## 结论

- 初审 `ds/deepseek-v4-pro`（max）判 pass，用时 59.6 秒。
- 初审 `claude-opus`（high）判 pending，用时 17.1 秒，理由是「材料里没有 #52 的原文或摘要，
  无法确认两边一致」。
- 升级 `codex-ark-kimi-k3`（high）判 pass，用时 70.1 秒；升级 `claude-opus-max`（max）判
  pending，用时 221.3 秒，除同样缺少用途原文外，另指出未写明门槛按观测比例还是精确界判定。
- 逐 criterion 共识 `overall = pending`，因此本轮不能关闭 Issue #52 的第三项门槛。

## 边界

- 本目录为历史证据，不修改；结论边界与第 5 轮相同，不构成真人审查。
- `artifact-index.json` 记录本目录除索引自身外的全部文件摘要。
