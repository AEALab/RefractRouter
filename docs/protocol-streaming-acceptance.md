# 现有协议、流式与结算验收

对应 [W08 / #209](https://github.com/AEALab/RefractRouter/issues/209)。本包在既有
Chat Completions、Responses → 上游 Chat Completions 范围内修复转换与记账，
不增加新协议、不改变模型路由策略、不进入 DAG 或宿主工具执行循环。

## 版本与准入

`refractrouter-gateway-config-v2` 显式启用全执行候选准入；已有 v1 配置继续保留，
其模型目录标注 `legacy-unverified`，不能据此声称整个模型池已兼容。
宿主可以在 planning v8 中显式配置
`protocolAdmission: "all-executor-protocol-admission-v1"`，复用同一 Python 检查。

准入覆盖 Static 的实际候选（含随机模式）、Task 池与回退、Stage 的两侧模型、
Escalation 的初始及接管模型、Advisor 的执行模型、Composite 的可能执行模型。
内部 Judge 有自己的请求合同，不承接用户的输出格式要求。
请求使用 function、JSON object、JSON Schema、strict tools、tool choice、并行工具或
`prompt_cache_key` 时，所有可能执行候选均须有对应 `verified` 配置及足够容量；
任一候选未经验证即在分类或执行调用前拒绝。

这些配置声明是准入依据，不是由本批模拟测试签发的真实供应商资格。
实际后端、模型版本及思考设置仍须独立验收；一个后端成功不能代表整个池成功。
同一在途任务继续使用冻结配置，不因全局配置更新而换用新的能力或思考声明。

`executionOptions` 在执行、重做、接管和宿主压缩中保留，Schema 等内容同时进入容量、
隐私域检查、费用预留及请求摘要，不把 Schema 插入或重排宿主消息。
显式调用方输出限制记录为 `caller_output_cap`。Task v1 经验组尚未按这些动态合同分层，
带合同的记录（含压缩）排除，已生成的影子预测在合同改变后标为失效，实际选模不变。
未指定输出限制的请求继续使用模型配置中的原生上限。

## 工具与思考历史

工具 ID、名称、参数和结果必须配对，未知、重复或篡改的关联在第二次派发前拒绝。
即使当前 `tools` 为空，只要历史仍包含工具调用，也要检查候选的 function 能力。
工具由宿主执行，Router 不执行请求中的工具。

真实思考历史只在可验证的原调用归属与允许的模型组合间续接；不支持的组合明确拒绝，
不删除思考块来伪造兼容。Responses 的客户端输出不泄露私有思考，后续工具结果在
同源续接时可以恢复供上游使用的历史；重启、跨任务、身份或历史变化沿用既有隔离检查。

历史 `deepseek-recipe` 调研形成的协议夹具已迁入正式测试。
[来源摘要](../data/protocol-streaming-v1/provenance.json)记录原工作区未提交文件的身份；
来源提交不冒充已包含这些未提交内容。本轮执行的是本项目的确定性夹具，
没有执行 recipe 生产服务或验证真实供应商兼容性，历史原始产物保持原样。

## 结束、取消与用量

流式测试按字节边界拆开中文、emoji、组合字符和工具参数，检查拼接后的内容与非流式
一致。响应 ID 中途变化、缺少结束、结束后继续输出、用量冲突均停止，不自动重发请求。
工具及成功结束事件须在结算后释放；`length`、过滤或错误不会变成成功交付。
Responses 转换保留 incomplete / failed，未完成的工具条目也不能标为 completed。

已知用量后取消的旧路径可能在提交 `complete` 前退出。本包先取消任务，阻止后续
Judge 或模型派发，再用原候选证据结算已知用量一次。候选继续标为丢弃，不交付、不执行
工具。中止或截断后的工具证据仍用于校验零输出等矛盾用量，不能清空后报成已知零用量。
候选无法合法投影、用量缺失或冲突时保留未知预留；重复回执不再次记账。

输入、输出及思考用量只接受非负原生整数，思考量不能超过输出量；同义字段同时出现时
必须一致，显式总量必须等于输入加输出。思考是输出的细分，不额外加一次费用。
原始用量保留在账本证据中。

## 缓存与费用

缓存字段透明透传，不重排 system、tools 或 history，不推定换模能共享 KV 缓存。
缓存读取量记录来源；供应商未报告和明确报告零分开。
公开汇总只有在该请求全部调用的对应细分已知时才提供，不能把部分已知伪造成完整总量。
缓存写入量同样保留可观测性；写入与普通输入单价不同时，回执缺少写入量就保留未知预留。
两者同价时金额可确定，允许结算，但写入细分仍保留未知；阶梯价格按实际输入档位比较。
已知写入按既有单价结算一次。

各调用的输入、缓存读写、计价快照和费用可以按调用顺序比较；命中数和标准单价估算
不能替代供应商实际扣费。取消、评审、重做及丢弃候选仍计入完整费用。

## 时间与交付观测

| 字段或范围 | 含义与边界 |
| --- | --- |
| `ttft_ms` / `latency_ms` | 单次上游调用的首 token 与调用耗时；首 token 不等于公开文本。 |
| `routerOperationMs` | Python 单次路由操作墙钟时间，含校验及证据写入，不称为纯 CPU 时间。 |
| `routerRoundTripMs` | DSH 到 Router 的一次操作往返，含进程通信；不冒充独立推理时间。 |
| `userFirstTextMs` | 从该宿主模型请求开始，到首段公开文本交付到客户端接口的耗时。 |
| `deliveryMode` | `live-text` 或 `buffered-release`，区分边生成边交付和审核后释放。 |
| `releasedTextBytes` | 本调用已交付公开文本的 UTF-8 字节数，不含私有思考或被丢弃候选。 |
| 任务与本地 Judge 时间 | 沿用任务起止、调用及本地服务观测；未提供的分项保持未知。 |

DSH 的首次文本指交付给宿主 Agent，不证明浏览器已绘制；Gateway 指成功回调到客户端
接口。消费中断但已交付片段仍可记录，回调拒收不能登记为已交付。
交付观测通过绑定当前任务真实 call ID 的独立 RPC 追加，不改变计费、质量或选模。
观测格式错误不使已经合法结算的用量变成未知；证据写入失败仍按原规则停止。

上游未单独提供服务端排队和推理时间时，这两项保持未知，不能用总耗时相减补造。
缓冲策略的上游首 token 不代表用户首字等待。少量夹具只验证计量语义；没有足够同条件
真实观测就展示原值或范围，不发布 P95 或声称用户等待已降低。

## 验收与后续

| 验收范围 | 证据入口 |
| --- | --- |
| 转换、工具续接、私有历史、结束及中文分块 | `test_recipe_protocol_differential.py`、`test_recipe_streaming_differential.py`、`test_gateway_streaming.py` |
| 全候选能力、容量、Schema 预留及数据域 | `test_protocol_admission.py` |
| 用量别名、缓存细分与未知预留 | `test_usage_integrity.py`、原预算与协议测试 |
| 已知用量后取消、未知回执和工具证据 | `test_terminal_planning_usage.py`、DSH planning 契约测试 |
| 交付观测归属、缓冲及消费中断 | `test_transport_observation.py`、Gateway 与 DSH 流式测试 |
| 动态压缩合同不借用旧费用经验组 | `test_task_empirical.py` |
| 脱离源码的实际安装包 | `scripts/validate_refractagent_install.py` 调用 `validate_gateway_protocol_install.py` |

安装验收使用实际 wheel、tgz 和本机固定 HTTP 上游，验证 Responses 工具与思考续接、
Chat JSON Schema、Unicode SSE、缓存用量以及不兼容候选的调用前拒绝；付费调用为零。
只有对应安装产物通过才报告安装验收成功。完整测试、独立审查及实际结果记录在 #209
对应 PR；本包通过不表示开放任务质量或成本收益已证明，真实收益统一由 #210 验证。
