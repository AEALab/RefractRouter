# Ark thinking:auto 相容性

核验日期：2026-09-13。端点：`https://ark.cn-beijing.volces.com/api/plan/v3`。
本表针对 `thinking: {type: "auto"}`，不是默认省略参数，也不是 reasoning effort 的 `medium` 等档位。

| 模型 | 结论 | 依据 |
|---|---|---|
| doubao-seed-2.0-mini | 不接受 | HTTP 400 明确拒绝 auto；上一轮移除字段后 200 |
| doubao-seed-2.0-lite | 不接受 | HTTP 400 明确拒绝 auto |
| doubao-seed-2.1-turbo | 不接受 | HTTP 400 明确拒绝 auto |
| doubao-seed-evolving | 不接受 | HTTP 400 明确拒绝 auto |
| glm-5.3-flash | 不接受 | HTTP 400 指出 type 的 auto 值无效 |
| glm-5.3 | 不接受 | HTTP 400 指出 type 的 auto 值无效 |
| deepseek-v4-flash | 接口接受 | HTTP 200 |
| deepseek-v4-pro | 接口接受 | HTTP 200 |
| minimax-m3 | 未确认 | HTTP 400 一般参数错误，尚不能归因于 auto |
| kimi-k2.7-code | 未确认 | HTTP 400 一般参数错误，尚不能归因于 auto |
| kimi-k3 | 未确认 | HTTP 400 一般参数错误，尚不能归因于 auto |

## 配置行为

预设保持省略未经逐模型验证的可选思考参数，GLM-5.3 保留已知强制开启要求。
用户显式配置 auto 时，Python 配置编译层拒绝已明确不接受的 Ark 型号，错误包含型号与修改建议，
在凭证解析和模型请求前阻断。接口接受的两个 DeepSeek 型号仍保留用户显式配置。
未确认型号不伪装成已确认拒绝；其他 provider 类型和未收录型号不套用这份端点特定限制。
DSH 设置只展示由 Python 资源导出的状态，不重复实现参数兼容判定。

## 证据与边界

[本轮十次诊断](../reports/ark-thinking-auto-2026-09-13/auto-probes.json)保留响应状态、错误与用量，
不保存密钥或用户对话。用户授权最多十次、总上限1.5 AFP，全部零重试、输出16 token。
十次保守预留合计1.0519 AFP；两次成功请求已知用量合计0.0612 AFP，错误响应未报告用量，
不能断言这些失败零扣费。豆包 mini 使用上一轮已授权的两次对照证据。

HTTP 200 仅证明参数被接口接受，不证明后端采用自适应思考，也不验证完整回答、DAG、质量、
其他参数组合或不同账户权限。此快照需要在供应商行为变更后重新核验。

## 紧凑规划的思考预算

思考 token 计入输出配额时，过小的规划输出容量可能导致 JSON 尚未输出便截断。
核心 0.5.0 的自动紧凑规划使用模型完整输出容量，取消应用附加的规划超时。
此前 0.4.4 针对豆包 mini 默认关闭思考的临时策略已撤销。
用户可通过 `plannerThinking` 选择继承模型设置、开启或关闭；默认继承。
该设置只作用于规划副本，节点执行与评审保持各自设置。

模型物理容量、供应商限制和用户预算仍有效；截断计划仍然失败，诊断保留结束原因、
输出 token、思考 token 与容量。确定性测试验证容量传递、无超时、阶段隔离和配置保存。
