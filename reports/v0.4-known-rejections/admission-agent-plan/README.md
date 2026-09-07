# v2 单轮准入验证

2026-09-07 从干净提交 `a6554bf`，通过独立 DSH profile 的原生验证工具执行。
本轮使用显式 `exclude-known-contract-rejections-v2`；prompt/checks v0.3、三候选 Flash/M3/Pro、
独立 K3 judge、temperature 0、thinking disabled、8192 输出上限与零重试均保持冻结。
新增的 19 模型目录没有扩展这次实验模型池。

DSH 状态：**pass**。Benchmark 完整性：**complete**。
收益判定：**Insufficient-evidence**。只有一个任务、一个轮次，不能关闭 #22 或启动 pilot。

## 最终质量与生产成本

| 策略 | 独立质量分 | 路线生产成本 AFP | 关键路径 ms | 比较轮次 / 预期 |
|---|---:|---:|---:|---:|
| node-oracle | 89.0 | 6.29415 | 89814 | 1/1 |
| node-type-rule | 91.0 | 5.8422 | 92268 | 1/1 |
| strong-all | 96.0 | 9.3016 | 115671 | 1/1 |
| task-oracle | 96.0 | 9.3016 | 115671 | 1/1 |
| weak-all | 87.0 | 0.55335 | 50627 | 1/1 |

质量、成本和延迟使用同一成功且独立评审集合；费用只含执行路线。完整支出另计探针、
节点 judge、最终 judge 与外层 DSH。比较细节见 [配对比较](strategy-comparisons.md)。

## 候选矩阵及规则验证

保存 21 格矩阵；状态：`{'judged': 21}`。
选中 7 个节点候选。
原始输出、检查、独立分数、成本和上下文哈希完整保存在 [矩阵](node-quality-matrix.json)。
选择理由和分配见 [v2 决策记录](selection-report_001-1.json)。
已知拒绝保留在 failure_taxonomy；blocking_failures 专门表达使实验不完整的条件。

本轮未出现契约拒绝，因此真实运行验证了 v2 的完整执行路径；拒绝排除与未知阻断的边界由
历史真实失败回归及确定性模拟准入验证，不将未发生的故障写成已完成的实时验证。

本轮最佳单模型为全 Pro：96 分、9.3016 AFP。混合路线为 89 分、6.29415 AFP，
质量低 7 分，成本约低 32.33%，关键路径延迟约为基线的 77.65%。质量差超过既定 2 分
同质量门槛，因此不能将节省成本解释为已满足路由收益条件；单轮也不能用于稳定性推断。

## 费用与证据

- 生产（含探针）：41.15905 AFP。
- 评审：102.305 AFP。
- 外层 DSH：0.20625 AFP。
- 本轮合计：**143.6703 AFP**。
- 旧授权内已知费用加未结算保留额：967.19845 AFP；剩余 1537.80155 AFP。
- 旧未结算请求仍保留 16.192 AFP，未读取或披露账户级账单。
- 本次部署上限为生产 250、评审 430、外层 0.7 AFP；结束后已恢复关闭 paid profile。
- 所有调用使用 Ark Agent Plan `/api/plan/v3`，没有后付费端点回退。

[账本](cost-accounting.json)、[外层 usage](outer-agent-usage.json)、[DSH evidence](dsh-evidence.json)、
[原始索引](evidence-index.json)、[请求遥测](model-progress.ndjson)、[失败分类](failure-taxonomy.md)。
[独立审计](audit.json)验证 21 个原始索引产物、21 格上下文与输出哈希、82/82 请求对应关系，
所有请求 `stop`、一次尝试；当前凭据扫描匹配数为零。
[离线复核](../admission-review/reviewed-summary.json)保留单轮 Insufficient-evidence 判定。

本轮 143.6703 AFP 低于 680.7 AFP 信封。累计已知费用为 951.00645 AFP，保留旧未知
结算请求的 16.192 AFP 后合计 967.19845 AFP；2505 AFP 总授权尚余 **1537.80155 AFP**。
下一次全新三轮估算 1979.87 AFP，比当前剩余高约 442.06845 AFP，尚未安排。

## 后续边界

本次是规则变更后的单轮准入，不与历史两轮拼成一个新的三轮实验。
#22 仍需在同一冻结配置下获得完整三轮对照；再核算预算后安排。
当前不启动 #5 pilot，也不以单轮结果宣称可部署的路由收益。
