# #39、#40 离线准备验证

本次为草案检查，不是付费实验结果。#41 按用户要求跳过。

- 完整测试：`UV_CACHE_DIR=/tmp/refractrouter-uv-cache uv run pytest -q`。
- 结果：560 passed，5 subtests passed，耗时 53.32 秒。
- 新增 25 项测试覆盖断网预检、来源与材料重复、输入实测、协议变化、
  串行依赖、计划分母、未知费用、共同配对、任务级聚类和缓存设置成本。
- 真实模型调用：0；付费费用：0。
- 历史 K3 成功基线新增精确代码快照兼容记录；原始证据未修改，
  已完成探针仍禁止跨代码快照继续 compose/finalize。完整测试覆盖这一边界。

草案及包络：

| 研究 | 草案 JSON 摘要 SHA-256 | 包络 |
| --- | --- | --- |
| #39 | `f1b02a57042ac6d9bb8f4769e3fac940d94039f07e928bf66eec2a110aa4e5f2` | [零调用预检](issue-39-research-draft-v1/preflight.json) |
| #40 | `e39638ba781cc05449f65754241b20a851d350e8829ee91effc742a8bbef545a` | [零调用预检](issue-40-research-draft-v1/preflight.json) |

摘要按 `research_protocol.digest` 对排序键后的 JSON 计算，不是文件字节哈希。
预检中的 `live_execution_ready=false` 是刻意保留的边界：
共享模板材料尚未通过独立性审查，真实运行器及人工复核仍未完成。
两项 Issue 保持开放，不从模拟或预检数据推出收益结论。

后续工作与限制见[研究草案](../../docs/research-39-40-draft.md)。
