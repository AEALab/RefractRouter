# 文本任务规划与节点路由

Python 核心负责 DAG 规划与校验、三指标选模、组合执行、预算记账及最终评估。
DSH 插件 0.7.0 的 `refractrouter_task` 提供宿主入口，与冻结基准工具
`refractrouter_validate` 并存。当前插件启动本地 Python runner，仍依赖匹配的源码环境；
它是核心能力的验证适配层，也是未来产品入口的一种形态，详见 [架构说明](architecture.md)。

当前节点只根据请求中的材料进行文本分析和生成，不执行浏览器、Shell、文件修改或其他
DSH 工具。不能把生成的操作建议当成已经完成的工具操作。

## 零调用运行

安装项目锁定依赖后，从仓库根目录运行：

```bash
npm run --prefix validation/dsh/plugin build
run_dir=$(mktemp -d /tmp/refractrouter-text-demo-XXXXXX)
uv run python validation/dsh/task_runner.py \
  --request-file data/routing/task-demo.json \
  --profile data/routing/demo-usd-v1.json \
  --manifest data/model-manifests/openai-gpt-5.4.json \
  --output-dir "$run_dir/output" --evidence "$run_dir/evidence.json"
```

示例使用确定性模拟产物，不解决真实任务，也不产生真实评分或模型费用。安装更新后的
插件并重启 DSH profile 后，可请 DSH 调用 `refractrouter_task`：

```bash
dsh plugin --profile headless add ./validation/dsh/plugin
dsh --profile headless --help
```

```json
{
  "task": "比较先做小规模试点与直接全面推广，分析成本、风险和建议。明确假设。",
  "mode": "preflight",
  "method": "B",
  "qualityMin": 80,
  "costMax": 1,
  "latencyMaxMs": 300000,
  "maxConcurrency": 2,
  "providerConcurrency": {"openai": 2},
  "providerMinIntervalMs": {"openai": 100},
  "weights": {"quality": 0.5, "cost": 0.25, "latency": 0.25}
}
```

未提供计划的 `preflight` 和 `demo` 使用标注的单节点预览，不验证模型拆分能力。
要观察模拟并行结构，传入 [并行计划示例](../data/task-plans/parallel-analysis-v2.json)。
单节点即使配置并发度 2，也只有一个节点运行。插件默认的 `demo-usd-v1.json` 是合成
profile，核心拒绝用它执行真实规划或节点调用。DSH 外层助手仍可能产生自己的模型费用，
不包含在插件的零调用保证和预算账本中；上面的独立 Python 命令没有外层助手调用。

## 模式与付费边界

| 模式 | 规划 | 节点执行 | 最终评估 |
|---|---|---|---|
| `preflight`（默认） | 显式计划或标注的预览 | 不执行 | 不执行 |
| `demo` | 显式计划或标注的预览 | 确定性模拟 | 不执行 |
| `plan` | 未提供计划时调用规划模型 | 不执行，返回 DAG 与模型分配 | 不执行 |
| `run` | 未提供计划时调用规划模型 | 按依赖及并发策略真实执行 | 清单中的独立评审模型 |

Agent Plan 部署配置示例：

```yaml
- id: refractrouter-validation
  config:
    allowPaidRuns: false
    billingUnit: AFP
    maxProductionCost: 100
    maxEvaluationCost: 50
    maxRetries: 0
    manifestPath: data/model-manifests/volcengine-agent-plan.json
    credentialEnv: CODEX_ARK_API_KEY
    taskProfilePath: data/routing/report-transfer-v1.json
```

这些数字是示例部署上限，不构成付费授权。实际调用前，须确认本次范围与生产/评审预算，
启用 `allowPaidRuns`，并在工具请求中传入不超过部署上限的 `maxProductionCost` 和
`maxEvaluationCost`。规划及节点调用记入生产账本，最终评审记入评审账本。
`plan` 也要求提供双预算，但不调用评审模型。`plannerModelId` 可指定候选模型；
未指定时，核心按输入和输出单价之和选择最低价候选。

独立 runner 还要求 `--execute-paid-run`、`--max-production-cost` 和
`--max-evaluation-cost`，与请求中的预算一致。凭证通过环境引用传入，不写进请求文件。
Ark 必须使用 `ark-plan` 和精确的 `https://ark.cn-beijing.volces.com/api/plan/v3`，零重试。

先使用 `plan` 检查真实拆分，再把产物的计划复制到后续请求的 `plan` 字段，可在 `run`
中执行同一个 DAG，避免再次规划。两次操作独立授权和计费，不重复收取历史规划费用。

## 规划、交接与执行

模型规划必须返回 `text-task-plan-v2`，声明拆分理由、输入字段及依赖原因、输出契约、
能力需求、节点检查和验收覆盖。结构与样例见 [DAG 拆分机制](dag-decomposition.md)。
`acceptanceCriteria` 固定 1 至 10 项条件，规划器不得改写或漏掉；未提供时由模型提取，
最终评审仍检查原始任务。旧版显式计划保持兼容并标注缺少契约，模型生成计划不允许降级。

所有节点获得原始任务；父节点只传递声明字段。JSON 交接要求精确字段集合和非空字符串，
最终产物须为文本。结构错误保存原文与费用，阻止下游。结构通过不能证明依赖语义正确，
节点检查清单也不是独立节点评分；实际任务质量由最终独立评审判断。

`maxConcurrency` 默认 1，范围 1..8。`providerConcurrency` 可进一步限制各 provider，
`providerMinIntervalMs` 设置节点请求启动间隔，范围 0..60000 毫秒。只接受模型清单中
存在的 provider。调度按就绪顺序逐个释放节点，不等待整个静态波次结束；下游必须等待
全部父节点成功并通过契约校验。DSH stdio LLM 桥暂时限串行，Agent Plan 直连支持并发。
这些限制作用于单次任务的节点调度，不是账户级 RPM/TPM 限流，也不覆盖外层 DSH 助手。

失败、取消或截止时间到达后，停止新派发并等待在途调用结算。尚未发送的预留可释放；
已发送但用量不明的调用保留预留。Python 线程无法撤回已提交给服务端的请求，不能承诺
取消后免计费或在截止时刻立即返回。任务 runner 接收 SIGINT/SIGTERM，DSH 仍保留
宿主进程超时边界；强制结束进程可能只能留下未确认费用。

## 三指标选模

v1 profile 按节点类型匹配；v2 进一步按主要能力、难度、风险和声明的输入预算区间匹配。
缺失或重叠分层、未知模型绑定、混合计费单位和非法数值会被拒绝。v2 缺失对应分层时，
不自动退回通用记录。节点输入及输出需求先用于筛除容量不足的模型；派发前再检查
完整请求的保守输入估算，超限时停止，不截断交接材料。

- `qualityMin` 是每个节点的 profile 质量代理底线，不是最终答案质量保证。
- `costMax` 限制预测节点总费用；实际规划/节点费用另受生产账本约束。
- `latencyMaxMs` 限制配置调度策略下的预计节点完成时间，同时设置任务总截止时间。
  实际规划消耗这个时间窗口，最终评审也须在窗口内完成。预测不包含规划、评审及实际
  网络和调度开销，不是 p95 或时延 SLA。
- A 在满足全局约束的组合中选择预测成本最低者；平手依次比较平均节点质量、调度时延、
  模型分配的字典序。
- B 要求三项非负显式权重且总和有限并大于零。质量与成本在每个节点的完整合格候选池中
  归一化，再对节点取平均；时延对完整 DAG 各组合的预计完成时间归一化。归一化边界在
  质量、成本、时延硬约束筛选前固定，恒定指标效用为 1。B 最大化加权效用，平手使用 A。

预测与执行共享依赖顺序、全局/provider 并发上限及启动间隔。`serial_latency_ms` 保留
累计节点耗时，`scheduled_latency_ms` 表示配置调度下的预计完成时间。非关键分支的
加速若不缩短整个 DAG，B 不会仅因此得到时延收益。

核心最多精确枚举 100,000 个组合；更大搜索显式报错，无可行组合时不放宽约束或指定
默认模型。平均节点分数与 B 效用都是选模代理，不能作为最终任务实测评分。

## Profile 与证据

`report-transfer-v1.json` 来自已归档 v0.3 的单报告任务、三次重复，使用平均独立节点
质量、平均 AFP 生产费用和最大观测节点时延。缺失或无效的模型/类型组整体排除。
跨任务使用它只是迁移预测；`kind: "empirical"` 是数据来源声明，核心不能独立认证
用户自定义 profile 的采集真实性。旧 profile 可生成到新路径：

```bash
uv run python -m experiments.build_node_routing_profile \
  reports/v0.3-contract-recovery/repeated-agent-plan --output /tmp/new-node-profile.json
```

v2 的输入预算分层为 `[256,8193)`、`[8193,32769)`、`[32769,131073)`，依据声明预算，
不是实际 token 用量。构建器要求相同上下文的完整候选矩阵、独立节点评分、原文和哈希、
正确用量以及不与测试集重叠的校准任务；每个分层至少 3 个样本。已知契约/语义失败排除
整个模型分层，未知质量不填零；合成观测始终生成合成 profile。
多任务校准、冻结对照和再构建命令见 [实验协议](dag-study.md)。

每次任务保存请求、profile、清单、`plan.json`、`plan-analysis.json`、`routing.json`、
`task-result.json`，有答案时另存 `answer.md`。账本保留请求和响应原文，证据文件记录
产物哈希。DSH 展示模型分配、受限长度的答案预览、费用、未确认预留、独立评分和产物路径，
以及执行模式、并发上限、观测峰值与预测时延。模式和配置不等于实际并发，须核对时间戳。

预算按请求 UTF-8 字节数加封装余量和清单输出上限保守预留，并发准入使用同一锁。
实际费用按服务端 usage 结算；超过预留会停止新调用，但不能撤销已发生费用。
评审失败仍保留答案、原始评审响应和账目，质量标为不可用。模型生成的 Markdown 和
交接内容均是不可信材料，不应作为系统指令执行。

## 节点失败后切换模型

Python `run_task` 与 DSH `refractrouter_task` 均接受 `maxNodeFallbacks`：默认 `0`，
设置为 `1` 时，失败节点可换一个模型再执行；最多为 `2`，即每节点至多三次尝试。
例如在原任务请求中加入：

```json
{"maxNodeFallbacks": 1}
```

当前支持已确认用量的结构错误、空输出和截断输出。回退沿用原始任务、节点契约及已经
通过的父节点字段，不把失败内容加入提示，也不重跑成功分支。只有替换结果通过结构
校验才释放下游；最终语义质量仍由原有独立评审判断。无法定位到单个节点的最终评审
失败，不会自动猜测并重跑节点。规划失败、认证/网络异常、未知用量、账本/归档故障、
取消和截止不会触发模型切换。

候选来自与初次路由相同的能力、输入规模和风险 profile，继续满足质量底线与模型容量，
并排除该节点已尝试的模型。A 按剩余预测成本排序；B 使用初次路由冻结的归一化尺度
和原权重，不根据失败后缩小的候选池重新归一化。其他节点分配固定不变。

启用时，失败调用和在途预留计入生产成本，再检查剩余节点预测费用、实际替换调用
预留及剩余截止时间；节点生产调用还以 `costMax` 作为总生产准入上限，包含此前规划
及失败费用。最终评审继续使用独立的评审额度。预测不能保证实际费用与时延，硬账本、
容量、总截止和 provider 并发/间隔仍在每次派发时执行；没有可行替代就停止该 DAG。
在途请求的剩余时延按完整 profile 时延保守估算，可能拒绝实际上仍能完成的替换。

结果中的 `routing.assignments` 与 `initial_assignments` 保留初始分配，`assignments`
记录当前执行分配；`nodes` 保留每节点最后一次状态，`node_attempts` 保存每次尝试。
所有尝试具有独立调用标签、原始输入输出、费用及时序，`recovery.events` 记录切换原因。
DSH 展示当前执行分配，完整历史从其返回的 `resultPath` 查看。

底层 HTTP 客户端仍零自动重试。旧冻结实验不启用节点回退；同一 DAG 单模型基线若
只替换其中一个节点便成为异构路线，不能继续用原名称参与收益比较。后续实验须分别
冻结节点切换、整任务换模型重跑和无恢复对照，将所有失败费用与时间纳入统计。

零调用机制验收：

```bash
uv run python -m experiments.validate_node_recovery --output-dir /tmp/node-recovery-validation-new
```

该命令仅使用确定性故障注入，验证输入交接、次数、模型切换及模拟账本，不验证真实
模型质量、成功率或回退的综合收益。
