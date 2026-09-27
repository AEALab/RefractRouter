# 独立模型路由与宿主边界

决策日期：2026-09-27。适用版本：Router 0.15.1、DSH 插件 0.27.0。

## 产品目标

RefractRouter 为小型开发团队提供独立的模型路由选择服务。优化顺序是：

1. 满足团队为任务规定的可接受质量、能力、数据域与可靠性要求。
2. 在合格候选中降低全部模型调用成本，包括 Judge、丢弃回复与接管。
3. 在成本可比的条件下减少首次可见输出和任务完成的等待时间。

可接受质量需要来自任务验收与团队反馈；Judge 的适合度和确定性分数不是成功率。
当前 Task 的首次调用费用上界也不是整任务预期费用，不把它描述为全局成本最优。
AFP 与 CNY 分账，未经团队明确提供可比较依据，不把订阅点数等同于现金。

## 职责

| RefractRouter 拥有 | 接入方 Agent 拥有 |
| --- | --- |
| 模型目录、能力与价格依据、选择策略 | 任务推进、工具与子 Agent 调度 |
| 模型/Judge 调用的准入、预留、结算 | 工具权限、审批、文件及终端执行 |
| 逐调用状态与已接受/丢弃回复的记录 | system prompt、技能、上下文压缩、会话界面 |
| 模型协议转换、来源记录和传输故障处理 | 已发出工具调用的执行、结果返回及生命周期 |

标准接口不注入系统提示，不创建 DAG，不执行工具，不重做宿主已完成的工具，
不识别客户端品牌后修改它的 Agent 行为。不同客户端的适配是消息协议问题。
DSH 插件仍负责其设置、模型入口、原生事件与轨迹展示，Python 保留策略业务。
历史 DAG 自动路由、实验执行器与内部工具循环继续作为独立研究入口保留。
独立模型接口不导入或调用 DAG 执行流程，也不将其作为外部 Agent 请求的默认行为。

## 两种 HTTP 入口必须区分

- `refractrouter-gateway`：本次新增的标准模型接口，客户端配置 Base URL 和虚拟模型名称。
- `refractagent serve`：历史自定义任务 HTTP 协议；不能把它描述为 OpenAI 兼容模型 Base URL。

运行独立模型服务不需要 DSH，也不读取 DSH 凭证文件。服务端配置引用自己的凭证环境变量。
`planningRouting` 沿用现有版本化策略设置；`providers` 独立配置真实调用端点。
现有 DSH profile 的模型、凭证、预算与默认策略不会迁移或改写。

```sh
refractrouter-gateway --config /absolute/path/gateway.json \
  --runs-dir /absolute/path/router-evidence --preflight
refractrouter-gateway --config /absolute/path/gateway.json \
  --runs-dir /absolute/path/router-evidence --host 127.0.0.1 --port 8088
```

客户端 Base URL：`http://127.0.0.1:8088/v1`。
模型 ID：`refract/static`、`refract/stage`、`refract/task`、`refract/escalation`。
`GET /v1/models` 只返回配置预检可用的策略。模型 ID 也可以使用不带前缀的策略名。

配置结构示意如下，`planningRouting` 需填入经核对的角色、能力、价格与额度；
示意不是可直接用于生产的免费价格预设。

```json
{
  "authTokenEnv": "REFRACTROUTER_API_KEY",
  "providers": {
    "ark": {
      "baseURL": "https://ark.cn-beijing.volces.com/api/plan/v3",
      "apiKeyEnv": "ARK_API_KEY",
      "timeoutSeconds": 120,
      "tokenLimitParameter": "max_tokens"
    }
  },
  "planningRouting": {}
}
```

`--preflight` 不调用模型，但要求配置、价格和所引用凭证可用。
对外监听必须配置服务认证。部署到团队网络时还需要运维层的 TLS、访问控制、容量限制和备份。
本版策略额度仍是任务额度；不是所有团队成员的共享资金池或 P6 共享预算。

## 已接通的协议范围

| 路线 | 本版状态 |
| --- | --- |
| Chat Completions 文本/function 输入、输出 | 已实现，真实核心与模拟上游验收 |
| Chat Completions SSE 与 usage | 普通执行文本实时交付；工具与成功结束事件等待结算 |
| Responses 完整文本/function 历史、`store=false` | 已实现，协议往返及 HTTP SSE 验收 |
| 上游 Chat Completions | 已实现，零自动重试，独立凭证引用 |
| 上游 Responses、Anthropic Messages | 独立网关未接通；原有其他入口的适配不代表这里已通过 |
| 媒体、托管工具、custom tool、加密 reasoning replay | 当前网关拒绝，不静默丢弃 |
| `previous_response_id`、Responses 存储式增量会话 | 当前网关拒绝；由客户端保存并回传完整历史 |
| DSH 0.1.5-rc.3 标准适配器与 ToolRuntime | 无 RefractAgent 插件的模拟上游、真实 Ark 两轮均通过 |
| 本机 Codex CLI 0.154.0 | 实际 CLI + 模拟及真实 Ark 上游工具往返通过；限定 Static 与下述配置 |
| Hermes 0.21.5 | 已安装 AIAgent 原生循环及真实 Ark 工具往返通过；限定 Static |

`stream=true` 时，Static/Stage/Task 及已接管的 Escalation 实时转发上游文字增量。
工具调用在拼接完成、核心接受并结算后输出，防止部分工具参数被执行。
Escalation 起始候选及 Judge 继续缓冲；审核通过后才释放候选，接管回复可实时输出。
私有推理保留在服务端 replay，不作为公开文字流输出。

上游缺少最终 usage、流中断或结算失败时，只发送错误，不发送成功结束事件，保留费用预留。
已经展示的文字不替换。客户端取消后停止进一步交付及后续派发，已在途调用继续尝试结算，
未知用量不释放。SSE 解析及缓冲总量上限 8 MiB，每次派发零自动重试。
确定性测试使用上游完成屏障，验证首段文字在上游尚未完成时已到达客户端。
DSH 插件自身流式行为保持原状。

未知参数在派发前拒绝，不能为了让某个客户端“连上”就删除它的工具约束或推理数据。
协议转换保留工具名称、调用 ID、参数、结果配对及角色；不执行工具。

## 状态与任务边界

标准 API 不保证提供真实 session、任务轮次或“追加指导”标识。
仅凭相同的首条消息不能把请求合并成同一个任务。

本版默认行为：

- 新请求分配独立身份，相同提示也不共用预算或升级状态。
- 客户端返回本服务刚交付的 function call ID 时，核对已接受历史前缀后续接同一任务。
  比对容许 JSON 对象字段顺序、工具参数 JSON 空白及空 assistant 文本的等价表示，
  不容许指令、有效文字、工具参数值或调用 ID 改变。
- 新 user 消息默认建立新任务；无法自动判断它是指导、压缩摘要还是新的任务。
- 如客户端能提供可信身份，可在 `metadata` 同时传 `refract_session`、`refract_task`。
  两者不随工具续接或追加指导改变，只有新任务才改变 task 值。
- 参数与策略在该任务冻结，任务中切换策略明确拒绝。
- 服务器重启后保留账本与工具关联，但不自动恢复可能已计费的执行。

这是一项信息边界，不应由 Router 通过替宿主管理对话或重写工具 ID 来掩盖。

## 证据、错误和费用

`host_evidence.py` 定义中立工具事实合同。DSH 特定字段转换集中在 `dsh_evidence.py`，
旧插件协议仍可读取。独立接口仅凭文本工具结果不能确认退出状态，记录为 `unclassified`；
Stage 不把它当作成功或模型能力失败。Escalation 的 Judge 仍可审查文本轨迹，但分数需独立验收。

同一事实去重，矛盾事实拒绝。并发的第二个 step 只拒绝该请求，不能取消原在途调用。
认证、传输、未知用量及证据写入故障停止后续受管调用。客户端断开后不再派发下一 Judge
或接管；已派发调用返回后结算，未知用量保留预留。没有底层自动 HTTP 重试。

标准响应 `usage` 汇总本次流程全部真实模型调用的 token；准确 AFP/CNY 费用、真实模型与
被丢弃回复以 Python 账本为准，不能用外层虚拟模型的单一价格重新推算混合费用。

## 客户端接入验收范围

2026-09-27 的 [接线与流式报告](../reports/gateway-client-acceptance-20260927/README.md)
分别保存模拟上游与真实模型证据。它验证已安装的客户端协议及原生工具，不是效果对照实验。

DSH 使用标准 Chat Completions Base URL 和 `refract/static` 模型即可走独立网关。
验收使用真实 DSH 的 `DeepSeekAdapter`、`Session`、`ToolRuntime`，没有加载 RefractAgent 插件；
两步调用由验收驱动器组织，不能描述为浏览器中完整 Agent UI 的验收。

本机 Codex CLI 验收使用 Responses、`store=false`，关闭托管 web search，客户端 HTTP
与流式重连次数均设为零。CLI 自行运行终端工具并返回结果，Router 只返回工具调用。
验收通过命令行临时覆盖 provider，不修改日常用户配置、认证、模型或默认 Agent。

- function 命名空间映射到稳定无冲突别名，保留 schema；回复还原原始 namespace/name。
- `prompt_cache_key` 作为不透明缓存提示转发；不将其当作真实任务 ID。
- `reasoning.summary=auto` 与 `include=[reasoning.encrypted_content]` 可作为可选返回提示。
  本网关不生成加密推理项；收到真正的 reasoning 历史项仍明确拒绝。
- 实际推理档位由路由角色配置冻结。`reasoning.effort` / `reasoning_effort` 可作为一致性断言：
  仅当所有可能执行模型的有效冻结值相同且与请求一致时接受；不覆盖角色或 Judge 参数。
  混合档位或未配置档位时应省略该参数，不把“未设置”等同于 `none`。
- `/v1/models` 的 `refract` 扩展公开文本/function 范围、执行模型容量交集及可接受推理档位。
  不公开凭证、地址或宿主提示；Judge 的容量和推理参数不混入主执行模型声明。
- Codex 可使用独立集成脚本生成本机目录，见下节；Router 核心不提供 Codex 的 Agent 指令。
- 未接通 hosted web search、custom tool、媒体、完整 Codex App/远程代理流程。
  不会悄悄删除这些工具让调用通过；不支持的请求在派发前明确失败。

最新增量验收见 [客户端能力协商报告](../reports/client-capability-negotiation-20260927/README.md)。

本轮客户端往返使用 Static。其他策略的核心与流式边界有确定性覆盖，
尚未分别执行每个客户端、每个策略的真模型验收。
标准工具文本没有可信退出状态时，Stage 仍使用高效默认；这不代表已取得完整轨迹信号。


## Codex 本机目录适配

`validation/codex/model_catalog.py` 读取使用者明确指定的本机 Codex 目录和宿主基线模型，
保留原目录、`base_instructions`、`model_messages` 与工具执行方式，追加虚拟路由模型。
仅按 Router 实际能力收紧媒体、工具格式、推理和容量声明；上下文压缩继续由 Codex 执行。
此文件包含宿主提示，只保存本机，不上传到 Router，也不替换日常配置。

先将经认证读取的 `/v1/models` 保存为本机 JSON，再运行：

```sh
uv run python validation/codex/model_catalog.py \
  --baseline /绝对路径/models_cache.json --baseline-model 已安装的宿主基线模型 \
  --gateway-models /绝对路径/router-models.json --output /绝对路径/router-codex-models.json
```

在该次 Codex 启动中传入 `model_catalog_json`，配合自定义 provider 的 `base_url`、
`wire_api="responses"`、`request_max_retries=0`、`stream_max_retries=0`。
关闭尚未接通的托管 web search；并非所有客户端都只改 URL 即可启用全部功能。

参数协商不能将成本限制改写为承诺的模型能力。调用仍独立检查真实输入、输出、数据域与余额。
工具较多的客户端可通过 `validate_gateway_static_live.py --probe-client` 在不派发模型的条件下
测量真实输入包络；该探测故意返回错误终止客户端，费用为零。

依据：[Codex 官方配置说明](https://learn.chatgpt.com/docs/config-file/config-reference)。


## 三客户端验收范围

当前产品接入验证仅覆盖 **DSH、Codex、Hermes**。
Hermes 的本机原生 Agent 接线及费用证据见
[Hermes 验收报告](../reports/hermes-gateway-acceptance-20260927/README.md)。

Hermes 应显式选择现有 profile，并使用模型目录声明的冻结推理档位；不更改日常默认配置。
验收驱动位于 `validation/hermes/check_gateway.py`，直接调用已安装 Hermes 原生 Agent 循环，
实例级关闭自动重试和模型回退。工具执行、上下文及权限属于 Hermes。
本轮真模型只覆盖 Static；其他策略与逐客户端取消、故障注入按独立检查项推进。
