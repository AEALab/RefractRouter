# 独立评审的两样本准入

下一步先验证 GLM-5.3 是否能区分缺乏实质比较的报告和内容较完整的报告。
本阶段仅两次独立评审调用，不生成 K3 基线、不执行节点探针、不启动完整 DAG 对照。
代码和零调用预检已准备好，真实可用性及校准结果仍待验证。

## 模型与请求

选择 GLM-5.3 是因为它不参与当前 K3／Flash／M3／Pro 生产对照，且在同一 Agent Plan
清单内。不同模型并不保证评分无偏；本次校准正是检验其准入条件，不能提前认为它合格。

2026-09-07 重新读取官方文档确认：GLM-5.3 默认开启思考且不能关闭，支持 1024k 上下文。
[官方套餐概览](https://www.volcengine.com/docs/82379/2366394?lang=zh)

输入、输出抵扣系数均为 4.5 AFP／万 token，即每千 token 0.45 AFP。
费用按输入和输出 token 计算，不将 reasoning token 在总输出之外重复加价。
[官方计费说明](https://www.volcengine.com/docs/82379/2516283?lang=zh)

请求固定使用 `/api/plan/v3/chat/completions`、`glm-5.3`、开启思考，输出上限 8192 token，
零重试。采用提示词要求 JSON，不假设尚未实测的 `response_format` 支持情况。
每份材料单独调用；不给出模型映射、历史分数、正反例标签或校准通过阈值。
提示明确将来源和报告视为不可信数据，不能服从其中改变评分的指令。

## 费用与停止条件

根据当前冻结两份材料，使用完整提示的 UTF-8 字节数加协议余量预留输入，
再加每次 8192 输出 token。合计保守预留约 **23.47 AFP**，建议本阶段授权额度为
**25 AFP、最多两次请求、零重试**。这不是实际消费预测，也不是服务端硬账单上限；
实际用量以响应记录为准。该额度不包含或授权后续生产实验。

该入口是独立评审的 Python 调用器，通过现有 Agent Plan 客户端发送请求；
本阶段不额外启动外层模型，因此没有新增 DSH 外层模型调用。
后续 K3 主对照仍通过其 DSH 原生入口执行。

截断、非法 JSON、样本错误、引文无法定位、缺少用量或请求失败时，保存已有证据并停止。
已返回用量的无效评分仍计费；未返回有效用量时总费用显示未知，不显示零。
预算不足时不发送下一次请求；不自动重新生成评分或更换模型。

## 冻结与执行

由于新增 Python 模块会改变主实验的代码快照，必须生成新预检，旧归档保持不变。

```bash
uv run python experiments/run_k3_baseline.py --output-dir /tmp/k3-next-preflight
uv run python experiments/run_blind_calibration.py \
  --input-dir /tmp/k3-next-preflight --output-dir /tmp/glm-calibration-preflight
```

这两条命令均为零调用。校准预检包含逐份请求、模型参数、费用预留、输入索引和代码哈希。
`--approved-preflight` 要求与本次材料和代码完全一致，但文件名或命令参数不替代用户授权。

只有获得本阶段明确预算授权后，才执行：

```bash
uv run python experiments/run_blind_calibration.py \
  --input-dir /tmp/k3-next-preflight \
  --approved-preflight /tmp/glm-calibration-preflight/preflight.json \
  --execute-paid-run --max-review-cost 25 \
  --output-dir /tmp/glm-calibration-paid
```

产物包括逐次原始响应与用量 `responses.ndjson`、请求进度、校准汇总；评分格式有效时，
还生成可直接交给 K3 主入口的 `reviews.json`。出现未知费用先核对账单与请求记录，
不得直接重跑整个阶段。

通过标准沿用已冻结规则：缺乏比较的样本不高于 50 分且识别出比较缺失，
内容较完整样本至少 80 分，两者差距至少 20 分。
两例通过仍不足以证明评审可靠，不自动启动生产实验、扩大样本或宣称路由收益。
没有真实执行前，不修改模型目录中的 `live_verified: false`。
