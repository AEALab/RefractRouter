# Stage 真实小样本 v8（2026-09-25）

本批次通过 `stage-v3` 的全部真实功能验收。

- 冻结指纹：`9b95a21a0c35bef4741194be883e24eba036abbab3ae893106ef3bd19d2c9e51`
- Stage 规则：`stage-v3`
- DSH profile：`headless`
- 模型调用：5 次
- 实际费用：23.1789 AFP
- HTTP 自动重试：0
- 首字等待：1011.935666 ms
- 输出：`STAGE_PILOT_OK`
- 模型序列：Flash、Flash、Pro、Pro、Flash
- 理由序列：`no-signal`、`ambiguous`、`repeated-failure`、`capable-hold`、`ambiguous`

以下检查全部通过：

- 调用次数不超过 6；
- AFP 不超过 221.184；
- 重复失败后由 Flash 升级到 Pro；
- 触发升级的 Pro 调用与下一轮 Pro 调用构成两轮保持；
- 没有新的困难证据后恢复 Flash；
- 决策理由与冻结预期一致；
- DSH 原生 Agent 循环完成并输出最终标记。

本结果只证明当前受控轨迹上的 Stage 真实切换机制。Static Flash、Static Pro 与 Stage 的代码和
资料研究收益对比仍须由尚未授权的 72 次冻结实验验证。

可公开证据见 [pilot-summary.json](pilot-summary.json)、[dsh-stdout.txt](dsh-stdout.txt) 与
[dsh-stderr.txt](dsh-stderr.txt)。完整规划记录包含 DSH 系统提示和本机路径，仅保留在本地忽略的
`workspace/.refractagent/runs/planning/`，不提交 Git。
