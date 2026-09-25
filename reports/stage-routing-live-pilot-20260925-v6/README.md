# Stage 真实小样本 v6（2026-09-25）

本批次首次完成真实 DSH 原生工具循环，但没有通过 Stage 换模验收。

- 冻结指纹：`fe49c711cd572806aead4277f35b733f8bd12314c47bf87a1b9b436fd39de23d`
- DSH profile：`headless`
- 模型调用：5 次
- 实际费用：15.65375 AFP
- HTTP 自动重试：0
- 结果：DSH 正常完成，输出 `STAGE_PILOT_OK`
- 路由：五次均为 `deepseek-v4.1-flash`，没有切换到 `deepseek-v4-pro`

根因是 DSH 持久消息把非零 Bash 退出保存在渲染文本中，并将 `isError` 保持为 `false`；旧适配
路径没有取得工具流水线中的规范 `exitCode`，因此 Python 将两次结果归类为完成。运行后已改为在
DSH `tools/result` 通知中捕获规范 Bash 结果，再把结构化事实交给 Python 归一化。正文中的
`[exit code: N]` 不参与判定。

修正后的 Python 测试与插件契约测试已通过。本批次是失败证据，不能改写为成功；复验必须使用
新的输出目录和新的调用授权。

可公开证据见 [pilot-summary.json](pilot-summary.json)、[dsh-stdout.txt](dsh-stdout.txt) 与
[dsh-stderr.txt](dsh-stderr.txt)。完整规划记录包含 DSH 系统提示和本机路径，仅保留在本地忽略的
`workspace/.refractagent/runs/planning/`，不提交 Git。
