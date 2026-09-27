# Hermes 独立模型接口验收

## 范围与版本

本次接入范围固定为 DSH、Codex、Hermes，不扩展其他客户端。
Hermes Agent 0.21.5（2026.9.24），本机提交
`deb4bd2c085757b3a5329d3a684d0ce395cc9a05`，Python 3.11.15，OpenAI SDK 2.24.0。
Router 核心保持 0.15.1；本次新增集成验收驱动，没有修改核心策略。

驱动调用已安装 Hermes 的 `AIAgent.run_conversation`，使用其真实 Agent 循环与 terminal 工具。
Base URL 指向独立 Router；模型回复中的工具交给 Hermes 执行。
这证明原生 Agent 接口路线，不等同于 Hermes 全部 CLI、桌面或聊天渠道已经验收。

## 接入与问题修正

- 按 Router 模型目录读取实际冻结推理档位，作为本次 Agent 构造参数。
- 第一轮因客户端默认推理档位不一致在派发前拒绝，0 次上游调用、0 AFP。
- 第一轮还提示子进程没有继承当前 profile；驱动已在导入 Hermes 前解析现有 active profile，
  沿用 `jasmine`。未创建或替换用户 profile，未修改模型、provider、凭证或日常预算。
- 测试实例限定 terminal 工具集、三次循环上限；禁用背景评审和记忆，以隔离受管调用范围。
- 实例级应用重试设为一次尝试，SDK 自动重试为零，流式重试为零，回退链为空。
  这些是验收驱动的临时参数，未写回 Hermes 配置。

## 无付费接线

模拟上游驱动实际 Hermes 完成两次请求、一次终端工具往返。
Router 始终只有一个任务，收到工具结果，Hermes 收到流式回调；上游模型费用为零。

真实客户端零调用探测测得 4 个工具定义、保守输入计数 15427。
输入计数按序列化字节数估算 token 上界，不是实际 token 用量。
冻结真实批次输入上界 24576、每次输出上界 512、最多两次调用，总费用上界 2.5088 AFP；
独立验收预算为 3 AFP，未修改用户日常设置。Hermes 驱动实际请求输出上限为 256。

## 真实模型结果

Static → Ark Agent Plan `/api/plan/v3` → `deepseek-v4-flash / low`。
Hermes 自行执行 `printf REFRACT_HOST_TOOL_OK`，收到结果后回答 `GATEWAY_CLIENT_OK`。

| 调用 | 输入 token | 输出 token | AFP |
|---|---:|---:|---:|
| 终端工具请求 | 3687 | 65 | 0.1876 |
| 工具结果续接 | 3787 | 7 | 0.1897 |
| 合计 | 7474 | 72 | **0.3773** |

两次均已结算，无未知用量、自动重试或模型回退；一个 Router 任务、一个宿主工具结果。
第二轮模型文字首字 919 ms，用户首字等待 924 ms；首轮为工具调用，无文字首字记录。
单样本不证明平均速度、质量提升或成本优势。

## 完整回归

`uv run pytest`：**1338 passed**，包含既有核心、插件契约及构建测试。
Hermes 原生 Agent 的模拟和真实接线另外按上述批次执行。

## 三客户端状态

| 客户端 | 真正验收的接入面 | Static 真模型工具往返 |
|---|---|---|
| DSH 0.1.5-rc.3 | 原生 DeepSeekAdapter、Session、ToolRuntime，测试驱动组织两轮 | 通过，0.0365 AFP |
| Codex CLI 0.154.0 | 实际 CLI、Responses、本机模型目录适配 | 通过，6.21375 AFP |
| Hermes 0.21.5 | 已安装 AIAgent 原生循环、Chat Completions、terminal 工具 | 通过，0.3773 AFP |

三条路线提示和工具数量不同，不横向比较这些费用。
Stage、Task、Escalation 的三客户端真实接线矩阵仍未完成。
取消、断流和未知用量已有核心确定性覆盖，尚未逐个客户端进行故障注入，不能据此标为全通过。

## 证据与复现

- `experiments/validate_gateway_clients.py --client hermes --hermes-root <安装目录>`：模拟上游。
- `experiments/validate_gateway_static_live.py --client hermes --hermes-root <安装目录>`：
  默认零调用预检；`--probe-client` 测量请求，`--execute` 仅执行冻结的新批次。
- 本地完整记录保存在 `.refractagent/acceptance/hermes-gateway-20260927/`，不公开宿主请求原文。
- 公开文件仅包含预检、汇总及脱敏用量。历史失败记录继续保留。

经验库仅评估“逐接入面声明验收范围”这一候选，既有能力成熟度规则已覆盖，跳过重复记录。
