# DSH 六策略有限端到端验收

验收日期：2026-09-29。

本目录记录 Static、Stage、Task、Composite、Advisor 和 Escalation 在用户现有 DSH profile
中的有限真实验收。测试保留 DSH 原生 Agent 循环；Router 不执行工具，不修改权限、提示、
上下文压缩或委派行为。

## 冻结范围

- 环境：DSH `0.1.5-rc.3`、插件 `0.29.0`、Python 核心 `0.15.4`。
- 配置：`refractagent-planning-v6`，六策略零调用诊断全部可用。
- 批次：六个新会话，最多 14 次远程模型调用，最多 60 AFP。
- HTTP 自动重试和委派关闭；媒体与 P6 子 Agent 共享预算不在本批次。
- Task 使用已安装的本地 Laya-MLX；本地推论不记 API 费用，质量仍按实验路线解释。

冻结任务、单项上限、验收条件和停止规则见 [preflight.json](preflight.json)。执行结果将在
真实调用后追加，不覆盖失败记录。
