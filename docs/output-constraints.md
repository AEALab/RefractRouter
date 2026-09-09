# 可选的最终输出长度检查

对应 [Issue #42](https://github.com/AEALab/RefractRouter/issues/42)。
250 只是该问题的回归测试上限，不是应用默认限制。未填写 `outputConstraints` 时，
应用不会添加字数上限，也不会从对话、引用材料或历史消息中自动提取长度要求。
模型输出仍受既有 `maxOutputTokens`、上下文与预算限制；token 与字数不是同一口径。

## 按任务设置

RefractAgent 请求文件可显式声明：

```json
{
  "task": "根据给定材料比较 A/B，给出成本、建议和一个风险。",
  "strategy": "balanced",
  "outputConstraints": {
    "maxLength": 250,
    "unit": "unicode-code-points",
    "countWhitespace": false
  }
}
```

保存为 `request.json` 后，以下命令只做预检，无模型调用：

```bash
refractagent run --request-file ./request.json --mode preflight
```

真实模式沿用安装指南的 provider、执行开关和预算参数。
`refractrouter_task` 工具也接受同名 `outputConstraints`，可逐任务设置。
自然语言中的“250 字以内”仍可由模型遵循，但只有结构化声明会启用确定性检查。
有歧义时应先明确口径，不将模糊要求自动转换成硬限制。

## 明确计数口径

三个字段必须同时提供，不接受多余字段、空对象或 `null`。

| 字段 | 取值与含义 |
| --- | --- |
| `maxLength` | 1–1000000 的整数上限；等于上限时通过 |
| `unit` | `unicode-code-points` 按 Unicode 码点计数；`utf8-bytes` 按 UTF-8 编码字节计数 |
| `countWhitespace` | `true` 计入所有空白；`false` 在计数副本中排除 Python `str.isspace()` 识别的字符 |

数字、字母、中文、标点和 Markdown 标记全部按所选单位计算；不只统计汉字。
例如 `中 A` 按码点计入空白为 3、不计空白为 2；按 UTF-8 字节分别为 5、4。
换行、制表符和全角空格可按上述开关排除；零宽空格 U+200B 不属于 `str.isspace()`。
组合附加符和 emoji 序列可能包含多个码点，不等于屏幕上的视觉字形数。
不做 Unicode 归一化、不移除 Markdown，也不把字符换算为 token。

检查对象是最终交付正文，不包含 DSH 的策略、费用和运行说明。中间节点不受此上限限制。
仅最终节点会收到结构化约束及其口径说明；计数检查不会触发节点回退或额外模型调用。

## DSH 原生模型入口

`refractagent` 插件实例的 `config` 可添加相同的 `outputConstraints` 对象。
修改后重启，该实例中的三个策略都会透传此约束。它适合明确要求固定长度的专用入口，
不是所有任务的默认配置；日常自由回答入口应省略该字段。
若不同任务需要不同上限，使用请求文件或 `refractrouter_task` 逐次传参。
升级时安装本分支匹配的 Python 核心及重建后的插件；旧核心不支持该请求字段。

## 结果与失败语义

Python 核心完成最终生成后、派发独立评审前保存正文和检查结果。
`result.json`、`summary.json` 及 DSH 运行说明分别呈现：

| 字段 | 含义 |
| --- | --- |
| `generation_status` | `not-started`、`running`、`completed`、`failed` 或 `simulated` |
| `quality`（底层为 `evaluation`） | 原始独立模型评审；未取得有效评审时为 `null` |
| `format_validation` | 确定性长度检查，含约束、实际长度、通过状态和最终正文 SHA-256 |

`format_validation.status` 为 `not-requested`、`not-evaluated`、`passed` 或 `failed`。
前两种的 `passed` 为 `null`，不冒充检查通过；预检、仅规划、模拟或未交付正文都不产生
真实长度通过结论。模拟说明文本也不作为真实答案验收。

语义评审有效但长度超限时，总状态为 `output-constraint-failed`，即使模型评审为通过也一样。
长度通过而语义评审失败时仍为 `quality-failed`。评审异常、超时或取消时保留相应的运行失败
状态，以及已经保存的正文和长度检查，不能用一次检查通过覆盖其他失败。
`refractagent run` 在 `output-constraint-failed` 时返回退出码 1，并输出完整结构化结果；
DSH 原生模型入口仍展示答案和失败状态，工具入口返回失败证据。回放保留两类评审结果。

本次不新增修复生成：不静默截断、不重写答案、不自动换模型。
原始响应、正文、语义评审、全部用量与失败原因继续保存。
只支持上述长度检查，不表示任意格式或所有自然语言要求都已经获得确定性验证。

## 原始问题的离线回归

测试只读加载归档的 M3 答案：原文 283 个码点，排除空白后 263 个码点。
将其作为模拟生产响应，独立评审替身仍返回通过；新检查应返回 263 > 250，
总状态为 `output-constraint-failed`，原文和两次调用的用量完整保留。
历史答案和原始评审不改写，也不重新发起真实模型调用。

```bash
uv run pytest tests/test_output_constraints.py
```

2026-09-09 本分支验证结果：31 项新增 Python 测试通过；完整 `uv run --offline pytest -q`
为 507 项测试、5 项子测试通过，包含 55 项 TypeScript 契约测试和编译产物安装检查。
TypeScript 严格类型检查与构建通过；未发起真实模型调用，历史 `reports/` 无变更。

本次新增模块会改变 K3 实验对全部 Python 源码的指纹。已核对：相对 `a9cf53c`，
指纹变化仅涉及 `agent.py`、`task_runtime.py`、`task_execution.py` 和新增长度检查模块；
历史 K3 的 DeepAgents 执行路径不导入这些应用模块，任务、模型、提示、评审和实验
runner 未变。兼容表追加原始成功基线到本次精确快照的登记，相关 40 项 K3/DSH 回归通过。
仅允许该成功基线恢复；已完成探针仍禁止跨版本 `compose/finalize`，未放宽历史冻结规则。
