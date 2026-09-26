# 独立模型路由与宿主边界

决策日期：2026-09-27。适用版本：Router 0.14.0、DSH 插件 0.27.0。

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
| Chat Completions SSE 与 usage | 已实现，只交付已结算且接受的回复 |
| Responses 完整文本/function 历史、`store=false` | 已实现，协议往返及 HTTP SSE 验收 |
| 上游 Chat Completions | 已实现，零自动重试，独立凭证引用 |
| 上游 Responses、Anthropic Messages | 独立网关未接通；原有其他入口的适配不代表这里已通过 |
| 媒体、托管工具、custom tool、加密 reasoning replay | 当前网关拒绝，不静默丢弃 |
| `previous_response_id`、Responses 存储式增量会话 | 当前网关拒绝；由客户端保存并回传完整历史 |
| Codex、Hermes、OpenClaw、Claude 各客户端真实接入 | 尚未分别验收，不能宣称任意客户端仅改 URL 已全部兼容 |

当前网关从上游取得完整回复、结算后才发送 SSE；这证明 SSE 协议兼容，
不代表已经实现上游逐 token 透传或降低首字等待。
DSH 插件现有 Static/Stage/Task 直接流式路径保持原有行为。
后续补充标准接口增量流式时，Escalation 待审回复必须继续缓冲。

未知参数在派发前拒绝，不能为了让某个客户端“连上”就删除它的工具约束或推理数据。
协议转换保留工具名称、调用 ID、参数、结果配对及角色；不执行工具。

## 状态与任务边界

标准 API 不保证提供真实 session、任务轮次或“追加指导”标识。
仅凭相同的首条消息不能把请求合并成同一个任务。

本版默认行为：

- 新请求分配独立身份，相同提示也不共用预算或升级状态。
- 客户端返回本服务刚交付的 function call ID 时，核对已接受历史前缀后续接同一任务。
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
