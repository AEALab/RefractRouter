# 统一金额计价迁移

## 目标与边界

新运行移除 AFP 预算与系数，保留 Ark 订阅模型及 `/api/plan/v3` 执行接口。
所有路线按明确对应的公开价格形成参考成本，统一展示 CNY，保留 USD 原价、汇率和来源。
订阅参考成本与按量 API 费用分别记录；参考估值不宣称实际扣款。质量满足要求时仍可
优先使用订阅路线，以减少额外现金支出，再比较参考成本与等待时间。

用户已明确保留订阅执行，无需为取消 AFP 而迁移渠道。订阅路线独立生成参考估值，
不得将其用于真实现金预算或宣称实际扣款。已有 AFP 原始记录保持只读兼容。
累计 AFP 授权和任务 AFP 预算均不转换成 CNY。

Python 负责价格选择、预算、结算及路由。DSH 插件负责目录、凭证、配置和展示，
不复制计价逻辑。标准模型接口继续独立于宿主，验收范围为 DSH 与 Codex。

## 当前核对结果（2026-10-06）

当前自动路由启用五条路线：DeepSeek 官方 Flash、Pro，Kimi 官方 K3，
Ark GLM-5.3、DeepSeek-V4-Flash。规划路由另有多条 Ark 配置，不能只迁移自动路由。

| 原路线／用途 | 候选金额路线 | 必须核对的事项 |
| --- | --- | --- |
| DeepSeek 官方 Flash、Pro | 保留官方接口与 CNY 价格 | 峰谷时段、节假日、缓存及派发时价格 |
| Kimi 官方 K3 | 保留官方接口与 CNY 价格 | 缓存读写互斥、TTL、用量字段 |
| OpenRouter Jev 1.13 | 保留 OpenRouter 路线 | USD 原始费用、汇率和判别账本汇总 |
| Ark GLM-5.3、GLM-5.3-Flash | OpenRouter 同名目录候选 | 实际 provider、模型版本、工具及 replay；尚未绑定 |
| Ark DeepSeek-V4.1-Flash | 官方 Flash／OpenRouter V4.1-Flash 候选 | 别名、实际版本和接口能力；尚未绑定 |
| Ark DeepSeek-V4-Flash、V4-Pro | 官方或 OpenRouter 版本化候选 | 不自动把旧版本换成新版本；OpenRouter 存在多个日期版本 |
| Ark Kimi-K3、Kimi-K2.7-Code | Kimi 官方／OpenRouter 候选 | 版本、上下文和可用凭证 |
| Ark MiniMax-M3 | OpenRouter 同名目录候选 | 实际 provider、价格与能力 |
| Ark Doubao 系列 | 待核对官方按量接口 | 本次 OpenRouter 目录筛选未发现对应 ID；不猜测映射 |

这张表是参考价格来源候选清单；Ark 执行渠道保留，不表示要改用表中的价格来源渠道。
同名不足以证明版本、缓存口径或模型能力相同，仍须记录映射依据。迁移保留原 provider、凭证与会话，金额额度采用已有明确的 CNY 设置。没有公开价格的路线显示具体缺项，不默认为免费。

公开目录来源为 `https://openrouter.ai/api/v1/models?output_modalities=all`；
查证日期 2026-10-06，相关型号与原始价格字段保存于
`data/model-catalogs/openrouter-currency-preview-2026-10-06.json`。
目录的价格来自该模型的 top provider；实际派发前须绑定允许的 provider／endpoint，
或采用覆盖所有允许路线的价格上界，并核对提供方切换规则。

已另行读取六个模型的原厂 endpoint，保存为
`data/model-catalogs/openrouter-manufacturer-endpoints-2026-10-06.json`。
包含 `typesafe`、`z-ai/fp8`、`minimax/fp8`、`deepseek`、`moonshotai/mxfp4`。
其中 MiniMax-M3 的该 endpoint 声明上下文为 524288 tokens，与现有 Ark 的
1048576 配置不同；迁移不能复制原容量或据同名推断完整等价。

## 计价合同

`refractrouter-currency-price-v1` 保存 provider、模型、endpoint、价格来源、查证日期、
原币种和按单个单位的价格。金额采用 Decimal，JSON 输出使用十进制字符串。
展示舍入不参与预算计算。当前基础模块接受已经按条件选定的价格；它不负责自行联网
刷新价格，也不推断型号等价。

输入按未缓存、缓存读取、缓存写入三种互斥用量计算。输出 token 已包含提供方计入的
推理 token 时不得再次相加。请求、图片、影片秒等按各自单位计量。
出现未适配的额外收费、动态负数价格、条件价格或缺失字段时，预览明确阻断，
不能静默忽略后用于预算。

目录转换得到 `reference-price`；绑定真实路线并验证适用条件后才可生成
`route-public-price`。基础计算输出 `calculated-not-provider-confirmed`，不冒充
提供方已经扣费。后续回执结算需按调用 ID、实际模型和 provider 核对。

USD 折算必须携带正数汇率、来源和日期。任务开始冻结价格计划与汇率，派发时按
冻结计划选择适用时段；实际扣费与计划有差异时保留差额，不能改写原始回执。

## 分批交付与验收

### 第一批：目录、合同与零调用预检

- [x] 核对当前启用路线及规划路由角色来源。
- [x] 保存 OpenRouter 公开目录相关型号快照。
- [x] 建立金额计算基础合同及单位、缓存、来源负例测试。
- [x] 提供零调用公开价格预览，输出阻断原因且不覆盖既有结果。
- [x] 适配 OpenRouter 实际 endpoint 的明确价格、UTC 时段和长上下文阶梯及预算上界。
- [x] 修正 DeepSeek 2026 年法定节日本日的时段估算；未知年度、未确认的调休折扣标明上界。
- [x] 完成当前已启用及规划已配置路线的实际 provider、条件价格和能力绑定。原本未启用且无参考价的四条 Doubao 路线继续阻断，详见验收报告。
- [x] 完成官方与 OpenRouter 价格适配器、核价目录刷新草稿、有效期维护诊断及快照差异检查；不承诺实时自动抓取官网。

### 第二批：运行账本与路由

- [x] 新版本分开配置参考成本上限与按量费用上限；旧 AFP 配置经明确迁移操作生成草稿。
- [x] 规划六策略及自动路由共同使用金额价格与预算接口。
- [x] Jev、planner、节点、审核、返工、接管及失败尝试沿用统一预留／结算入口并保留去重。
- [x] 移除 `maxAfpCoefficient` 约束；订阅优先改为独立渠道偏好，不依赖 AFP。
- [x] 保留 Static 固定／随机语义和其他策略的审核、保持、接管规则。
- [x] 区分预计、未派发保护、已派发待核对及已结算金额。
- [x] 验证并发原子预留、取消释放、未知用量停止及恢复不重发。

### 第三批：宿主、安装与发布

- [x] DSH 设置仅展示新金额预算，轨迹展示费用依据与来源。
- [x] 保留历史 AFP 读取；历史重算另存，不能覆盖原始费用或判断。
- [x] 完整 Python 测试、TypeScript 类型检查、契约测试和构建。最终 1698 passed、5 subtests passed。
- [x] 在原 profile 完成 DSH 及 Codex 有限真实接线与费用核对。
- [x] 核对源码、分发包、已安装包和实际界面，完成验收报告。
- [x] 提交 [PR #185](https://github.com/AEALab/RefractRouter/pull/185)。

只执行固定功能与对账验收；本迁移不自动启动大规模收益实验。真实调用前核对
已有现金授权剩余、未知用量预留及具体路线；AFP 授权不扩大现金授权。

## 可复现零调用命令

```sh
uv run python experiments/preview_currency_prices.py \
  --catalog data/model-catalogs/openrouter-currency-preview-2026-10-06.json \
  --output /tmp/currency-price-preview-new.json
```

已有结果为 `reports/currency-price-preview-20261006.json`。全部行的
`dispatchReady` 仍为 false：目录预览不能替代实际路线准入。

包含实际 endpoint 的预览为 `reports/currency-endpoint-preview-20261006.json`，
可通过同一命令增加以下参数重现：

```sh
--endpoints data/model-catalogs/openrouter-manufacturer-endpoints-2026-10-06.json \
--at 2026-10-06T04:00:00+00:00
```

六条 endpoint 的价格均可读取；作为订阅估值前还需验证版本对应，预览不授权派发。
促销折扣未确认时拒绝物化，不在公开值上再次擅自乘折扣系数。

## 官方依据

- [OpenRouter 模型与价格字段](https://openrouter.ai/docs/guides/overview/models)
- [OpenRouter 用量及费用回执](https://openrouter.ai/docs/cookbook/administration/usage-accounting)
- [OpenRouter provider 路由](https://openrouter.ai/docs/guides/routing/provider-selection)
- [DeepSeek 官方人民币价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)
- [Kimi 官方计费说明](https://platform.kimi.com/docs/pricing/chat)
- [2026 年放假安排](https://www.beijing.gov.cn/zhengce/zhengcefagui/202511/t20251104_4258873.html)
- [法定节日本日与调休的区别](https://www.gov.cn/zhengce/content/202411/content_6986380.htm)

## 保留订阅路线的修正与实现状态

用户进一步确认保留 Ark 订阅模型，仅删除 AFP 计价。此前草稿中强制更换执行渠道、
将全部预算定义为现金及删除订阅优先的内容不再作为实施目标。

- 订阅执行身份与参考价格身份分开保存；不复制参考渠道的上下文或工具能力。
- 同一调用保存参考成本；只有按量调用另有 API 费用。汇总不得把这两列相加。
- 订阅月费未分摊时标为未按调用归集，不把参考金额说成扣款，也不说模型免费。
- 参考成本额度控制估值消耗；现金额度仅控制按量调用。两项均不能由旧 AFP 数值转换。
- 已增加 `subscription_valuation` 合同及保留 Ark 端点的确定性验证。
- v7 规划配置、v5 自动目录及 v6 自动运行配置已接入双金额语义。订阅图片采用非 token
  参考账本，保留调用身份与公开价格映射；用户原有 profile 已完成迁移安装，保留 provider、凭证与会话。
- 自动节点分配和真实 direct／DAG 候选比较，在质量合格后优先较少现金支出，
  再比较参考成本。参考成本更高但现金更少的结果，不能报告为参考成本节省。
  旧配置维持原排序，历史研究基线不追改。
- 已完成 DSH 与 Codex 标准接口真实 Static 工具续接：含失败尝试共 5 次订阅调用，
  参考成本 0.44438752 CNY，新增按量现金支出 0；见
  `reports/currency-migration-live-20261006/README.md`。

## 收尾核对（2026-10-06）

- 完整回归已取得 `1692 passed, 5 subtests passed`，耗时 329.33 秒。
  此后新增的迁移与价格刷新补丁须计入最终 PR 前回归，不能沿用该结果作为最终版本证明。
- 显式自动目录升级移除旧 `objective.maxAfpCoefficient`，返回移除项证据；
  品质门槛、原配置和历史记录保持原样。直接提交含旧系数的 v5 配置仍拒绝。
- 价格预览支持 `--previous`、`--as-of`、`--max-age-days`：比较各计价维度，
  区分渠道／币种变化与单纯价格变化，默认查证超过 30 天提示刷新。
  该有效期是维护诊断，不代表官方价格保证，也不在任务中联网或改写冻结价格。
- 不在运行期间自动抓取并应用官方网页价格；设置页已增加价格与容量刷新入口，读取当前核价目录。当前目录更新通过
  系统维护的核价目录和显式配置草稿进行。不得将预览差异检查描述成自动更新已交付。

- 补齐金额版新增 Ark 模型、媒体预设以及 Task／Composite 的订阅现金优先；
  41 项针对性 Python 测试与 3 项真实 Python 工作进程插件契约测试通过。
  新增 Task／Composite 测试实际结算一次判别和一次执行，检查参考账本增长、现金账本为零。
- 最终候选版本为核心 0.16.2、插件 0.30.2；安装包核对与最终完整回归均完成，详见 `reports/currency-migration-acceptance-20261006.md`。
