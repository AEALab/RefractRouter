# Stage 真实小样本 v7（2026-09-25）

本批次验证了真实模型切换，但没有通过冻结的决策理由验收。

- 冻结指纹：`fe49c711cd572806aead4277f35b733f8bd12314c47bf87a1b9b436fd39de23d`
- DSH profile：`headless`
- 模型调用：5 次
- 实际费用：23.2942 AFP
- HTTP 自动重试：0
- 输出：`STAGE_PILOT_OK`
- 模型序列：Flash、Flash、Pro、Pro、Flash
- 实际理由：`no-signal`、`ambiguous`、`tool-signal`、`capable-hold`、`ambiguous`

模型序列、调用上限、AFP 上限、最终输出与 DSH 完成状态均通过。唯一失败项是第三轮理由：
两次 Bash 命令完全相同，但模型生成的展示 `description` 不同，导致旧指纹没有将它们识别为
同一失败。窗口内两个失败仍使信号分数超过阈值，因此模型正确升级，但理由退化为通用
`tool-signal`。

运行后已升级到 `stage-v3`：shell 失败指纹保留命令和其他执行参数，排除不影响执行的
`description`，并将规则版本加入后续零调用预检指纹。确定性测试使用 v7 的参数差异验证
`repeated-failure`。`stage-v3` 后续复验的新冻结指纹为
`9b95a21a0c35bef4741194be883e24eba036abbab3ae893106ef3bd19d2c9e51`。本批次原记录保持失败，
不覆盖、不重算，也没有自动发起新的真实调用。

可公开证据见 [pilot-summary.json](pilot-summary.json)、[dsh-stdout.txt](dsh-stdout.txt) 与
[dsh-stderr.txt](dsh-stderr.txt)。完整规划记录包含 DSH 系统提示和本机路径，仅保留在本地忽略的
`workspace/.refractagent/runs/planning/`，不提交 Git。
