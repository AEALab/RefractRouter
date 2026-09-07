# DAG 拆分机制

本轮实现 Issue #32 的规划与交接机制。目标是为节点路由提供可检查的任务边界，并识别
真实并行机会。运行器已支持有界并发、原子预算预留和匹配的调度预测；
分层 profile 已完成一轮真实校准；DSH 实际助手调用已通过单任务端到端验证。
完整多任务留出对照与真实异构交接仍未完成，不将宿主入口通过解释为已取得路由收益。

真实宿主验证还补齐了两项规划要求：输入容量须按完整序列化消息的 UTF-8 字节数加
256 的保守上界估计；只有最终节点作为交付，必须保留用户要求分别呈现的全部部分。
中间分析完成不能代替最终输出覆盖。详见
[真实 DSH 验证报告](../reports/dag-decomposition/issue-32-dsh-live-20260907/README.md)。

## 规划规则

模型规划器按原始任务选择 1 至 8 个节点，说明拆分收益及交接、重复输入和汇总开销。
简单任务允许不拆分，短小或强耦合步骤可以合并，不要求使用不同模型。
按主要能力划分职责，支持 planning、extraction、synthesis、generation、verification。
共同读取原始材料不构成依赖；只有消费上游产物才建立边，并说明所需字段及原因。

每项验收要求至少有一个负责节点，所有节点必须汇入最终文本产物。
模型应保留来源、假设与不确定性，汇总节点核对冲突、遗漏和术语一致性。
图校验只检查声明是否一致，不能证明模型描述的依赖语义真实或验收条目充分。

`acceptanceCriteria` 可由用户固定 1 至 10 条要求；规划器必须逐项原样保留及维持顺序。
未提供时由模型提取，最终独立评审仍以原始任务为依据，不能只依据模型自行缩减的条件。

## 契约版本

新模型规划必须使用 `schema_version: "text-task-plan-v2"`。
顶层字段为 `schema_version`、`decomposition_reason`、`nodes`、`final_node_id`、
`acceptance_criteria`。旧版无版本的显式 `plan` 可继续使用，并在诊断中显示
`legacy-plan-without-handoff-contracts`；旧格式不会被自动包装成经过新版校验的计划。

每个节点保留 `node_id`、`node_type`、`prompt_template`、`parents`，新增 `contract`：

| 字段 | 约束与含义 |
|---|---|
| `objective` | 非空的主要职责说明 |
| `inputs` | 键必须与 `parents` 完全一致；每项包含非空 `reason` 及消费字段列表 `fields` |
| `output` | `format` 为 `text` 或 `json`；`fields` 将字段名映射到内容要求 |
| `capability` | `difficulty`、`risk` 为 low/medium/high；包含输入预算和输出需求 |
| `checks` | 1 至 10 条节点语义检查要求，作为节点执行指令，不冒充独立评分 |
| `covers` | 负责的全局验收条目的零基索引；整体必须覆盖所有条目 |
| `execution` | 当前仅支持 `text-model` |
| `failure_policy` | 当前仅支持 `stop`，不自动重试或放宽约束 |

`text` 输出只能声明 `text` 字段，执行时直接返回文本；最终节点必须为此格式。
`json` 输出声明 1 至 8 个字段，每个字段的值均为非空字符串，禁止多余或缺失字段。
这是有界的扁平对象契约，不支持任意嵌套 JSON Schema。若需描述结构化证据，可在
`evidence` 字符串中保留来源 ID、事实和关联关系。

输入预算 `input_budget_tokens` 范围为 256..131072，输出需求
`expected_output_tokens` 范围为 1..8192。路由器筛除无法容纳声明输入预算和模型
输出上限、或输出上限不足的候选模型。运行时再按既有 UTF-8 字节数加封装余量的保守
输入估算检查请求，超出节点预算时停止，不截断任务或交接材料。
输出需求用于容量筛选，不是新的输出截断值；实际请求仍遵守模型清单上限。

`node-routing-profile-v2` 按主要能力、难度、风险及声明输入预算区间匹配；
没有匹配分层时返回无可行路线，不自动使用通用行。v1 仍按节点类型匹配。
这些值是质量代理；声明高难度不会自动指定强模型，也不能证明实际质量。

## 交接与诊断

所有节点获得原始任务，以保持交付目标和原始证据可见；父节点产物仅传递声明字段。
输出结构校验在调用结算之后、下游执行之前进行。失败时保存无效原文和费用，阻止
剩余节点与最终评审；成功的结构校验记录为 `structure-valid`，节点语义状态仍为
`not-evaluated`。运行结果的最终评分另由独立评审生成。

模型规划原文及提示协议哈希保留在 `task-result.json`，非法规划也保留原文和已发生费用。
每次有效规划保存 `plan-analysis.json`，同时嵌入 `task-result.json` 的 `plan_analysis`：

- `ready_waves`：按依赖计算的就绪波次，同一波次没有彼此依赖。
- `dependency_depth`、`max_wave_size`：图的依赖层数及最大波次大小；不是运行时最大并发度。
- `parallel_opportunities`：多节点就绪波次，表达静态调度机会。
- `join_nodes`、`downstream_counts`：汇总位置与错误可能传播的下游节点数量。
- `criterion_owners`：每项验收要求的负责节点。
- `warnings`：旧契约、重复指令和输入、到达节点上限、汇总上下文等结构复核提示。

提示不会自动删除边、合并节点或宣称语义失败；同类型节点也可以承担不同工作。
运行时的 `execution_mode` 按配置显示 `serial` 或 `bounded-parallel`；
它表示执行策略，实际并发须检查节点时间戳及 `peak_running_nodes`。
`semantic_dependencies_verified` 始终为 false。
关键路径时间、并行墙钟时间和任务 p95 不由波次大小推导。

## 离线示例与使用

固定示例均不需要调用模型，不是规划器真实质量的证据：

| 示例计划 | 对应任务与结构 |
|---|---|
| [并行分析](../data/task-plans/parallel-analysis-v2.json) | 给定两方案的独立成本与风险材料，分别分析后汇总；两分支没有数据依赖 |
| [必要串行](../data/task-plans/serial-analysis-v2.json) | 根据成本测算判断资金不足风险，风险分析必须等待成本节点 |
| [单节点](../data/task-plans/single-answer-v2.json) | 将用户给定句子改写得更简洁，无需增加规划或汇总节点 |

从仓库根目录生成一个显式计划的模拟请求，并执行同一核心运行时：

```bash
run_dir=$(mktemp -d /tmp/refractrouter-dag-v2-XXXXXX)
uv run python - "$run_dir/request.json" <<'PY'
import json
import sys
from pathlib import Path
plan = json.loads(Path('data/task-plans/parallel-analysis-v2.json').read_text())
request = {
    'task': '根据给定材料比较试点与全面推广的成本和风险；资料不足时说明缺口，不虚构数字。',
    'mode': 'demo', 'method': 'A', 'qualityMin': 80, 'costMax': 1,
    'latencyMaxMs': 300000, 'maxConcurrency': 2, 'providerConcurrency': {'openai': 2},
    'acceptanceCriteria': plan['acceptance_criteria'], 'plan': plan,
}
Path(sys.argv[1]).write_text(json.dumps(request, ensure_ascii=False))
PY
uv run python validation/dsh/task_runner.py \
  --request-file "$run_dir/request.json" \
  --profile data/routing/demo-usd-v1.json \
  --manifest data/model-manifests/openai-gpt-5.4.json \
  --output-dir "$run_dir/output" --evidence "$run_dir/evidence.json"
```

DSH 插件 `refractrouter_task` 接受相同请求字段，仅负责传递和结果展示。
未提供计划的 `preflight`/`demo` 现在只使用标注的单节点预览，不执行语义拆分。
要观察真实模型拆分，使用 `plan`；调用前仍需付费开关、模型凭证与明确的生产/评审预算。
本次修改和离线示例均不包含真实模型调用或新增预算授权。

## 并发与后续验收

调度按就绪节点逐个释放，不等待整个静态波次结束。JSON 交接校验成功后才释放下游；
失败、取消或到期后停止新派发，等待在途调用结算，未知用量保留预留金额。
启动间隔和并发上限只约束本任务的节点调度，不是账户级 RPM/TPM 限流。
使用 DSH stdio LLM 桥时仍限串行；Agent Plan 直连路径支持并发。

完整参数与限制见 [文本任务指南](text-task-routing.md)。
冻结任务、六组对照、分层校准、留出测试和预算见 [多任务对照协议](dag-study.md)。
