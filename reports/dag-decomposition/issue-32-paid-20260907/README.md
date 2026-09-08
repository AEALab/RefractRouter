# Issue #32 首轮真实执行与格式失败诊断

**本轮真实实验在首个节点停止，未完成校准或六组对照。** 共发出 1 次模型请求，
无重试；按返回 usage 和冻结 AFP 费率确认生产费用 **0.0275 AFP**，评审费用 **0**，
未知用量预留 **0**。不能据此判断节点路由收益或分层 profile 质量。

## 授权与实际执行

用户在已列明 9 任务、六组对照、最多 456 次调用、生产 3,504.5376 AFP 与评审
15,581.1840 AFP 上限后回复“继续”，本轮据此执行，授权范围保存于
`authorization.json`。代码、清单和协议指纹在启动前与上轮验收逐项一致；使用新目录，
Agent Plan `/api/plan/v3`，零重试。上限不是实际费用，DSH 外层不在本轮范围中。

冻结规则要求首个不可用或非法结果停止。本次仅进入 `compare_cal_a` 第一次校准的
`cheap` 单模型组，节点为 `cost`，模型 API 为 `deepseek-v4-flash`。返回用量为输入
314、输出 236 token，费用为 `(314 + 236) / 1000 × 0.05 = 0.0275 AFP`。
模型响应耗时 5,454 毫秒，`finish_reason=stop`；没有截断、后续节点或评审调用。

本轮任务使用给定合成材料：试点投入 12 单位、覆盖 2 组；全面推广投入 40 单位、
覆盖 8 组；试点便于修正错误、全面推广存在培训不足风险。DAG 为独立成本分析和风险
分析后汇总。本轮处于串行校准组，第一个成本节点失败后，风险与汇总节点均未派发。

## 失败定位

模型输出的最外层是 Markdown 的 `json` 代码围栏，严格 `json.loads` 解析因此失败，
记录 `node-output-contract-invalid: expected JSON object`。

离线取出围栏内的内容后，可确认其中包含且仅包含 `result`、`evidence`、`assumptions`
三个非空字符串字段。这个操作只用于诊断；运行时没有去围栏修复，没有把本轮改判为
成功，也没有独立语义评审，因此不能宣称内容质量通过。

现有节点执行会请求 JSON 模式。离线重建 HTTP 请求的测试确认
`response_format={"type":"json_object"}` 会进入请求体；本轮归档保留了应用层消息、
有效模型清单、实际端点进度和返回正文，没有完整 HTTP 请求体抓包。不能仅凭这次结果
断言供应商是否忽略或如何实现 `response_format`。

原提示要求 JSON 字段，但未明确禁止 Markdown 围栏。本轮只加强节点指令：返回单个
原始 JSON 对象，禁止对象外文字和围栏；保持严格输出校验与原字段要求。修改后的提示
能否提高真实格式通过率，仍需新的受控验证，不能由离线通过推定。

## 离线修复验证

完整回归 **224 项测试、5 项子测试通过**，原始日志为 `pytest-after-diagnosis.log`。
新增测试覆盖真实归档响应回放、围栏仍被拒绝、首错停止并保留 0.0275 AFP 的模拟记账、
HTTP JSON 模式构造、三模型格式通过但不宣称语义通过、付费参数缺失时零派发。
测试中的回放不发起网络或新增费用；真实执行次数仍为 1。

严格解码器保持不变。原始任务、节点和契约也保持不变；新回放协议固定原始请求与失败
产物哈希，以及加强后消息的哈希，提示或来源变化会拒绝执行。

## 下一步小额验证（尚未授权执行）

[data/benchmarks/dag-handoff-replay-v1.json](../../../data/benchmarks/dag-handoff-replay-v1.json)
冻结对原成本节点的三模型格式验证：`deepseek-v4-flash`、`minimax-m3`、
`deepseek-v4-pro` 各最多 1 次，零重试，首个失败停止。没有下游或评审调用，格式通过
也不会自动重启完整实验。零调用预检已保存于 `replay-preflight/`。

生产费用保守上限 **20.8896 AFP**，评审费用 **0**，最多 **3 次调用**。
范围只涵盖格式契约，不生成校准 profile，不判断语义质量或路由收益。
协议指纹为 `88935aac2317b7ddb2125d49b6a606e2179dfdb34c1b4e0d101ad14ecb75af35`。

```bash
uv run python -m experiments.replay_text_node_contract \
  --output-dir /tmp/text-node-replay-preflight-new
```

获准后才可使用 `--execute-paid-run`、上述 `--approved-protocol-sha256` 及
`--max-production-cost 20.8896`，输出到新的目录。本报告不是新增授权。
原全量方案遵守首错停止规则；修改提示后的回放属于新范围，未消耗旧上限的剩余余额。

## 证据

- `run-01/`：未改写的真实请求/响应、失败节点、计划、费用、有效清单、实现指纹和进度。
- `run-01/artifact-index.json`：原始执行产物哈希，诊断前后逐项一致。
- `diagnosis.json`：零调用诊断及明确的语义未评估状态。
- `execution.log`、`preflight.json`、`authorization.json`：实际命令结果、原范围预检及授权。
- `replay-preflight/`：新格式验证的冻结协议与零调用费用预检。
- `verification-index.json`：本次诊断后源码与外层说明的指纹；不替换原运行索引。

第 6 项真实组合验收仍未完成，第 4 项真实分层数据和第 7 项 DSH 实际助手调用也未完成。
参考 [完整实验指南](../../../docs/dag-study.md)。本地改动尚未提交或发布。

本轮按 Craft Wiki 评估了一条候选经验；围栏与严格 JSON 不兼容属于常规格式诊断，
未达到新增非显然决策规则的门槛，本次跳过摄入。
