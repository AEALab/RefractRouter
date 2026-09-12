# Ark 文字模型的 AFP 成本档位

2026-09-12 从官方浏览器正文核对：
[套餐概览](https://www.volcengine.com/docs/82379/2366394?lang=zh)、
[AFP 抵扣规则](https://www.volcengine.com/docs/82379/2516283?lang=zh)。
网页读取服务仅返回目录，最终以浏览器中实际可见的模型表和抵扣系数表核验。
两页标注更新时间分别为 2026.09.12 07:54:42、07:54:43。

| 常规输入／输出系数 | 文字模型 |
|---|---|
| 0.25 / 0.25 | doubao-seed-2.0-mini |
| 0.5 / 0.5 | doubao-seed-2.0-lite、deepseek-v4-flash、glm-5.3-flash |
| 2.5 / 2.5 | doubao-seed-2.1-turbo、doubao-seed-evolving、minimax-m3 |
| 4.5 / 4.5 | glm-5.3、kimi-k2.7-code |
| 5.5 / 5.5 | deepseek-v4-pro |
| 10 / 10 | kimi-k3 |

公式为 `(输入 token × 输入系数 + 输出 token × 输出系数) / 10000`。
核心配置的每千 token 价格为对应系数除以 10，不使用人民币价格冒充 AFP。
Kimi K3 限 Medium / Large / Max，其余表内文字模型列为全部套餐支持；
实际账户权限仍由服务商决定。GLM-5.3 不支持关闭思考。
GLM-5.3-Flash 的上一轮 0.25 活动已于 2026-09-11 结束，当前采用常规 0.5。
Auto 属于服务商动态路由模式，不作为固定型号进入本地候选模型池。

## 应用配置

`src/refractrouter/resources/ark-agent-plan-catalog.json` 保存本次核对快照；
Python `ark_plan.application_configuration()` 和 `afp_metadata()` 负责导出应用模型池与展示数据。
TypeScript 仅展示清单、传递字段，不实现成本过滤或节点选模。

`strategies.<mode>.maxAfpCoefficient` 表示输入和输出系数都不能超过的上限，
只支持 `billingUnit: AFP`。它与 `models` 手动选择取交集，与 `reasoningEffort` 独立。
例如上限为 0.5 时实际保留四个生产候选，评审模型不参与该过滤。
无候选时返回错误，不能悄悄放开上限或切换模型。

AFP 是成本维度，不是质量维度；六档是六个官方实际价格值，不是官方能力等级。
新应用示例给所有候选相同的未校准预测，避免从价格推导质量。
用户要让质量优先产生有依据的模型差异，需配置质量预测或进行独立评测。

历史 `data/model-manifests/volcengine-agent-plan.json`、旧清单与报告均未修改。
DSH Ark 设置预设改用完整应用配置；CLI 历史 preset 路径保留，
通过 `config-example --provider-type ark-agent-plan` 可导出同一完整应用配置。
