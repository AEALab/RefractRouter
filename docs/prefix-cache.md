# 稳定前缀与缓存验证

关联：[#72](https://github.com/AEALab/RefractRouter/issues/72) 第三阶段。

通过 Python / CLI 的 request-file 设置 `"prefixPolicy": "stable-v1"`。
默认 `legacy` 保留既有布局；自动规划、显式 DAG 与直接回答均可启用，
本轮不新增 DSH 配置界面，也不改变调度并发、输出容量、取消或预算机制。

## 请求变化

节点 user 消息先放任务材料与输出约束，再放节点职责、契约、ID 和上游产物。
嵌套对象按键名稳定排序，数组与原文内容不重排。已有 system 指令保持不变。

结构化材料先放共同任务、验收要求，再放全局来源及其 requires 闭包，最后放局部来源；
同组按来源 ID 排序。`selective-v1` 仍按已声明的来源选择原文。
最终节点保留全文，最终评审的任务、system 指令、模型和规则不变。
没有结构化材料时不猜测边界，保留整个 task 字符串。

容量预估、整图准入、实际派发、备用模型与动态再拆使用同一节点消息构造器及策略。
格式不同的节点可能有不同 system 指令；不同局部材料也会缩短共同前缀。
这些情况下不保证缓存复用，更不假设不同模型之间可以复用 KV cache。

## 用量语义

每次账本保留 `input_tokens`、`output_tokens`、`cached_input_tokens`、`latency_ms`，新增：

- `cache_usage_source`：实际 HTTP 返回的缓存计数字段路径；未报告时为 null。
- `cache_usage_available`：是否取得有效缓存字段。false 时数值字段中的 0 只是兼容值，
  不能解释成供应商确认没有命中。DSH 桥接当前也不作为原始供应商缓存证据。
- `ttft_ms`：当前客户端是非流式，记录 null；不把整次请求时延冒充首 token 时延。

识别 Chat Completions 的 `prompt_tokens_details.cached_tokens`、
`input_tokens_details.cached_tokens`、`prompt_cache_hit_tokens`，以及 Responses 的
`input_tokens_details.cached_tokens`。非法数值或互相矛盾的字段保留未知用量和预算预留，
不能静默当作零命中结算。原始 HTTP usage 继续留在 response 证据中。

缓存计费继续使用模型配置的价格。2026-09-14 核对的
[Agent Plan 官方 AFP 抵扣规则](https://www.volcengine.com/docs/82379/2516283)
按输入/输出 token 与模型系数计算；未取得本轮四个模型缓存输入的独立 AFP 折扣证据。
因此诊断协议把缓存输入按普通输入计费。报告的是 token 与冻结价格计算的 AFP，
不宣称已核对账号控制台逐笔扣减；缓存命中本身不代表 AFP 减少。

## 冻结诊断

协议：[prefix-cache-v1.json](../data/research/prefix-cache-v1.json)。
复用 #53 的六项公开开发材料，没有新增无用长文本来制造命中。
四个模型为 DeepSeek V4 Flash、MiniMax M3、DeepSeek V4 Pro、Kimi K3，
使用 `/api/plan/v3`、现有默认思考配置和底层零重试。

1. 32 次接口探针：4 模型 × 2 布局 ×（首次并发 2 次、首次顺序 1 次、重复前缀 1 次）。
2. 4 次应用执行，共最多 12 次调用：直接回答 / 同一张三节点图 × 2 布局。
   同图的统计与决策节点并行，最终节点交付。执行全部用 Pro，最终评审仍用 Kimi K3。
   显式冻结图不产生规划费用；自动规划选择和材料选择收益须另做消融，不能从本轮外推。

最多 44 次调用。应用继续保留候选模型完整输出容量，预算预留按其最坏情况设置；
整批 4000 AFP 是硬上界而非预计消耗，探针上限 240，每个应用生产上限 900、评审上限 40。
单探针或应用时间界限 300 秒；认证、未知用量、账本或证据异常停止整批并结算在途调用。
已知用量的探针输出失败保留后可继续独立诊断，不补跑、不追改冻结证据。

默认零调用预检：

```sh
uv run python experiments/validate_prefix_cache.py --output-dir /tmp/cache-preflight
```

读取该次 SHA256 后，另选全新目录执行：

```sh
uv run python experiments/validate_prefix_cache.py --execute \
  --freeze-sha256 <预检摘要> --output-dir <新目录>
```

不能清空服务端缓存，所以全部冷状态标为 `unconfirmed`。
各模型交替布局顺序，但无法排除跨布局及此前请求的缓存污染；
并发节点同时就绪即派发，不等待预热，也不为了命中串行化。
首次顺序与并发探针使用不同的真实任务子集；不能直接把两类时延差异归因于并发或缓存。
只在同任务、同模型下描述首次顺序和重复前缀变化。

每条应用路线仅一次，缓存、负载、输出长度及模型随机性均可能影响总时延。
模型评审通过不能代替 #52 的独立真人质量门槛；未完成质量准入前不称为 Pareto 解。

## 2026-09-14 live-01 结果

原始证据：[live-01](../reports/prefix-cache-v1/live-01)；
分析产物：[analysis-01](../reports/prefix-cache-v1/analysis-01/README.md)。
冻结摘要为 `1041103ba252978bad1574f029729d1629b6b6487d4cf9196934ee438abc61c9`。

整批 44 次调用全部结算，无未知用量；按冻结价格计算 105.54515 AFP。
输入 66,989 token、输出 158,597 token，接口报告缓存命中合计 6,144 token。
所有应用路线均通过原有模型评审，但尚未完成 #52 的独立真人质量复核。

| 路线 | 端到端秒数 | 生产 AFP | 评审 AFP | 总 AFP | 模型评分 | 缓存 token |
|---|---:|---:|---:|---:|---:|---:|
| direct-legacy | 101.268 | 2.85450 | 3.24500 | 6.09950 | 98 | 0 |
| direct-stable-v1 | 101.352 | 2.55695 | 3.88000 | 6.43695 | 90 | 1,024 |
| same-dag-stable-v1 | 142.598 | 7.29135 | 3.12800 | 10.41935 | 96 | 2,048 |
| same-dag-legacy | 189.631 | 9.98195 | 2.98500 | 12.96695 | 85 | 1,024 |

同一张三节点图中，stable-v1 单次观察比 legacy 快约 24.8%、少约 19.7% AFP；
但这只是每路线一次的开发诊断，不能推断稳定收益或 Pareto 改善。
直接回答在本次两条布局中都同时更快且更便宜；在模型评审均通过的前提下，
它仍是本批开发材料的支配路线。

接口探针只在 DeepSeek V4 Pro 的 stable-v1 布局观察到两次 1,024 token 命中；
DeepSeek V4 Flash、MiniMax M3、Kimi K3 的八次探针均报告零命中。
Pro 的重复前缀请求命中 1,024 token 后耗时 62.179 秒，首次顺序请求未命中时
为 61.816 秒；本批没有观察到缓存命中转化为整次请求时延下降。
Agent Plan 未核实缓存输入的独立 AFP 折扣，因此上述 AFP 均按普通输入价格计算。

实跑后补充了结构化材料的 `source_position` 字段：stable-v1 重排材料时保留
用户原始输入中的材料序号，避免“第一份材料”等位置指代失真。live-01 的四个
应用请求均未使用结构化 `materials`，因此该补丁不改变已归档实发请求；
完整回归 904 项测试通过，另 5 个子测试通过。
