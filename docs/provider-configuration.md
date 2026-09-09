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

## Provider 接入方式

| `type` | 用途 | 配置 |
| --- | --- | --- |
| `openai-compatible` | 由 Python 直连支持 Chat Completions 的服务，包括本机服务 | `baseUrl`；需要认证时填写 `credentialEnv` |
| `openai-responses` | 由 Python 直连 Responses API，支持推理模型 | 默认 `https://api.openai.com/v1`；`credentialEnv` 填凭证引用 |
| `dsh` | 复用当前 DSH profile 已配置的 provider、模型与凭证 | `dshProvider` 填宿主 provider ID；省略时使用 `id` |
| `ark-agent-plan` | 用户选择的方舟 Agent Plan 订阅 | 固定 `/api/plan/v3`；需要认证时填写 `credentialEnv` |

`id` 是用户自己的 provider 标识。不同 provider 可以提供同名 API 模型；
模型的 `id` 必须在本份配置中唯一，`model` 则是对应服务实际接收的模型 ID。
结果的 `model_routes` 同时保存配置 ID、provider、模型和推理档位，避免同名候选混淆。

`openai-compatible` 会在 `baseUrl` 后添加 `/chat/completions`。它不等于对全部厂商协议的支持；
Responses API 使用单独的 `openai-responses` 类型，向 `/responses` 发请求；
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
| `maxOutputTokens` | Chat Completions / DSH 类型为 1000–8192；Responses 为 1000–128000，包含推理和正文；还受应用及 DSH 请求上限限制 |
| `routing.quality` | 用户配置的 0–100 质量预测；候选必填 |
| `routing.latencyMs` | 用户配置的正数时延预测；候选必填 |
| `qualityMin` | 选路质量预测底线，默认 0；不等于最终评审通过分数 |
| `pricing` | 每 1000 token 的输入、输出价格；`cachedInputPer1k` 可选，默认输入价格 |
| `jsonMode` | `json-object-hint` 发送 JSON 格式提示；`prompt-only` 仅依靠提示词约束 |
| `requestOptions` | Chat Completions 可用 `temperature`、`top_p`、`thinking`、`reasoning_effort`、`seed`；Responses 见下节；均需模型支持 |
| `maxTokensParameter` | HTTP provider 可选 `max_completion_tokens` 或 `max_tokens` |

DSH 模式只传递 `temperature` 和 `reasoning_effort`，其他模型选项在宿主配置中管理。
Chat Completions 与 DSH 候选使用应用请求的 temperature；评审保留自身配置。
Responses 只发送模型 `requestOptions` 中显式声明的采样参数，不自动注入 temperature。
没有配置实测数据时，三个策略以这些声明值做预测；保存的 profile 标记为 `configured`、
观测样本为 0，不能称为实测效果或 SLA。最终评审是另外一次调用。

所有价格必须使用同一个 `billingUnit`，例如 USD、CNY 或 AFP。核心不自动换算汇率或把
AFP 与现金相加。混用单位会拒绝执行；跨 provider 比较前由用户按明确口径配置共同单位。
订阅的比较价格可设为零，但这时成本策略无法区分这些同价模型。

## OpenAI Responses 与推理模型

OpenAI 推理模型的接入采用 **Responses API**。官方参数和返回结构见
[Responses 迁移说明](https://developers.openai.com/api/docs/guides/migrate-to-responses)。
生成模板后填写自己账户可用的模型 ID、实际价格和上下文容量：

```bash
refractagent config-example --provider-type openai-responses --output ./providers-openai.json
refractagent models --provider-config ./providers-openai.json
refractagent dsh-config --provider-config ./providers-openai.json \
  --output ./refractagent-openai.json --mode live --max-output-tokens 32768 \
  --production-budget 2 --evaluation-budget 1
```

模板中的模型、价格和容量需要用户核对；2 / 1 仍是示例任务上限。
DSH 解析 `OPENAI_API_KEY`，首次启用时将覆盖配置中的 `allowPaidRuns` 改为 `true`。
一个 provider 的配置示例如下，可与其他协议的候选或评审组合：

```json
{
  "id": "openai",
  "type": "openai-responses",
  "baseUrl": "https://api.openai.com/v1",
  "credentialEnv": "OPENAI_API_KEY"
}
```

对应模型的 `provider` 填 `openai`，可使用以下 `requestOptions`：

```json
{
  "reasoning": {"effort": "medium"},
  "text": {"verbosity": "low"}
}
```

支持 `reasoning.effort`、可选 `reasoning.summary`，以及 `text.verbosity`。
具体模型支持的 effort 和参数组合，以该模型的官方说明为准；核心不根据模型名字猜测能力。
Responses 不使用 Chat Completions 的 `reasoning_effort` 或 `maxTokensParameter`。
采样参数 `temperature` / `top_p` 仅在模型配置中显式填写时发送，需确认该模型支持。

JSON 模式转换为 `text.format`。每个节点发送独立的同步请求，使用 `store: false`；
当前不串接 `previous_response_id`、不携带加密推理状态，也不启用服务端工具或 background 轮询。
多轮对话仍由应用传入可见上下文，DSH 中的最终回答展示方式保持一致。

`max_output_tokens` 包括正文和 reasoning tokens；达到上限可能只产生推理、没有正文。
该情况按未完成输出处理并结算已知用量。输入缓存和推理明细会保存，推理不重复加到
`output_tokens` 上计费。依据见 [官方推理用量说明](https://developers.openai.com/api/docs/guides/reasoning)。

配置中的模型 `maxOutputTokens`、插件 `maxOutputTokens` 和 DSH 请求上限共同约束调用。
上面的 32768 是可调整示例，不是默认值或成功保证；未显式提高应用上限时默认仍是 2048。
独立 CLI 可添加 `--max-output-tokens 32768`。过小上下文、未确认用量、拒绝或未完成响应
均不会被当作成功结果，也不会自动改用 Chat Completions 重试。

## 按 DAG 节点联合选择模型与 reasoning effort

一个候选 `id` 代表一组可执行配置：provider、物理模型、推理档位及其他请求设置。
同一物理模型使用多个档位时，增加多行候选并使用不同 `id`，例如 `answer-low` 和
`answer-high`。核心对每个 DAG 节点同时比较这些候选和其他 provider 的模型。

`reasoningEffort` 是可选的模型字段。Python 将其映射为 Responses 的 `reasoning.effort`，
或 Chat Completions / DSH 的 `reasoning_effort`。只填写对应模型实际支持的值；核心不会
探测服务端能力，也不会根据档位名称推断质量。已有 `requestOptions` 写法仍有效，
两处同时配置时必须一致。省略表示交给 provider 默认行为，和显式 `"none"` 不同。

每个候选的 `routing` 有一组默认预测，还可用 `profiles` 为不同节点声明完整预测：

| 字段 | 含义 |
| --- | --- |
| `quality`、`latencyMs` | 必填，分别是质量预测和时延预测 |
| `outputTokens` | 可选，预测输出总 token，包含推理与正文；省略时按有效 `maxOutputTokens` 预测 |
| `profiles[].nodeType` | 节点类型，使用 DAG 支持的类型，例如 `synthesis`、`generation` |
| `profiles[].difficulty`、`risk` | 均必填，取 `low`、`medium` 或 `high`；匹配节点契约 |
| `profiles[].inputMinTokens`、`inputMaxTokens` | 可选，匹配契约的 `input_budget_tokens`；区间左闭右开，默认 `[256, 131073)` |

每个 profile 必须完整填写自己的 `quality`、`latencyMs`；不继承默认 `outputTokens`，
省略仍按有效输出上限。匹配到 profile 就使用该组预测，否则使用默认预测。同一候选的
profile 不允许重叠，以免由配置顺序决定选路。无节点能力契约的旧版 DAG 不能使用这些分层预测。

例如，将以下两行加入 Responses provider 的 `models`，并保留一个独立 `judge`。
`team` 必须对应已配置的 provider，`YOUR_MODEL_ID` 需替换为账户支持这两个档位的模型。
价格与预测都是演示值，不能当成厂商报价或实测性能：

```json
[
  {
    "id": "answer-low",
    "provider": "team",
    "model": "YOUR_MODEL_ID",
    "role": "candidate",
    "reasoningEffort": "low",
    "contextWindow": 262144,
    "maxOutputTokens": 32768,
    "pricing": {"unit": "USD", "inputPer1k": 0.001, "outputPer1k": 0.002},
    "routing": {
      "quality": 60, "latencyMs": 1000, "outputTokens": 1000,
      "profiles": [
        {
          "nodeType": "synthesis", "difficulty": "medium", "risk": "medium",
          "quality": 92, "latencyMs": 1000, "outputTokens": 1000
        }
      ]
    }
  },
  {
    "id": "answer-high",
    "provider": "team",
    "model": "YOUR_MODEL_ID",
    "role": "candidate",
    "reasoningEffort": "high",
    "contextWindow": 262144,
    "maxOutputTokens": 32768,
    "pricing": {"unit": "USD", "inputPer1k": 0.001, "outputPer1k": 0.002},
    "routing": {
      "quality": 96, "latencyMs": 8000, "outputTokens": 10000,
      "profiles": [
        {
          "nodeType": "synthesis", "difficulty": "medium", "risk": "medium",
          "quality": 90, "latencyMs": 8000, "outputTokens": 10000
        }
      ]
    }
  }
]
```

以预设 `compare` DAG 和以上声明值运行质量优先策略，成本／风险分析节点会选 `low`，
最终汇总节点会选 `high`。这是同一 DAG 内的联合选择；质量、成本和时延预测改变时，
选择也可能改变。高档位不保证更高质量，未配置多个候选时也不会自动生成档位。
DSH 覆盖配置中设置 `template: "compare"`，同时将插件 `maxOutputTokens` 设为 `32768`；
独立 CLI 可先零调用检查：

```bash
refractagent run --task '比较方案 A/B 的成本与风险' \
  --provider-config ./providers-openai.json --template compare --strategy quality \
  --max-output-tokens 32768 --mode preflight
```

成本预测 = 节点输入包络 × 输入单价 + 预测输出总 token × 输出单价。
**预测用于路由，硬预算仍按完整输出上限逐次预留，收到响应后按实际用量结算。**
所以预测可行的路线仍可能在派发时因完整预留不足而停止；降低 `outputTokens` 不会放宽预算。
若预测输出超过应用／DSH 实际输出上限，核心在创建任务记录前报错，不会截短预测后继续使用原质量值。

配置预测仍是 `configured`、样本数为 0，不能冒充校准结果。每次生成的 profile 会绑定
有效 provider、API 模型、effort、其他请求选项、输出容量及价格；重放时设置不一致会拒绝。
修改配置时应重新核对预测，核心不会自动重测质量。

`refractagent models`、任务 `model_routes`、独立评审 `evaluation_model`、调用记录和 DSH
回放信息包含配置 `id` 与 `reasoning_effort`。这里记录的是实际发送的请求档位；服务端是否
按预期实现仍需服务端支持。节点未执行时，路由结果只代表选定配置，不能当作已发生的调用。

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
