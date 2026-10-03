# OpenRouter Jev 1.13 接入验收

日期：2026-10-03。范围为 Jev 接入渠道、费用合同、DSH 设置与独立 Python 客户端。
先执行一次公开合成文本请求，之后按用户确认补充两条 DSH 真实工具接线任务。
不评价自然任务的审核准确率或策略收益。

## 真实调用

- 接口：`POST https://openrouter.ai/api/alpha/decisions`。
- 请求模型：`typesafe/jev-1.13`；实际模型：`typesafe/jev-1.13-20260917`。
- 上游：`TypeSafe`；请求关闭提供方回退；客户端没有自动重试。
- 一次请求包含 Choice、Noul、Score，三种类型均正常返回。
- 输入 461 tokens、输出 76 tokens；回执费用为 0.000019362 USD。
- 使用项目冻结汇率 6.7459 折算为 0.0001306141158 CNY。
- 端到端约 660 ms；单次测量不能作为平均值或延迟分位数。
- 原始请求、预检、派发标识、完整回执与汇总分别保存在本目录 JSON 中；不含密钥。

预检冻结最多一次请求、32k 输入 tokens 计费上界，CNY 上界小于 0.01。
实际调用未使用 Ark 执行器，不计 AFP，也不冒充完整 DSH 任务成功。

## 实现与本机部署

核心 0.15.7、插件 0.29.3 新增 `jev.route`；旧配置省略此字段时保持 `typesafe` 行为，
插件新建规划配置默认明确写入 `openrouter`，信任授权仍需独立设置。
`openrouter` 使用独立端点、凭证引用、模型回执校验和费用结算。两种渠道复用现有 Judge
题目与策略。OpenRouter 使用 `usage.cost` 结算，不能用 token 推算覆盖实付费用；缺少费用、
版本或提供方信息时保留预留并停止。回执费用超过预留时保存实付费用并停止任务。

DSH 设置卡片新增“Jev 接入方式”；切换渠道会清除原信任选择，避免把对一个接入方的许可
自动延伸到另一个接入方。`OPENROUTER_API_KEY` 已登记本机受保护环境文件和 DSH 凭证服务；
本仓库和本报告只记录引用，不保存凭证或用户环境配置。

用户在长期可信云授权问题后明确要求以后默认使用 OpenRouter 的 Jev。
原 profile 已据此切换至 OpenRouter，并登记独立信任策略，允许判别请求包含本机路径及
任务上下文。原设置已备份；其他模型、策略、预算及凭证保持不变。

## 验证范围

无网络测试验证旧配置兼容、渠道隔离、费用为零、实付费用、缺失费用、未知版本、超容量、
超额停止、DSH 凭证边界、真实回执来源和旧核心能力阻断。

- 完整 `uv run --offline pytest`：1491 项通过，含 DSH TypeScript 插件契约。
- 最后补充费用超额持久化校验后，OpenRouter 定向测试 12 项通过。
- TypeScript 类型检查、插件构建与 `npm pack` 通过；包版本 0.29.3。
- 本机核心已安装 0.15.7，保留 Laya-MLX 0.2.0；原 web profile 加载 0.29.3。
- 实际浏览器已核对“Jev 接入方式”的 Typesafe／OpenRouter 选项。
- 原 profile 已按后续授权将 Jev 默认渠道切换至 OpenRouter；本次切换没有新增付费调用。
- 切换后实际浏览器显示 OpenRouter、`OPENROUTER_API_KEY` 及可信云；零调用检查六种
  策略均可用。新配置默认值调整后 TypeScript 类型检查及构建再次通过。

## DSH 两条任务收尾验收

用户确认收尾顺序后，在原端口 3080、原 web profile 分别新建 Advisor 与 Escalation
会话。未修改单任务预算、模型、判别门槛或 provider；每条任务仅要求宿主执行一次
`printf` 并回报标记。冻结范围见 [预检](dsh-preflight.json)，实际摘要见
[结果与账本](dsh-results.json)。完整请求保留在本地，不将宿主上下文公开提交。

| 策略 | 实际行为 | AFP | Jev CNY |
|---|---|---:|---:|
| Advisor | 两次执行、一次审核；工具续接后 APPROVE，概率 0.99、confidence 0.98 | 6.49575 | 0.002089542525 |
| Escalation | 起始候选丢弃、接管及工具续接；一次判别 | 7.1342 | 0.00195496182 |

Escalation 的原始首选为 PROCEED，概率 0.70、confidence 0.58；由于用户当前仍采用
0.8 单门槛，Router 将其解释为 UNCERTAIN 并接管。没有为了验收调整门槛。
这证明不确定分支的行为正确，不证明这个正常工具请求有必要升级。
两个会话均只执行一次宿主工具；接管后不追加审核，轨迹已注明。

两条任务合计五次 Ark 执行、两次 OpenRouter 判别，13.62995 AFP、0.004044504345 CNY，
全部调用已结算，没有未知用量。实际执行推理等级为 Flash low、4.1 Flash high；后者由
DSH 已有模型默认参数补齐。Jev 实际版本为 `typesafe/jev-1.13-20260917`，单次耗时分别
809 ms、725 ms。预算预检记录的批次监督上限不是对用户运行配置新增硬额度。

提交前完整 `uv run --offline pytest`：**1492 passed**（207.47 秒），含插件契约测试。
实际浏览器核对工具次数、最终标记、原始判断与 Router 动作、接入渠道、单次及累计费用，
原有任务 DAG 页签与两个独立设置卡片均保留。

本次不增加自然任务质量题集，不宣称 OpenRouter 路线优于直连，不扩大标准 Gateway
的 Judge 执行能力，也不改变其他策略的判别阈值。

来源：
[OpenRouter Jev 官方说明](https://openrouter.ai/docs/guides/community/jev)、
[Decisions 合同](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-questions-and-answers-request)、
[模型价格](https://openrouter.ai/typesafe/jev-1.13)。资料核对日期：2026-10-03。
