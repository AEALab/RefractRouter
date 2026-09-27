# 独立网关流式与客户端验收

## 本轮交付

日期：2026-09-27。核心 0.15.0，DSH 0.1.5-rc.3，插件维持 0.27.0。
在既有独立接口上增加真实上游 SSE 文本传递、function 命名空间转换及历史等价表示兼容。
工具执行、权限、提示、上下文和任务推进继续由接入方负责。

工具完成事件在核心接受回复、结算及保存续接信息之后发送。
Escalation 高效候选全部缓冲；丢弃候选不交付，强模型接管可实时输出。
取消后停止新派发，已派发调用继续核对用量；未知用量保留预留，不重试。

## 验收范围

| 路线 | 实际执行 | 结果 |
|---|---|---|
| Codex CLI 0.154.0 → Responses → 模拟上游 | 实际 CLI 自行执行终端工具，完整往返两次 | 通过，零付费 |
| DSH 标准适配器 → Chat Completions → 模拟上游 | 实际 Session、ToolRuntime 执行一次工具，两次请求 | 通过，零付费 |
| DSH 标准适配器 → Chat Completions → Ark | 实际模型选择工具、宿主执行、模型接收结果 | 通过，2 次付费调用 |

DSH 驱动器不加载 RefractAgent 插件，两步执行由测试驱动组织，不代表完整浏览器 Agent UI
已通过独立网关验收。Codex 上游为确定性夹具，不代表已验收 Codex 的真实模型回答质量。
三条流程均保持一个 Router 任务；没有内部工具循环、DAG 或 HTTP 自动重试。
用户日常 provider、默认模型、预算与 profile 未由验收脚本修改。

## 真实费用与延迟

调用固定为 Static、Ark Agent Plan `/api/plan/v3`、`deepseek-v4-flash`、推理 `low`。
冻结每次输入上界 8192、输出上限 512 tokens，共两次；预检上界 0.8704 AFP，
独立验收配置硬上限 1 AFP，没有修改用户的单任务配置。

| 调用 | 输入 token | 输出 token | 费用 |
|---|---:|---:|---:|
| 首轮工具请求 | 290 | 62 | 0.0176 AFP |
| 工具结果续接 | 371 | 7 | 0.0189 AFP |
| 合计 | 661 | 69 | **0.0365 AFP** |

按冻结输入、输出均 0.05 AFP/千 token 复算；两次均已结算，没有未知用量。
第二次首段可见文字等待为 1366 毫秒。第一次为纯工具回复，未记录文字首字时间，
不能把空值当作零毫秒。此处只有一个工具任务，不用于宣称性能或成本收益。

## 确定性测试与安装

- 完整 `uv run pytest`：**1330 passed**，包括插件契约及构建覆盖。
- TypeScript 严格类型检查通过。
- 流式屏障测试证明下游收到首段文字时，上游尚未结束；覆盖两种协议。
- 覆盖中断、缺少用量、取消、Escalation 缓冲、工具命名空间及历史续接。
- 历史比较只规范化已知等价的空文本、JSON 键序和空白；重复键、参数变更及额外参数
  不能被当作等价历史放行。不使用消息 hash 代替任务身份。
- 最终 wheel 已安装，三个网关模块与源码逐字节一致，摘要见 `artifacts.json`。

原始完整运行记录在本地忽略目录 `.refractagent/acceptance/gateway-20260927/` 保存；
公开证据仅保留预检、汇总、测试日志和产物摘要，避免公开用户路径、会话与请求原文。

## 限制与下一步

- Codex 仍提示虚拟模型缺少专用模型目录元数据，使用客户端默认回退；本轮关闭托管搜索。
- 仅文本、function、全历史请求子集；媒体、custom tools、托管工具、私有 reasoning 历史
  和增量 response ID 尚未验收。客户端显式 reasoning effort 当前拒绝，采用角色冻结值。
- 本轮真实客户端路线为 Static；Stage、Task、Escalation 的客户端真模型矩阵仍需逐项验证。
- 普通工具正文不提供可信退出状态；Stage 不从正文猜测失败，缺证据时使用高效模型。
- Hermes、OpenClaw、Claude 及完整 Codex App 未验收，不能宣称任意 Agent 仅改 URL 即兼容。
- 未启动长期运行的生产网关；用户原 DSH 服务继续运行。本轮安装不自动更改其模型入口。
- 下一步是处理客户端模型元数据与参数协商，再选择一个日常客户端完成真实端到端任务。

## 参考

- [Codex 配置说明](https://learn.chatgpt.com/docs/config-file/config-reference)
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [接口边界与启动方法](../../docs/independent-model-router.md)

经验库仅评估历史等价比较这一候选；通用适用边界尚未充分验证，保留原始待验证笔记。
