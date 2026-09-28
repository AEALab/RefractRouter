# Codex CLI 与 Hermes 工具证据接线验收

本批不调用付费模型。两端均使用各自已安装的原生 Agent 工具循环，Router 使用本机模拟
模型回复。固定流程为两次执行 `false`，第三次由 Stage 选择执行模型并结束任务。

| 客户端 | 工具事实 | 执行模型序列 | 结论 |
|---|---|---|---|
| Codex CLI | 两次可信非零退出 | `small → small → large` | 可选适配器接线通过 |
| Hermes | 两次可信非零退出 | `small → small → large` | 可选插件接线通过 |

原始机器摘要分别保存在 `codex-probe.json` 与 `hermes-probe.json`。Codex 探测在临时配置中
运行项目自己的钩子脚本；Hermes 探测在临时 profile 中加载真实插件。两者均没有修改用户的
常用会话、provider、凭证或默认模型配置。
两条轨迹的决策原因均为 `no-signal → ambiguous → repeated-failure`。

这只证明宿主工具事件与调用 ID 的配对和策略换模。它没有验证 Codex 桌面端、其它 Codex
执行模式、实际模型的任务收益，也没有在日常 profile 中启用可选适配。纯 Base URL 仍将
没有结构化状态的工具结果标为无法分类。
