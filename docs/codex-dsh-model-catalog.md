# Codex 与 DSH 模型目录及分类草稿

本页归档 **2026-11-02** 的开发环境整理结果：Codex/OpenCodex 可见 **5 个上游 provider、
37 个模型**；DSH 通过新增的 `opencodex` 宿主入口加载其中 **29 个模型**。
这是已配置账户的目录快照，未新增真实生成调用，也不是面向所有账户的可用性保证。

完整 ID、分类、目录容量和费用快照见
[机器可读清单](../data/model-catalogs/codex-dsh-2026-11-02.json)，
本次发现、同步及复用调用摘要见
[同步验收](../reports/model-catalog/20261102-01/同步验收.json)。
两份文件只用于讨论和追溯，不是可以直接加载的 Router 配置。

## 目录与接入范围

| 上游 provider | 模型数 | 现有计费关系 | 本次 DSH 入口 |
| --- | ---: | --- | --- |
| `openai` | 8 | 现有 ChatGPT/Codex 订阅，不套用 API 美元价格 | 当前 Direct 登录未接入 |
| `ark` | 15 | Agent Plan 订阅，以 AFP 比较；实际扣减未知 | `opencodex`，模型 ID 保留 `ark/` |
| `ds` | 2 | DeepSeek 原厂按量，峰谷与缓存分别计费 | `opencodex`，模型 ID 保留 `ds/` |
| `moonshot` | 6 | Kimi 中国站普通按量 API | `opencodex`，模型 ID 保留 `moonshot/` |
| `minimax-cn` | 6 | 沿用已有中国站账户与密钥，实际计费类型未确认 | `opencodex`，模型 ID 保留 `minimax-cn/` |

DSH 新增的是 **一个宿主 provider 下的 29 个模型条目**，不是增加 29 个 provider。
原有 DeepSeek、Ark、Kimi 直连入口保留，因此选择器内会出现同名但接入路径不同的模型。
不能把重复入口当作新的物理模型，也不能混合不同渠道的用量与计费。

OpenCodex **2.91.0** 官方 DSH 导出在 OpenAI 为 Direct 模式时排除原生 GPT 条目。
本次没有搬运 ChatGPT 登录凭据或更换账户模式，故 GPT 的 8 个模型只属于 Codex 目录，
不能称为 DSH 已可调用。后续如需接入，应另行核对受支持的认证方式。
实现依据为该版本的
[DSH 导出实现](https://github.com/lidge-jun/opencodex/blob/v2.91.0/src/clients/config-export/dsh.ts)。

## 强弱分类待重新定义

以下是研究候选分组，**尚未获用户最终定义，也未写入任何生产路由策略**。
跨厂商的能力高低、同一模型不同思考档位的质量，都需要独立任务验证。
名字包含 `Flash`、`Pro` 或 `highspeed`，价格高低和版本新旧，均不能单独证明能力。

| 建议组 | 模型条目数 | 完整模型 ID |
| --- | ---: | --- |
| 强模型候选 | 10 | `gpt-6-astra`、`gpt-6.1-sol`；`ark/glm-5.3`、`ark/deepseek-v4-pro`、`ark/kimi-k3`、`ark/kimi-k3.1-pro`；`ds/deepseek-v4-pro`；`moonshot/kimi-k3`、`moonshot/kimi-k3.1-pro`、`moonshot/kimi-k3.1-pro-highspeed` |
| 弱模型／低成本候选 | 5 | `gpt-6-luna`；`ark/doubao-seed-2.0-mini`、`ark/deepseek-v4-flash`、`ark/doubao-seed-2.1-lite`、`ark/glm-5.3-flash` |
| 中间组候选 | 7 | `gpt-6.1-terra`；`ark/deepseek-v4.1-flash`、`ark/deepseek-v4.1-flash-economy`、`ark/doubao-seed-2.1-pro`、`ark/minimax-m3`；`ds/deepseek-flash`；`minimax-cn/MiniMax-M3` |
| 待定义／单独验证 | 3 | `ark/doubao-seed-evolving`、`ark/kimi-k2.8-preview`、`minimax-cn/MiniMax-M3.1-Flash` |
| 兼容与历史备选 | 12 | `gpt-6-sol`、`gpt-5.6-sol`、`gpt-5.6-terra`、`gpt-5.6-luna`；`ark/kimi-k2.7-code`；`moonshot/kimi-k2.6`、`moonshot/kimi-k2.7-code`、`moonshot/kimi-k2.7-code-highspeed`；`minimax-cn/MiniMax-M2.5`、`minimax-cn/MiniMax-M2.5-highspeed`、`minimax-cn/MiniMax-M2.7`、`minimax-cn/MiniMax-M2.7-highspeed` |

“历史备选”表示本轮建议优先讨论新候选，并不表示这些模型已下线或能力较弱。
GPT 分组参考[厂商模型定位](https://developers.openai.com/api/docs/models)，并非本项目质量排名。
后续定义应同时记录目标任务、质量要求、实际模型与渠道、思考档位、成本单位、
工具续接和输出合同，避免用一个全局强弱标签代替可检验的选模条件。

### Flash 别名须分开

DeepSeek 原厂的 `deepseek-flash` 在本次核对时指向 **DeepSeek-V4.1-Flash-1017**。
原厂旧名 `deepseek-v4-flash` 和 `deepseek-v4-flash-vision-exp` 仍被接受，但已转由新版服务。
不能把 `ds/deepseek-flash` 与 `ark/deepseek-v4-flash` 视为同一部署。
依据见 [DeepSeek 原厂说明](https://api-docs.deepseek.com/quick_start/pricing/)。

## 能力组与成本组分别维护

清单保留常规费率、活动区间和核对时有效价格；**快照不具备自动更新或计费执行能力**。
进入后续实验前必须重新冻结当前费率与活动有效日期，不得直接拿此表结算新调用。
AFP、CNY 和 USD 不直接相加；订阅参考估值不等于实际现金支出。

下面是 2026-11-02 的 Ark 文本比较值，输入和输出分别按每百万 token 计算。
不含搜索、媒体、存储等其他计费项，也不代表供应商账单扣减。

| 模型 | 常规输入／输出 AFP | 核对时活动输入／输出 AFP |
| --- | ---: | ---: |
| `glm-5.3-flash` | 50 / 50 | 50 / 50 |
| `deepseek-v4-flash` | 50 / 50 | 50 / 50 |
| `deepseek-v4.1-flash` | 250 / 250 | 125 / 125 |
| `deepseek-v4.1-flash-economy` | 200 / 200 | 100 / 100 |
| `glm-5.3` | 450 / 450 | 450 / 450 |
| `deepseek-v4-pro` | 550 / 550 | 550 / 550 |
| `kimi-k3` | 1000 / 1000 | 1000 / 1000 |
| `kimi-k3.1-pro` | 700 / 700 | 350 / 350 |

Kimi K3 的五折区间已于 2026-10-26 00:00（北京时间）结束；K3.1 Pro 的本次活动区间
结束于 2026-11-10 00:00。不能把活动价写成永久价格，也不能因为 K3.1 Pro 暂时更便宜
就把它划入弱模型组。来源为
[Ark AFP 规则](https://console.volcengine.com/ark/region:cn-beijing/docs/agent-plan-personal-afp-credits-billing-rules)。

Kimi 普通 API 的缓存读取、写入与保留时间另行核算；缺失的费率或用量保留未知。
MiniMax 当前账户的计费类型尚未确认，公开按量价格仅供参考；四个旧型号未冻结价格，
清单中保留 `null`，不能当作免费。依据分别见
[Kimi 计费说明](https://platform.kimi.com/docs/pricing/chat)和
[MiniMax 公开价格](https://platform.minimax.cn/docs/pricing/overview)。

## 维护与同步方式

1. 读取既有每周模型与计费维护记录，核对版本、待复查模型、公开费率和历史调用时间。
   列表可见、模型接口发现成功、历史生成成功与当前端到端验收分别记录。
2. 检查本机配置和账号模型接口。凭据仅在原有本机解析路径内使用；不公开密钥、账户、
   会话或完整设置。临时超时、429 和服务器故障保留待复查，不能据此删除模型。
3. 使用 `opencodex sync` 刷新 Codex 目录，不带重启参数，不更换默认模型或审批设置。
4. 使用 `opencodex inspect client-config --client dsh --json` 获取官方模板，核对实际
   DSH 版本和正在使用的 profile。本次 DSH 为 **0.1.5-rc.3**，采用已验证的
   `settings.yaml` 设置层；不可把新版工具的默认目标位置盲目套到已有 web profile。
5. 先备份，只将模板中 `llm-pi-ai.providers.opencodex` 合并到原设置。保留直连 provider、
   默认模型和全部 RefractAgent 设置。新宿主入口配置 `retryPolicy.maxRetries: 0`；
   使用 `compat.supportsMaxOutputTokens: false` 省略 Responses 的 `max_output_tokens`。
6. 在运行界面确认目录加载、模型 ID 和原设置保持，并归档脱敏摘要。目录或能力有变化时，
   后续生成验收另冻范围、预算、用量和失败记录；本次复用既有证据，新增生成调用为零。

上述配置只改变 DSH 宿主的可选目录，不会自动启用 Router 的候选、评审或规划角色。
宿主的零重试也不能证明 OpenCodex 内部没有恢复派发；本轮未修改或重新验收代理内部策略。
因此此入口尚不能凭目录同步结果获得本项目受管实验的全链路零重试资格。

新入口没有人为写入 Responses 输出限制，但这**不等于已逐个核验原生输出上限**。
目录未提供上限的条目保留 `null`，不能拿宿主默认回退值冒充模型原生容量。
当前 Ark 目录的 `256000` 是 OpenCodex 本地上下文配置帽，不能当作所有 Ark 模型的原生窗口。
目录中的模态、思考档位还包含通用推断，本轮未逐项做视觉或工具往返验证。

## 验收范围

本次只读发现中，Kimi 返回 6 个模型，DeepSeek 返回 2 个；MiniMax 返回静态目录状态，
不构成今天逐个模型调用通过的证据。此前同日归档了 Terra、Kimi K3.1 Pro 普通／高速版、
MiniMax M3 的成功生成检查，本次复用并保留原时间，不扩充为 37 个模型的新验收。

DSH 实际选择器中已观察到新增目录的 29 个条目。原默认仍为 RefractAgent 规划路由的
Escalation 模式，预算、策略和旧直连设置保持。本机安装的插件为 **0.33.25**，
与仓库公开预览版本不同；本次只更新设置，没有升级、降级或覆盖安装包。

本页和 JSON 合入仓库只完成文档与证据归档，不会修改其他开发者的账户或日常模型配置，
也不把目录同步、既有生成检查或完整工程测试通过当作真实路由收益证据。
