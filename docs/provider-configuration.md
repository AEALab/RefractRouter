# 自行配置 providers 与 models

适用：RefractRouter 0.3.0、DSH 插件 0.11.0。Ark Agent Plan 是一个可选 provider。
RefractRouter 根据用户声明的可用模型路由；不会自动启用账户下全部模型。
当前 RefractAgent 处理文本任务，图片、视频生成模型暂不在这个执行入口的支持范围内。

## 配置在哪里

DSH 的 `refractagent` 插件配置接受 `providerConfig`，其中包含 `providers` 和 `models`。
可以直接编辑 profile 的覆盖配置，也可以用 CLI 生成配置后嵌入 DSH：

```bash
refractagent config-example --provider-type openai-compatible --output ./providers.json
# 编辑 providers.json，填写实际端点、模型 ID、价格与路由预测
refractagent models --provider-config ./providers.json
refractagent dsh-config --provider-config ./providers.json \
  --output ./refractagent-live.json --mode live \
  --production-budget 2 --evaluation-budget 1
```

`models` 只做本地配置校验和清单展示，不请求模型服务。
生成器将配置内容复制到 `refractagent-live.json` 的 `providerConfig`；它不是文件链接。
后续修改 `providers.json` 时需重新生成一个新覆盖文件，或直接更新插件中的 `providerConfig`，
然后重启 DSH。生成器不会覆盖已有文件。

首次部署将插件的 `allowPaidRuns` 改为 `true` 后即可提交真实任务，无需逐任务确认。
以上 2 / 1 是示例每任务生产／评审上限，单位来自 `billingUnit`。
完整安装与启动命令见 [安装指南](refractagent-local-quickstart.md)。

## 三种 provider 接入方式

| `type` | 用途 | 配置 |
| --- | --- | --- |
| `openai-compatible` | 由 Python 直连支持 Chat Completions 的服务，包括本机服务 | `baseUrl`；需要认证时填写 `credentialEnv` |
| `dsh` | 复用当前 DSH profile 已配置的 provider、模型与凭证 | `dshProvider` 填宿主 provider ID；省略时使用 `id` |
| `ark-agent-plan` | 用户选择的方舟 Agent Plan 订阅 | 固定 `/api/plan/v3`；需要认证时填写 `credentialEnv` |

`id` 是用户自己的 provider 标识。不同 provider 可以提供同名 API 模型；
模型的 `id` 必须在本份配置中唯一，`model` 则是对应服务实际接收的模型 ID。
结果的 `model_routes` 会同时保存 provider 和模型，避免同名模型混淆。

`openai-compatible` 会在 `baseUrl` 后添加 `/chat/completions`。它不等于对全部厂商协议的支持；
其他原生协议应通过已安装的 DSH provider 适配器接入。
`baseUrl` 不接受用户名、密码、查询参数或片段；API Key 放在凭证服务或环境变量中。

## 完整最小示例

下面使用一个候选模型与一个独立评审调用。端点、模型 ID、价格、容量和预测均为占位示例，
请替换成自己服务的信息。同一物理模型可用不同配置 ID 承担候选和评审角色；
独立评审指单独发起的评审调用，不保证评审来自另一家厂商或另一物理模型。

```json
{
  "schemaVersion": "refractagent-providers-v1",
  "billingUnit": "USD",
  "qualityMin": 80,
  "providers": [
    {
      "id": "team",
      "type": "openai-compatible",
      "baseUrl": "https://your-provider.example/v1",
      "credentialEnv": "TEAM_MODEL_KEY",
      "maxTokensParameter": "max_completion_tokens"
    }
  ],
  "models": [
    {
      "id": "answer",
      "provider": "team",
      "model": "YOUR_MODEL_ID",
      "role": "candidate",
      "contextWindow": 32768,
      "maxOutputTokens": 2048,
      "pricing": {"unit": "USD", "inputPer1k": 0.001, "outputPer1k": 0.002},
      "routing": {"quality": 85, "latencyMs": 10000},
      "jsonMode": "json-object-hint"
    },
    {
      "id": "review",
      "provider": "team",
      "model": "YOUR_JUDGE_MODEL_ID",
      "role": "judge",
      "contextWindow": 32768,
      "maxOutputTokens": 2048,
      "pricing": {"unit": "USD", "inputPer1k": 0.001, "outputPer1k": 0.002},
      "jsonMode": "json-object-hint"
    }
  ]
}
```

至少一个 `candidate`，且恰好一个 `judge`。增加模型只需增加模型行并引用 provider。
不同模型可以使用不同 provider；生产和评审也可以使用不同 provider。

| 字段 | 含义 |
| --- | --- |
| `contextWindow` | 输入和输出共享的上下文容量；核心在调用前检查实际输入包络 |
| `maxOutputTokens` | 1000–8192；实际还受应用和 DSH 请求输出上限限制 |
| `routing.quality` | 用户配置的 0–100 质量预测；候选必填 |
| `routing.latencyMs` | 用户配置的正数时延预测；候选必填 |
| `qualityMin` | 选路质量预测底线，默认 0；不等于最终评审通过分数 |
| `pricing` | 每 1000 token 的输入、输出价格；`cachedInputPer1k` 可选，默认输入价格 |
| `jsonMode` | `json-object-hint` 发送 JSON 格式提示；`prompt-only` 仅依靠提示词约束 |
| `requestOptions` | 可选 `temperature`、`top_p`、`thinking`、`reasoning_effort`、`seed`；需目标服务支持 |
| `maxTokensParameter` | HTTP provider 可选 `max_completion_tokens` 或 `max_tokens` |

DSH 模式只传递 `temperature` 和 `reasoning_effort`，其他模型选项在宿主配置中管理。
应用请求的 temperature 会覆盖生产候选的配置值；评审模型保留自身配置。
没有配置实测数据时，三个策略以这些声明值做预测；保存的 profile 标记为 `configured`、
观测样本为 0，不能称为实测效果或 SLA。最终评审是另外一次调用。

所有价格必须使用同一个 `billingUnit`，例如 USD、CNY 或 AFP。核心不自动换算汇率或把
AFP 与现金相加。混用单位会拒绝执行；跨 provider 比较前由用户按明确口径配置共同单位。
订阅的比较价格可设为零，但这时成本策略无法区分这些同价模型。

## 复用 DSH 已配置的模型

先在当前 DSH profile 配好并验证目标 provider，再生成模板：

```bash
refractagent config-example --provider-type dsh --output ./providers-dsh.json
```

将模板中的 provider 改成例如：

```json
{"id": "my-models", "type": "dsh", "dshProvider": "my-existing-provider"}
```

模型的 `provider` 填 `my-models`，`model` 填宿主已注册的具体模型 ID。
目标 provider 的重试策略必须为 `mode: normal`、`maxRetries: 0`，
防止一次核心调用在宿主内变成未记账的多次尝试。该设置依目标 DSH provider 插件配置。
目标不能是 `refractagent` 本身，以免递归调用。

插件通过 DSH 原生 LLM 服务执行 Python 已选定的模型，凭证继续留在 DSH。
核心收到统一的回答和用量；宿主缺失 provider、模型或零重试设置时，会在调用前报错。
含 `dsh` provider 的真实执行必须经过 DSH 插件，不能独立使用 CLI 直连。
可以在同一份配置中混用 DSH provider 和直接 HTTP provider。

## 选择 Ark Agent Plan

希望编辑 Ark 候选清单时生成可编辑模板：

```bash
refractagent config-example --provider-type ark-agent-plan --output ./providers-ark.json
```

也可显式使用随包预设，保留已有三候选加 Kimi-K3 评审的配置：

```bash
refractagent dsh-config --preset ark-agent-plan \
  --credential-env CODEX_ARK_API_KEY --output ./refractagent-ark.json \
  --mode live --production-budget 40 --evaluation-budget 80
```

`--preset` 与 `--provider-config` 互斥。预设只是便利入口，不限制用户可配置的模型名单。
新增 GLM、Kimi、DeepSeek、MiniMax 或豆包文本模型时，填写账户实际可调用的 API 模型 ID、
容量、选项及计费信息；配置校验不代表已验证账户权限或模型可用性。
图片和视频生成模型仍需后续执行器支持，不能仅修改模型 ID 就使用文本入口生成媒体。

## 凭证与排障

HTTP provider 的 `credentialEnv` 是凭证引用，例如 `TEAM_MODEL_KEY`，不加 `env:` 前缀。
DSH 会解析同名凭证；也可在启动 DSH 前设置该环境变量。
仅无认证的本机或网关服务应省略它。核心配置和任务记录不保存密钥值。

| 错误或现象 | 处理 |
| --- | --- |
| 要求配置 `providerConfig` 或 `preset` | 0.11.0 真实模式不再隐式使用 Ark；生成或补充配置后重启 |
| `Missing RefractAgent credential` | 设置错误中指明的引用；不同 provider 可使用不同凭证 |
| `no-feasible-route` | 核对质量底线、上下文容量、价格、任务预算及预测时延 |
| 不认识 provider / model | 核对配置 ID；DSH 类型还需确认宿主中已存在模型 |
| `llm-provider-retry-policy-not-zero` | 在目标宿主 provider 设置中将自动重试设为零 |
| 评审失败或无法解析 JSON | 核对 judge 的权限、输出上限、JSON 支持与选项 |

修改配置不会重新执行已完成的任务；重启 DSH 后发送新任务验证。
