# 官方 Jev 在规划路由中的接入

规划路由可在 DSH 插件设置中，为 Advisor Gate、Escalation、Task、Stage 协作模式及
Composite 的 Task／Stage 环节分别选择「官方 Jev」。选择只影响 Judge；执行模型仍由各策略
原有配置决定。Static 和纯规则 Stage 不产生 Judge 调用。

## 设置与边界

在「RefractAgent 规划路由」设置卡片中，先配置 CNY 生产预算、DSH 凭证引用及 Jev 数据域，
再进入相应策略选择 Judge。新建规划配置默认使用 OpenRouter，接入方式仍可选择 Typesafe 直连。
旧配置省略 `jev.route` 时继续使用直连，避免静默变更既有数据传输路线。
对应凭证引用默认是 `TYPESAFE_API_KEY` 或 `OPENROUTER_API_KEY`；API 密钥须登记在 DSH 凭证
服务，不能填写到插件配置。Jev 是云端、文本型服务；默认外部云会拦截包含本机绝对路径等
敏感资料的判别输入。选择可信云须使用已登记的信任策略，不能继承对其他提供方的授权。

直连固定调用 `jev-1.13.0`；OpenRouter 使用 `POST /api/alpha/decisions`、
`typesafe/jev-1.13`，校验实际版本 `typesafe/jev-1.13-20260917`，只允许 TypeSafe 提供方，
关闭提供方回退与客户端自动重试。设置切换渠道时清除旧的数据域许可，需重新选择可信云策略；
OpenRouter 和 TypeSafe 都会接收判别内容。两种渠道共用已有题目及策略，不增加前置 LLM。

Advisor 和 Escalation 默认只比较获选项概率与各自设置的门槛，Choice `confidence`
只记录、不参与准入。在「官方 Jev Judge」中可显式切换为实验分动作规则：
`confidence >= 0.55`，最终批准／放行的概率至少 0.80，返工、缺陷或停滞接管、
正常工具续接的概率至少 0.70。实验规则启用时，各策略的单一概率门槛不参与 Jev 判定。
切换从下个任务生效；轨迹按冻结任务显示实际规则、原始分类、两项数值、门槛和最终动作。
该规则只适用于 Advisor、Escalation 的 Jev Choice。此前 24 条 TypeSafe 直连留出题中，
旧规则与分动作规则均为 22 条符合内部标签，尚不足以将实验规则设为默认。
Task 对候选能力卡进行一次 Choice 选模；证据不足或低于门槛时使用指定备援。Stage
只在规则要求的执行边界调用 Judge；Composite 可独立配置 Task 与 Stage 的后端。

Jev 的官方价格为每百万输入 token 0.042 USD、输出 token 免费。核心按照冻结汇率将实际输入
用量折算成 CNY 结算；OpenRouter 则采用回执 `usage.cost` 的 USD 金额折算，允许有效零费用，
不以直连的估算价格覆盖实付金额。保留渠道、提供方、具体版本、请求 ID、USD 费用、来源及汇率日期。
派发前使用渠道的输入上界预留额度（直连 64k、OpenRouter 32k tokens）；
未知用量保留预留并停止后续受管调用。Jev 的调用不计入 AFP。凭证仅在 DSH 宿主内解析，
Python 核心只接收判别请求和无密钥的回执。

两种渠道的完整请求另有 96 KiB 传输技术上限；它不是 token 容量证明，不会截断输入。
提供方拒绝超容量请求时停止，不转另一渠道重试。OpenRouter 缺少费用、用量、实际版本、
提供方或请求 ID 时保留预留并停止。独立 Python `JevClient`／`JevDecisionAdapter` 也接受
`route="openrouter"`；后者默认读取 `OPENROUTER_API_KEY`。本次不扩展标准 Gateway 的
Judge 执行循环，DSH 安装接线与独立客户端接通分别验收。

## 已验证与待验证

无网络测试覆盖审批、升级、Task 一次选模、Stage 换模、Composite 串接、数据域、媒体拒绝、
账本及 DSH 凭证边界。插件使用宿主 HTTP 通道执行 Jev 请求，零自动重试。图片／影片审核
不在此次文本接线范围内；遇到媒体块不会把附件内容伪装成文本送给 Jev。

2026-10-02 在原有 DSH web profile 中核对了规划路由与自动路由设置卡片、五个 Judge
环节的 Jev 选项及零调用诊断。首次预检发现：插件已经更新，但同版本号的 Python 工具
仍是旧安装副本，导致 Advisor 保存后报 `advisor.judge.type` 不支持 Jev。使用
`uv tool install --force --reinstall '.[local-judge]'` 重建安装后，五个环节的 Jev
配置均通过零调用检查；原有策略选择已恢复。发布包因此升至核心 0.15.5、插件 0.29.1，
预检也会在旧核心缺少 Jev 能力时直接提示升级。

2026-10-03 在同一 profile 的临时服务中完成五种策略的有限真实接线，官方 Jev 共调用
10 次，已确认 0.017126882 CNY；Ark 执行调用另计 62.73045 AFP，包含三次派发 Jev
前失败的尝试。验收修正输入容量字节误判、非 token 账本汇总及路由轨迹空值显示，
核心升至 0.15.6、插件升至 0.29.2。原 profile 设置已恢复，实际服务升级仍需独立安装验收。
详见[真实接线验收报告](../reports/jev-dsh-live-acceptance-20261002/README.md)。

后续已经用冻结题集分别核对各用途的判别；TypeSafe 直连 Jev 在 Task 开发题 5／6、
Task 留出题 6／8、Stage 7／16、Advisor 20／24、Escalation 22／24 条符合内部标签。
这些数字不能合并为总体准确率，也不能直接转移到 OpenRouter 渠道的自然任务质量。
OpenRouter 已完成两条 DSH 真实工具任务：Advisor 审核批准，Escalation 因默认 0.8
门槛把原始 `PROCEED` 概率 0.70 映射为无法判断并接管。该任务证明接管路径可用，
也提示需要观察不必要接管。详见[固定题对照](../reports/planning-jev-comparison-20260930/README.md)、
[OpenRouter 验收](../reports/jev-openrouter-20261003/README.md)及
[Jev 门槛核对](../reports/jev-gate-review-20261003/README.md)。

参考：[TypeSafe API](https://docs.typesafe.ai/api)、[模型与计价](https://docs.typesafe.ai/models)、
[置信度说明](https://docs.typesafe.ai/confidence)、
[OpenRouter Jev 接口](https://openrouter.ai/docs/guides/community/jev)、
[OpenRouter Decisions 合同](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-questions-and-answers-request)。
