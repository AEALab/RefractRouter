# Refract Agent（析衡）

> 析构知难，衡派选优 — Refract the task, spend every token where it matters.

RefractRouter 是一个面向**任务分解感知的异构 LLM 路由**研究项目。它研究的问题是：当复杂任务被表示为 DAG 后，如何在质量、成本和延迟之间为每个节点选择合适的模型，而不是只在整个请求层面选择一个模型。

## 当前状态

v0.1 已进入可运行原型阶段。当前实现包含：

- 固定 7 节点报告生成 DAG、冻结 source pack 与离线 fake model adapter。
- `weak-all`、`strong-all`、`node-type-rule`、`task-oracle`、`node-oracle` 基线策略。
- DeepAgents 0.7 宿主运行时与 LangGraph 执行底座。
- 可追溯的最终 HTML 引用、确定性评分、baseline 表、Pareto 表和 oracle gap 报告。
- 可安装的 DSH bundle、结构化验证工具与确定性 runner；已在隔离 profile 通过真实 DSH
  headless tool call 验证。
- 20-task 合成 benchmark（train/test 各 10 个）、USD/AFP 真实模型 manifest、
  OpenAI-compatible 与 DSH LLM adapter、真实 token/成本/延迟遥测、独立 judge 与预算保护。

首次真实 Agent Plan paid dry run 已验证专属 `/api/plan/v3` 传输、遥测和 DSH 证据链，
但因默认深度思考耗尽 1,200-token 输出额度而以 `incomplete / No-go` 结束；证据保存在
`reports/v0.1-real/dry-run-agent-plan-default-thinking/`。修正版关闭候选模型与 judge 的
thinking，并保持原输出额度和 AFP 上限。第二轮已完成 41 个无 reasoning 的生产请求，随后
在首次 judge 预算检查暴露并修复了字段引用错误。pilot 在修正版 dry run 完整通过前保持阻塞。

## Quick Start

```bash
uv sync --extra dev --extra deepagents
uv run pytest
uv run refractrouter run \
  --task data/tasks/report_001.json \
  --strategy strong-all \
  --output reports/v0.1/report_001-cli.html
uv run python experiments/run_v0_1.py
uv run python validation/dsh/canonical_runner.py \
  --task data/tasks/report_001.json \
  --output-dir /tmp/refractrouter-canonical-validation \
  --evidence /tmp/refractrouter-canonical-evidence.json
uv run python experiments/run_real_v0_1.py \
  --phase dry-run \
  --output-dir /tmp/refractrouter-real-preflight
npm install --global pnpm@10.15.0 @deepseek-ai/dsh@0.1.1-rc.2
dsh plugin --profile headless add ./validation/dsh/plugin
dsh --profile headless --dump-config | rg -A6 refractrouter-validation
python3 scripts/validate_dsh_plugin_lifecycle.py
dsh --profile headless \
  'Call refractrouter_validate exactly once with {"phase":"final","executePaidRun":false}. Return the tool result unchanged.'
```

命令说明：

- `uv sync --extra dev --extra deepagents`：安装测试依赖与 DeepAgents/LangGraph。
- `uv run pytest`：运行完整测试套件。
- `uv run refractrouter run ...`：执行一次 canonical task 并输出 standalone HTML。
- `uv run python experiments/run_v0_1.py`：运行五个策略并生成实验报告。
- `uv run python validation/dsh/canonical_runner.py ...`：在隔离目录重跑完整实验、
  独立计算 oracle gate，并输出可审计的验证证据。
- `uv run python experiments/run_real_v0_1.py ...`：默认只执行真实模型 preflight，
  检查数据集、模型快照、凭据是否存在、调用数量和成本估算，不调用 API。
- `dsh plugin ...`：把 `dsh-refractrouter-validation` bundle 安装到 profile；之后通过
  `refractrouter_validate` 结构化工具运行验证，不让模型临时组装 shell 命令。
- `python3 scripts/validate_dsh_plugin_lifecycle.py`：在临时 `DSH_HOME` 中验证插件安装、
  配置覆盖、卸载、重装和启动；不会发起模型调用。

## Real-model benchmark

仓库提供两个 v0.2 模型清单：`data/model-manifests/openai-gpt-5.4.json` 使用 USD
计费和直接 Chat Completions；`data/model-manifests/volcengine-agent-plan.json` 使用 AFP
计费，并调用方舟 Agent Plan 专属 `/api/plan/v3/chat/completions`。方舟候选池冻结为
`deepseek-v4-flash`、`minimax-m3`、`deepseek-v4-pro`，独立 judge 为 `kimi-k3`。
当前 AFP 系数及支持范围来自[方舟抵扣规则](https://www.volcengine.com/docs/82379/2516283?lang=zh)
和[套餐概览](https://www.volcengine.com/docs/82379/2366394?lang=zh)。

三阶段默认调用量和保守成本估算如下。估算假设每个生产调用 4,000 input / 1,200
output tokens、judge input 8,000 tokens，不计算缓存折扣；实际支出以 API usage 为准。

| Phase | Train / test tasks | Production calls | Judge calls | Conservative estimate |
|---|---:|---:|---:|---:|
| dry-run | 0 / 1 | 56 | 5 | $1.95 |
| pilot | 5 / 5 | 455 | 35 | $15.40 |
| final | 10 / 10 | 910 | 70 | $30.80 |

同一 dry run 使用方舟池时，生产调用按最贵候选 `deepseek-v4-pro` 的 5.5 系数估算，
judge 按 `kimi-k3` 的 10 系数估算：生产 160.16 AFP、评审 46 AFP，总计
206.16 AFP。建议调用上限分别为 200 AFP 和 60 AFP。DSH 原生工具调用的外层 agent
不进入这两本 benchmark 账；固定使用 `deepseek-v4-flash`，另设 5 AFP 运行上限，因此一次
完整执行的批准上限为 265 AFP。

付费 dry run 必须同时显式提供开关和两类预算上限：

```bash
export OPENAI_API_KEY="..."
uv run python experiments/run_real_v0_1.py \
  --phase dry-run \
  --execute-paid-run \
  --max-production-cost 2 \
  --max-evaluation-cost 1 \
  --output-dir reports/v0.1-real/dry-run
```

密钥只从 manifest 指定的环境变量读取，不写入任务、run record 或 DSH evidence。
runner 记录 input/output/cache/reasoning tokens、实际成本、端到端与关键路径延迟、
重试、finish reason、request ID 和标准化 failure type。超过预算后不会继续发起新调用。
默认执行策略固定为 temperature 0、单次 120 秒超时、最多重试 2 次；preflight 会把这些
参数写入记录，也可通过 `--timeout-seconds` 与 `--max-retries` 显式覆盖。聚合结果包含
质量、生产成本与关键路径延迟的均值/标准差，以及成本和延迟的 p50/p95；需要观察同一
任务的运行波动时，用 `--repeats 3`（或更高）执行，但调用量和预算会同比增加。

Agent Plan 支持 OpenAI 兼容的 Chat API 与 Responses API。RefractRouter 使用前者；AFP
manifest 和 DSH 插件共同拒绝普通方舟 `/api/v3`，只允许
`https://ark.cn-beijing.volces.com/api/plan/v3`。DSH 凭证服务在每次获批的付费操作中解析
Agent Plan 专属 Key，并只交给受控且诊断输出会脱敏的 benchmark 子进程。冻结 manifest
显式关闭 thinking，避免推理 tokens 占用结构化正文的 1,200-token 上限。配置与零费用验证
步骤见
`validation/dsh/plugin/README.md` 和 `reports/v0.1/issue-4-agent-plan-preflight.md`。

独立 judge 使用 `data/judges/v0.1.md` 的固定 rubric。需求覆盖、证据准确性和 HTML
有效性分别取确定性检查与 judge 的较低值；source trace 失败时证据分直接归零。
生产成本和 judge 评测成本分别统计，Pareto 主比较只使用生产成本。
真实阶段会生成 `baseline-table.md`、`pareto-front.md`、`oracle-gap.md`、
`failure-taxonomy.md`、逐策略 run record 和带哈希的 `evidence-index.json`。

final phase 即使模型和 judge 全部成功，也只会标记为 `awaiting-human-audit`。复制
`data/judges/human-audit-template-v0.1.json`、填写冻结的两项任务及两种 oracle 策略后，
运行以下命令；人工分与 judge 分差距超过 10 分时，最终结论强制为 No-go：

```bash
uv run python experiments/finalize_real_v0_1.py \
  --output-dir reports/v0.1-real/final \
  --audit /path/to/completed-human-audit.json
```

## v0.1 Scope

固定工作域为一般文书办公中的深度调研报告生成：

```text
parse_requirements
  -> build_outline
  -> extract_evidence
  -> synthesize_analysis
  -> write_report
  -> render_html
  -> verify_report
```

Canonical task 是 `data/tasks/report_001.json`，主题为“2026 年企业 LLM Agent 平台选型”。输入使用 `data/source_packs/report_001/` 下的固定 source pack，输出必须是可离线打开的 standalone HTML。

完整数据集定义在 `data/benchmarks/v0.1.json`。`report_001` 保留为 canonical task；
`report_002` 至 `report_020` 是明确标注的合成 benchmark brief，不代表现实供应商事实。
每个任务包含 8 份独立 source pack，训练集与测试集按 task ID 隔离。

## Architecture Boundary

### DeepAgents / LangGraph

`DeepAgentsGraphExecutor` 使用 DeepAgents 0.7 作为宿主运行时，并通过一个确定性工具调用执行固定 DAG。v0.1 不启用 DeepAgents 的自动规划、动态拆解或自主 sub-agent 生成；图结构和节点顺序由 `TaskDAG` 冻结。

### RefractRouter Core

核心代码位于 `src/refractrouter/`，负责：

- Task DAG schema 与模型注册表。
- 节点执行、上下文传递、拓扑排序。
- 路由策略、节点评分、任务评分。
- 成本与关键路径延迟统计。

### DSH

DeepSeek Harness 作为外层验证环境，负责组合、工具调度、模型 provider、进程生命周期、
sandbox、凭证解析和证据捕获；不参与模型选择，也不替换 DeepAgents/LangGraph 主执行循环。
`validation/dsh/plugin/` 是可由 `dsh plugin` 安装的 bundle，向 Cordis 树贡献
`refractrouter_validate` 工具。插件通过 DSH 原生 service 运行固定 argv，并把 Python
runner 的证据投影为结构化结果。Agent Plan benchmark 请求由受控 Python runner 直接调用
专属 `/api/plan/v3/chat/completions`；外层 DSH agent 仍使用 `ark-plan` provider。评分、hash
与 gate 仍只有 Python runner 一份实现。

v0.1 固定支持 DSH `0.1.1-rc.2`、Node `>=22.19.0 <23` 和 pnpm `10.15.0`，并在 CI 中
验证 Node `22.19.0` 与最新 Node 22。插件暂按仓库路径或指定 commit 生成的 tarball 分发，
不发布 registry package。安装、故障诊断、升级和回滚步骤见
`validation/dsh/plugin/README.md`。

真实阶段由插件调用 `validation/dsh/real_runner.py`。bundle 默认
`allowPaidRuns: false`；付费执行必须由更高优先级的 profile patch 开启，并同时通过部署级
与调用级两层生产/评审预算上限。直接 HTTP manifest 的凭证仅显式交给受控子进程；
Agent Plan 还要求精确的专属 base URL。凭证不会出现在工具结果、请求进度或 evidence 中。

## Current Dry Run

最新 fake-model 结果见 `reports/v0.1/baseline-table.md`：

| Strategy | Task score | Cost (USD) | Critical path (ms) |
|---|---:|---:|---:|
| `weak-all` | 79.762 | 0.006200 | 10574 |
| `strong-all` | 100.000 | 0.100416 | 4036 |
| `node-type-rule` | 83.333 | 0.039113 | 7241 |
| `task-oracle` | 100.000 | 0.100416 | 4036 |
| `node-oracle` | 100.000 | 0.025152 | 9316 |

解读：

- `node-oracle` 与 `task-oracle` 达到相同 100 分。
- `node-oracle` 成本降低 74.95%。
- `node-oracle` 关键路径延迟为 `task-oracle` 的 2.31 倍。
- 按 v0.1 的三目标 Go/No-Go 规则，本轮为 **No-go**：质量-成本优势明确，但未满足延迟不超过 120% 的条件。

证据分只统计最终 HTML 中能够回链到 source pack 的唯一来源。中间节点中的
`source_id`、不存在的来源以及缺少来源索引的引用不会得到证据分。当前结果仍由
fake adapter 生成，只用于验证实验链路与评分约束，不代表真实模型质量。

完整分析见 `reports/v0.1/oracle-gap.md` 和 `reports/v0.1/pareto-front.md`。
真实 DSH headless 复核结果及稳定 artifact hash 见
`reports/v0.1/dsh-validation.md`。

## Repository Layout

```text
src/refractrouter/       Core executor, routing, scoring, metrics, and CLI
tests/                   Unit tests
data/schema/             Task DAG and run-record JSON schemas
data/tasks/              Canonical task definitions
data/source_packs/       Frozen source packs
data/benchmarks/         Train/test/pilot and human-audit split
data/model-manifests/    Frozen provider, model snapshot, price, and key-env configuration
data/judges/             Versioned independent-judge rubric
experiments/             v0.1 experiment runner
validation/dsh/          DSH bundle, Cordis tool, boundary, and runner contracts
reports/v0.1/            Generated baseline, Pareto, oracle gap, and run records
```

## Roadmap

1. 使用关闭 thinking 的冻结 manifest 重跑 1-task paid dry run，并复核 judge 覆盖、source
   trace、实际 AFP、失败率和证据哈希。
2. dry run 通过后执行 10-task pilot，并复核实际 token、成本、失败率与 p95 延迟。
3. 对预先冻结的 10% 样本完成人工抽检，并与独立 judge 结果对照。
4. pilot 通过后执行 20-task final benchmark，并通过 DSH plugin tool call 复核。
5. 汇总 DSH evidence，发布最终 Pareto、failure taxonomy 与 Go/No-Go 结论。

## Wiki

研究档案、文献笔记、会议纪要和架构讨论位于 [RefractRouter Wiki](https://github.com/AEALab/RefractRouter/wiki)。
