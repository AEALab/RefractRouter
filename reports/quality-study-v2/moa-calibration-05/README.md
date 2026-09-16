# DeepSeek 单侧初审证据（Issue #79）

本目录记录 ds/deepseek-v4-pro（thinking effort max）通过 codex CLI 完成的
19 例开发正负例单侧初审。这是 Issue #79 第三轮 MoA 初审判定 A 的替代证据，
不是完整 MoA 共识，也不能替代另一位初审。

## 证据

- preflight.json：零调用冻结预检，19 个目标。
- run-manifest.json：运行身份、时间、续跑与异常说明。
- deepseek-primary-all-calls.jsonl：原始调用证据，包含重复记录和损坏尾部。
- deepseek-primary-first-run.jsonl：按预期顺序去重后的首轮 19 例证据。
- deepseek-primary-sandbox-failed.jsonl：沙箱内 CLI 初始化失败的 19 条证据。
- summary.json：状态与判定统计。
- artifact-index.json：核心产物 SHA-256 索引。

## 运行说明

DeepSeek 上游不支持 codex CLI 的 --output-schema response format，因此本轮
冻结策略关闭该参数，并依靠系统提示中的严格 JSON 约束。并发续跑导致
rules-02-equivalent 出现重复、尾部出现一条损坏记录；原始字节全部保留，
首轮证据按预期顺序取每个 case 的首次有效记录。零重试协议保持不变，
解析失败保留为 failed/pending，不重跑。
