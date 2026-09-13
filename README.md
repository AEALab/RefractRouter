# Refract Agent（析衡）

> 析构知难，衡派选优 — Refract the task, spend every token where it matters.

RefractRouter 是面向团队集中路由的应用项目。RefractAgent 提供本机任务入口，按质量、成本和时延偏好选择模型，支持整任务处理及 DAG 节点分配，并保存结果与费用。

## 安装与启动

**首次使用请按 [Wiki：安装与启动指南](https://github.com/AEALab/RefractRouter/wiki/安装与启动指南) 操作**，
也可阅读 [仓库内同版文档](docs/refractagent-local-quickstart.md)。
指南从环境准备、构建安装包开始，完整覆盖 DSH 插件安装、provider 与模型配置、
模拟演示、真实任务、日常重启及常见故障。

1. 安装 Python 核心 `refractrouter` 和 DSH 插件。
2. 在固定工作目录生成配置，先用模拟任务确认安装成功。
3. 配置自己的 providers、models 与凭证，启用真实执行并启动 DSH。
4. 在 DSH 选择 RefractAgent 的省成本、均衡或质量优先，输入文本任务。

Ark Agent Plan 是可选 provider，也可直连 Chat Completions、OpenAI Responses 推理接口，
或复用 DSH 已配置的模型。每个 DAG 节点可联合选择物理模型与 `reasoning effort`，
依据该候选在节点类型、难度和风险下的质量、成本及时延预测进行分配。
字段与示例见 [自定义 providers 与 models](docs/provider-configuration.md)。

**当前运行方式：DSH 按请求启动本机 Python 核心，无需单独启动 Router HTTP 服务。**
`refractagent` 是应用命令；DSH 提供网页和会话入口。团队集中后端仍在后续开发范围内。

完成指南中的安装与真实模式配置、设置 Key 后，日常启动命令为：

```bash
export DSH_HOME="$HOME/.local/share/refractagent/dsh"
cd "$HOME/RefractAgentWorkspace"
dsh --profile web --patch ./refractagent-live.json \
  --host 127.0.0.1 --port 53611
```

访问 [本机 DSH 页面](http://127.0.0.1:53611/)。如安装时沿用原 DSH 配置，启动时也沿用
同一 `DSH_HOME`。默认演示结果带 `[SIMULATED]`；启用真实配置后需发送新的 Query。
当前支持文本分析与生成；RefractAgent 模型入口暂不执行 DSH 工具或生成图片、视频。
本机三策略已通过 6 次真实调用验收，证据及已知长度控制限制见
[应用验收记录](reports/refractagent-local/20260908/README.md)。

## 核心与 DSH 插件的定位

本项目保留单仓库。**Router 是核心，DSH 插件是验证与接入核心的宿主适配层**。
插件用于验证任务拆分、节点选模与组合执行的可行性；未来也可以通过
“DSH + 插件连接核心 Router”提供实际任务入口，这是本项目产品化的实现形态之一。

| 部分 | 目录 | 职责 |
|---|---|---|
| Router 核心与任务运行时 | `src/refractrouter/` | DAG 规划与校验、节点选模、执行、预算记账与评估 |
| 实验与证据 | `experiments/`、`data/`、`reports/` | 冻结任务、对照实验与质量、成本、时延证据 |
| DSH 插件 | `validation/dsh/plugin/` | 工具入口、宿主配置、凭证与进程对接、结构化结果展示 |
| DSH 验证与调用入口 | `validation/dsh/` 下的 Python runner | 连接插件与核心、组织验证并保存证据 |

RefractAgent 模型入口使用已安装的 Python 核心，脱离源码目录的安装和执行已通过验收。
历史验证工具继续需要匹配的源码环境；团队集中 Router 服务留待后续阶段。
本机应用验收不代表跨任务路由收益已获验证。
完整边界见 [架构说明](docs/architecture.md) 和 [DSH 集成说明](validation/dsh/README.md)。

## 研究与验证记录

当前 [三类任务质量协议](docs/quality-study-protocol.md)提供候选材料、三态质量检查、
开发正负例校准，以及[实际路线与统计绑定](docs/quality-study-freeze.md)。
[非真人条件验证](reports/quality-study-v1/technical-freeze-analysis.md)已完成，
独立真人材料审查、盲审与用途确认仍待完成；尚未证明 Pareto 收益。

[#53 时间与 AFP 开发对照](reports/pareto-development-v1/README.md)接续该协议，
在六个开发任务上比较直接回答、整任务选模、共享图串行/并行和自动图执行。
逐调用费用、端到端时间与质量状态分别审计；开发资源点不等于质量合格的 Pareto 前沿。

[自动拆分应用入口](docs/automatic-dag.md)支持 `refractagent run --template auto`：
快速规划模型输出短计划，Python 编译契约并并行执行；困难节点可进行一次有界再拆。
排程材料中的显式错误依赖由确定性检查拦截，检查范围和未覆盖内容分别记录。
[旧验收](reports/automatic-dag/README.md)保留原始误判；
[快速规划与动态执行验收](reports/fast-dynamic-dag/README.md)记录新验证，不代表已经证明整体收益。

2026-09-10 的 [#39/#40 联合实测](reports/dag-decomposition/joint-39-40-v1-analysis/结项评估.md)
已完成 430 次真实调用与 104 个预定条件，消耗 1085.01 AFP，账本及文件审计通过。
现有配置未验证综合收益；自动计划虽有语义审查通过者，但没有执行节点。
#40 的真人复核仍待完成，研究结项与产品能力通过分别判断。

新的 [K3 整任务基线对照](docs/k3-baseline-comparison.md)已实现零调用预检、
独立评审交接及成本约束选模：Kimi-K3 一次完成任务，对比七节点 DAG 的达标最低费用路线。
参考路线和探针计入首次使用费用；单轮不自动 Go，当前尚未完成该真实对照。
模拟验证不能证明质量或节省收益。
[GLM-5.3 两样本真实校准](reports/v0.5-glm-calibration/paid-admission-1/README.md)现已通过：
缺乏比较的报告 28 分、内容较完整的报告 91 分，两次共 8.68545 AFP；
该结果仅用于评审准入，不代表生产对照完成。

2026-09-08 的 [K3 准备阶段](reports/v0.5-k3-prepare-admission/README.md)因基线请求在
120 秒超时而停止：发起 7 次生产请求，5 次正常返回；已知费用 4.98315 AFP，另两次
请求费用未知。未形成完整对照。已离线修复基线失败后仍继续参考路线的问题，198 项测试通过。

v0.1 已进入可运行原型阶段。当前实现包含：

- 固定 7 节点报告生成 DAG、冻结 source pack 与离线 fake model adapter。
- `weak-all`、`strong-all`、`node-type-rule`、`task-oracle`、`node-oracle` 基线策略。
- DeepAgents 0.7 宿主运行时与 LangGraph 执行底座。
- 可追溯的最终 HTML 引用、确定性评分、baseline 表、Pareto 表和 oracle gap 报告。
- 可安装的 DSH bundle、结构化验证工具与确定性 runner；已在隔离 profile 通过真实 DSH
  headless tool call 验证。
- 20-task 合成 benchmark（train/test 各 10 个）、USD/AFP 真实模型 manifest、
  OpenAI-compatible 与 DSH LLM adapter、真实 token/成本/延迟遥测、独立 judge 与预算保护。

issue #19 的修复已通过真实 Agent Plan dry run：61/61 个请求完成、无截断或失败，
五个策略成功率与 judge 覆盖均为 100%，DSH 返回 `pass`。生产与评审合计 47.59695 AFP。
证据见 `reports/v0.1-real/dry-run-agent-plan-8192/`；旧失败证据仍保留。

此前单任务路由收益判定为 No-go：node-oracle 84 分、task-oracle 100 分，成本几乎相同。
两者实际都选择 7 节点全用 Flash，报告来自不同生成调用，因此分差不能归因于模型分配差异。
这不影响此前 dry run 完整性验收通过。旧报告保留历史判定。

issue #22 已补齐独立节点评审、三模型矩阵、配对比较，并完成获批的真实三轮运行：
215/215 请求正常返回，63 格矩阵和 9 份单模型结果全部保存。Flash、全 Pro、固定混合的
最终平均质量分别为 88.333、88.333、86.667。M3 的中间 JSON 契约失败及组合输出缺失
证据字段导致 oracle 最终评审不完整，因此判定为 **Insufficient-evidence**。
未评审的备用分数在核对版汇总中显示 N/A。
旧结果见 [v0.2 三轮复验证据](reports/v0.2-node-quality/repeated-agent-plan/README.md)。

2026-09-07 在契约修复后完成新三轮复验：237/237 请求正常结束，63 格矩阵全部保存，
62 格有效，九份单模型报告全部获得独立评分。第二、三轮 node-oracle 组成了不同的混合
路线；相对全 Pro 的配对平均质量高 7.5 分、成本低 3.734175 AFP，但相对当轮最佳单模型
质量低 4.5 分、成本高 2.598275 AFP。首轮因一个 Flash 分析候选缺少证据而被冻结选择规则
跳过，因此完整三轮判定仍为 **Insufficient-evidence**，未启动 pilot。
详见 [v0.3 三轮复验报告](reports/v0.3-contract-recovery/repeated-agent-plan/README.md)。
[issue #29](https://github.com/AEALab/RefractRouter/issues/29) 记录候选拒绝与缺失评估的规则问题；
issue #22 继续跟踪完整对照，issue #5 等待有效证据。

issue #29 的统计口径修复现已实现：质量、生产成本和关键路径延迟使用相同的成功且独立
评审轮次，报告列出纳入／排除集合；全量费用与覆盖率另报。节点矩阵另列记录完整性、
评估可用性、候选资格及路线可执行／已执行状态。冻结选择策略仍为
`all-candidates-required-v1`；用户已确认的新策略 `exclude-known-contract-rejections-v2` 可显式启用。
v2 保留已知契约拒绝并选择其他合格候选，缺评估、无效上游或无合格候选仍阻断。
DSH 工具参数为 `selectionPolicy`，Python 参数为 `--selection-policy`。
[v2 单轮真实准入](reports/v0.4-known-rejections/admission-agent-plan/README.md)已完成：DSH pass，
82/82 请求正常，21 格矩阵与所有最终评审完整，总计 143.6703 AFP。混合路线 89 分，
本轮最佳单模型 Pro 96 分；仍为单轮 Insufficient-evidence，未启动 pilot。
[独立离线复核与后续计划](reports/v0.4-cohort-review/README.md)保留历史证据不变，
确认 node-oracle 两个有效轮次平均质量 91.5、平均成本 5.365025 AFP，仍无完整 Go 证据。

[v2 全新三轮对照](reports/v0.4-known-rejections/repeated-agent-plan/README.md)已执行：
242/242 实际请求正常返回，63 格矩阵全部独立评审，三轮混合路线得分 94、90、92。
第三轮 Flash 单模型分析输出遗漏 `evidence`，导致三个下游请求及一次最终评审未执行，
最佳单模型对照仅前两轮有效。有效配对中混合路线质量低 2.5 分、成本高 1.985325 AFP；
完整性与收益判定仍为 **Insufficient-evidence**，#22 继续开放，#5 pilot 未启动。
[失败诊断](reports/v0.4-known-rejections/repeated-agent-plan/failure-diagnosis.json)确认上游证据
存在，拒绝符合冻结契约；下一步先离线评估证据保留及完整路线失败的比较规则。

复核工具现在要求历史证据目录之外的全新输出目录：

```bash
uv run python experiments/review_node_quality_evidence.py \
  reports/v0.3-contract-recovery/repeated-agent-plan \
  --output-dir /tmp/refractrouter-cohort-review
```

现已补充 **C → A → B 三指标单模型离线选模**：先展示已有数据的质量、AFP 成本和
关键路径 p95 取舍，再使用显式约束选成本最低者（A），或使用显式权重排序（B，支持
叠加硬约束）。质量最高固定单模型与综合选择分别报告；无可行候选明确返回无解。
参见 [选模规则](reports/model-selection/selection-rules.md) 和
[v0.3 数据敏感性分析](reports/model-selection/v0.3-analysis/selection-analysis.md)。
本次为同一任务三次重复的样本内分析，新增入口不发起模型调用。

使用新的输出目录重现示例，三个权重依次为质量、成本、时延：

```bash
uv run python -m experiments.analyze_model_selection \
  reports/v0.3-contract-recovery/repeated-agent-plan \
  --output-dir /tmp/refractrouter-model-selection \
  --quality-min 88 --cost-afp-max 6 --latency-p95-ms-max 80000 \
  --weights 0.5 0.25 0.25
```

阈值与权重均须显式提供，示例不代表生产默认要求。A/B 选择函数可通过
`refractrouter.model_selection.select_model` 调用；旧版冻结报告付费 runner 尚未接入这套离线规则；文本任务入口使用下述节点路由。

## 文本任务入口

插件 0.7.0 提供 `refractrouter_task`：接收任务描述，通过模型规划并校验最多 8 节点的 DAG，
按节点质量预测、总成本和调度时延约束选择模型组合，再执行并独立评估最终答案。
支持 A 约束式和 B 显式加权式；无可行路线时明确返回失败。

`preflight` 使用标注的单节点预览，`demo` 使用模拟输出；`plan` 和 `run` 才会调用真实模型，
须启用部署开关并提供两项预算。当前为文本生成能力，不执行节点中的浏览器、Shell 或外部
工具动作。附带的真实路由 profile 来源于单个报告任务，只是迁移预测，不能保证任意任务质量。
使用方式、DAG 格式、预算和示例见 [文本任务与节点路由](docs/text-task-routing.md)。

按照 Issue #32，模型规划现使用 `text-task-plan-v2`：解释拆分理由、声明每条依赖消费的
字段、节点输出契约、能力需求和验收覆盖。简单任务可不拆分，独立分支会显示为并行机会；
默认串行，可配置最多 8 个并发节点及 provider 限制。核心会拦截非法交接并保留原文和费用，支持用 `acceptanceCriteria`
固定验收条件。详见 [DAG 拆分机制与离线示例](docs/dag-decomposition.md)。

分层 profile、校准/测试隔离和六组冻结对照已提供离线入口；真实收益仍待授权实验。
实验任务、验收阈值及完整费用预检见 [多任务对照协议](docs/dag-study.md)。

## Ark Agent Plan 模型清单

[官方模型清单的 2026-09-07 快照](docs/ark-agent-plan-model-catalog.md)记录 19 个模型，覆盖
文本、向量化、图片、视频、语音合成与识别，包括 GLM-5.3、GLM-5.3-Flash、Kimi-K2.7-Code
和 Doubao 系列。清单保存套餐档位、长度上限、AFP 计费单位、限时折扣和接入状态，
可按能力及套餐筛选。它不改变已冻结的四模型实验 manifest，也不自动发起模型调用。

```bash
uv run python -m refractrouter.model_catalog
uv run python -m refractrouter.model_catalog --capability text-generation --plan-tier large --json
```

## 开发与实验验证（可选）

以下命令用于开发和历史实验验证。普通用户安装与运行应用请使用顶部的安装指南。

```bash
uv sync --frozen --extra dev --extra deepagents
npm ci --prefix validation/dsh/plugin
npm run --prefix validation/dsh/plugin typecheck
npm run --prefix validation/dsh/plugin build
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

- `uv sync --frozen --extra dev --extra deepagents`：安装测试依赖与 DeepAgents/LangGraph。
- `npm ci --prefix validation/dsh/plugin`：安装锁定的 TypeScript 开发工具。
- `npm run --prefix validation/dsh/plugin typecheck` / `build`：严格类型检查和构建插件。
- `uv run pytest`：运行 Python 全套测试及编译后的 TypeScript DSH 契约测试。
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

三阶段默认调用量和保守成本估算如下。估算假设每个生产调用 4,000 input / 8,192
output tokens、judge input 8,000 tokens，不计算缓存折扣；实际支出以 API usage 为准。

| Phase | Train / test tasks | Production calls | Judge calls | Conservative estimate |
|---|---:|---:|---:|---:|
| dry-run | 0 / 1 | 56 | 21 节点 + 5 最终 | $11.86 |
| pilot | 5 / 5 | 455 | 210 节点 + 35 最终 | $107.91 |
| final | 10 / 10 | 910 | 420 节点 + 70 最终 | $215.82 |

生产预算将已知的单模型和探测遍历按各自模型价格计算，其余待选路调用按最贵单次
请求计算；输入/输出 token 假设不变。同一轮方舟 dry run 估算生产 238.96 AFP、
评审 420.99 AFP，共 659.96 AFP（总额使用未舍入值计算）。
三轮重复为 168 次生产、63 次节点评审、15 次最终评审，最多 246 次调用；估算生产
716.89 AFP、评审 1262.98 AFP，总计 1979.87 AFP。训练集只执行一次，不随测试轮数重复。
旧归档中的“全部生产调用按最贵模型计算”估算仍作为历史记录保留。

issue #22 的三轮复验已获得 2505 AFP 总预算批准并执行。修复过程中在总额内调整了
生产/评审预留；截至 v0.3 三轮复验，含初次中断、七样本重放与 DSH 外层调用，已知费用为
807.33615 AFP，另保留一笔中断请求的 16.192 AFP 未结算估计。合计占用 823.52815 AFP，
剩余 1681.47185 AFP；明细见 [预算记录](reports/v0.3-contract-recovery/repeated-agent-plan/cost-accounting.json)。
此次授权不自动扩展到后续 pilot。预算检查在每次调用前进行；输入 token 数仍是估算假设，
单次请求结算可能超出预留，所以这些上限不能保证请求内精确硬停。

后续用户批准总额增至 **3000 AFP**，其中 v2 全新三轮额度为生产 730、评审 1270、
外层 0.5 AFP。该轮实际用量 **376.10695 AFP**，含单轮准入等历史用量后的累计已知费用
为 1327.1134 AFP；保留旧未结算 16.192 AFP 后尚余 **1656.6946 AFP**。
参见 [最新账本](reports/v0.4-known-rejections/repeated-agent-plan/cost-accounting.json)。
付费 profile 已关闭，没有自动重跑或启动 pilot。

零费用三轮预检命令：

```bash
uv run python experiments/run_real_v0_1.py \
  --phase dry-run --repeats 3 --max-retries 0 \
  --manifest data/model-manifests/volcengine-agent-plan.json \
  --output-dir /tmp/refractrouter-node-quality-preflight
```

实际运行必须使用获批范围内的 `--execute-paid-run --max-production-cost ...
--max-evaluation-cost ...`，并使用新的输出目录；已有矩阵证据的目录禁止重复写入。

密钥只从 manifest 指定的环境变量读取，不写入任务、run record 或 DSH evidence。
runner 记录 input/output/cache/reasoning tokens、实际成本、端到端与关键路径延迟、
重试、finish reason、request ID 和标准化 failure type。超过预算后不会继续发起新调用。
默认执行策略固定为 temperature 0、单次 120 秒超时、最多重试 2 次；preflight 会把这些
参数写入记录，也可通过 `--timeout-seconds` 与 `--max-retries` 显式覆盖。聚合结果包含
质量、生产成本与关键路径延迟的均值/标准差，以及成本和延迟的 p50/p95；需要观察同一
任务的运行波动时，用 `--repeats 3`（或更高）执行，但调用量和预算会同比增加。

issue #25 的恢复入口为 `contract-replay`，只重放归档中的 7 个失败写作节点，复用原始
上游并核验哈希。默认零调用，最多三次重放、不重试，遇到第一个契约失败即停止。
它验证输出格式与证据传递，不产生语义质量分或 Go 结论：

```bash
uv run python experiments/replay_node_contracts.py --output-dir /tmp/refractrouter-contract-preflight
```

真实重放由 DSH 的 `refractrouter_validate` 工具使用 `phase: "contract-replay"` 执行，
沿用 Agent Plan 专属端点、部署级开关及生产/评审双预算限制。M3 的 manifest 使用
`json_mode_strategy: "prompt-only"`；其他模型保留 `json-object-hint`。这些都是调用策略，
不代表服务端已保证 schema。节点提示协议 v0.3 明确区分中间 JSON 和最终 HTML，
preflight 记录 schema 哈希及各模型 JSON 策略。

Agent Plan 支持 OpenAI 兼容的 Chat API 与 Responses API。RefractRouter 使用前者；AFP
manifest 和 DSH 插件共同拒绝普通方舟 `/api/v3`，只允许
`https://ark.cn-beijing.volces.com/api/plan/v3`。DSH 凭证服务在每次获批的付费操作中解析
Agent Plan 专属 Key，并只交给受控且诊断输出会脱敏的 benchmark 子进程。冻结 manifest
显式关闭 thinking，避免推理 tokens 占用结构化正文的 8,192-token 上限。配置与零费用验证
步骤见
`validation/dsh/plugin/README.md` 和 `reports/v0.1/issue-4-agent-plan-preflight.md`。

最终报告 judge 使用 v0.1 固定 rubric（说明见 `data/judges/v0.1.md`）。需求覆盖、证据准确性和 HTML
有效性分别取确定性检查与 judge 的较低值；source trace 失败时证据分直接归零。
生产成本和 judge 评测成本分别统计，Pareto 主比较只使用生产成本。
真实阶段会生成 `baseline-table.md`、`pareto-front.md`、`oracle-gap.md`、
`failure-taxonomy.md`、逐策略 run record 和带哈希的 `evidence-index.json`。

节点评审使用 `data/judges/node-v0.2.md`：确定性检查仅限制分数上限，独立 judge 从正确性、
证据支持、完整性、下游可用性评估内容，且不接收候选名称、价格或能力等级。引用次数、
英文关键词和合法 JSON 本身不代表语义质量。验证节点按上游 HTML 的实际情况检查结论。
每轮用 strong-all 的固定直接上游输入分别探测三模型，按语义分最高、实际节点成本最低
选择，再重新执行组合后的完整 DAG。该 node-oracle 是局部贪心选择，无法证明全局最优。

每个 task/repeat 保存 `node-quality-matrix.json` 和 `.md` 的 7×3 矩阵，包含原文、输入与
输出哈希、成本与延迟、评分维度和理由、资格与选择结果。`node-evaluations.ndjson` 逐格
落盘，记录选择前状态；最终选择以矩阵 JSON 为准。`single-models/` 保存三个模型每轮的
完整结果和最终 judge 记录，包括没有被任何基线复用的中间价位模型。
评审失败、候选调用失败或缺少有效候选时不生成 node-oracle 路由，不静默退回最便宜模型。

`strategy-comparisons.json` 和 `.md` 按 task/repeat 配对，将 node-oracle、node-type-rule
分别对照 strong-all、task-oracle。task-oracle 是每组中经过最终评审的最佳单模型，允许
选择便宜模型；strong-all 才是全贵模型。报告给出逐轮质量、成本、延迟差及均值/标准差，
并报告每个任务内部的重复波动。相同模型分配的分差不能作为路由改变带来的收益。
少于三轮、证据不完整或两种 oracle 始终采用相同分配时，判定为 `Insufficient-evidence`。
三轮只提供描述性波动观察，不构成跨任务泛化或统计显著性的证明。


final phase 即使模型和 judge 全部成功，也只会标记为 `awaiting-human-audit`。
先从冻结产物生成绑定索引与运行哈希的 v0.2 人工审核模板：

```bash
uv run python experiments/finalize_real_v0_1.py \
  --output-dir reports/v0.1-real/final \
  --prepare-audit --result-dir /tmp/refractrouter-human-audit-template
```

人工填写四个样本的维度分、总分、逐条主张核对、原文依据、理由、审核者及带时区的时间。
使用新目录保存审核结果；历史 v0.1 空白模板保留作历史记录，不再用于最终确认。
人工分与 judge 分差超过固定的 10 分，或审核发现严重事实错误时，审核不通过。
oracle 证据不足时，最终状态保留 `incomplete`：

```bash
uv run python experiments/finalize_real_v0_1.py \
  --output-dir reports/v0.1-real/final \
  --audit /path/to/completed-human-audit.json \
  --result-dir /tmp/refractrouter-human-audit-result
```

原始 benchmark 不作修改。审核流程和七项 Issue 的依赖见
[历史基准验证交接](docs/benchmark-validation-handoff.md)。

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

## 架构边界

实现语言限定为 **Python + TypeScript**（[issue #28](https://github.com/AEALab/RefractRouter/issues/28)）。
Python 负责 DAG、节点执行与模型分配、策略、评分评测、数据集、适配器、成本/时延统计和
实验 runner；TypeScript 负责 DSH 插件入口、配置与工具类型、宿主服务、进程与凭据边界、
结构化结果及该层契约测试。新增实现语言或跨层复制业务逻辑须先记录架构提案，并在合并前
取得维护者批准。完整职责、构建产物及评审要求见 [架构说明](docs/architecture.md)。

插件源码位于 `validation/dsh/plugin/src/`，严格类型检查后编译到 `dist/`；包入口为
`dist/index.js`，契约测试位于 `validation/dsh/plugin/tests/`。编译生成的 JavaScript
仅作为运行产物，禁止新增手写 JavaScript 实现。安装 checkout 插件前需执行上述构建命令。

### DeepAgents / LangGraph

`DeepAgentsGraphExecutor` 使用 DeepAgents 0.7 作为宿主运行时，并通过一个确定性工具调用执行固定 DAG。v0.1 不启用 DeepAgents 的自动规划、动态拆解或自主 sub-agent 生成；图结构和节点顺序由 `TaskDAG` 冻结。

### RefractRouter Core

核心代码位于 `src/refractrouter/`，负责：

- Task DAG schema 与模型注册表。
- 节点执行、上下文传递、拓扑排序。
- 路由策略、节点评分、任务评分。
- 成本与关键路径延迟统计。

### DSH 验证与产品接入

DeepSeek Harness 提供外层宿主环境，负责组合、工具调度、模型 provider、进程生命周期、
sandbox、凭证解析和会话证据。Router 核心负责 DAG 节点的模型选择与执行。
`validation/dsh/plugin/` 是可由 `dsh plugin` 安装的 bundle，向 Cordis 树贡献
`refractrouter_validate` 验证工具和 `refractrouter_task` 文本任务工具。
前者组织冻结基准验证，后者探索实际任务的产品入口；两者调用同一项目的 Python 核心能力。
插件通过 DSH 原生 service 运行固定 argv，并把 Python
runner 的证据投影为结构化结果。Agent Plan benchmark 请求由受控 Python runner 直接调用
专属 `/api/plan/v3/chat/completions`；外层 DSH agent 仍使用 `ark-plan` provider。评分、hash
与 gate 仍只有 Python runner 一份实现。

v0.1 固定支持 DSH `0.1.1-rc.2`、Node `>=22.19.0 <23` 和 pnpm `10.15.0`，并在 CI 中
验证 Node `22.19.0` 与最新 Node 22。插件暂按仓库路径或指定 commit 生成的 tarball 分发，
不发布 registry package。安装、故障诊断、升级和回滚步骤见
`validation/dsh/plugin/README.md`。

基准实验由插件调用 `validation/dsh/real_runner.py`，文本任务调用
`validation/dsh/task_runner.py`。bundle 默认
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

1. issue #4 的失败证据已保留，issue #19 修复已通过新的 1-task 真实准入验证。
2. issue #25 修复中间输出契约并恢复完整 oracle 对照后，为 issue #5 的 10-task pilot
   核定独立预算，再评估多任务与重复运行差异。
3. pilot 通过后，对冻结样本完成人工抽检，并与独立 judge 结果对照。
4. 执行 20-task final benchmark，通过 DSH plugin tool call 复核并发布最终结论。

## Wiki

研究档案、文献笔记、会议纪要和架构讨论位于 [RefractRouter Wiki](https://github.com/AEALab/RefractRouter/wiki)。
