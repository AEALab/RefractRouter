# 变更日志

## 0.14.1

- 将省成本、均衡、质量优先分为独立区块，增加标题分隔线、内边距和区块间距。

## 0.14.0

- 引入 2026-09-12 核对的完整 Ark 文字模型清单，替换 DSH 设置预设中的三个实验候选。
- 新增六档 AFP 成本上限，与推理强度分离；Python 实际过滤候选并校验空集。
- 显示模型官方输入／输出系数和套餐范围，保留 GLM-5.3 的思考约束。
- 需要 Python 核心 0.4.1；历史实验 manifest 和报告保持不变。


## 0.13.2

- 将模式下的内部模型 ID 文本输入改为真实模型名称勾选列表。
- 解释三种模式的选择偏好，以及勾选限制范围、不勾选使用全部候选模型的含义。
- 排除评审模型，区分同名模型并提示已移除的配置引用。


## 0.13.1

- 对齐官方插件卡片的标题、说明、折叠箭头、主题色与保存按钮。
- 将 Ark 预设展开为可编辑配置，保留凭证引用；未编辑时仍使用原预设。
- 修复未完成 JSON 被宿主刷新覆盖、无法放弃及多行模型输入换行丢失。
- 为推理强度、候选模型和完整 JSON 提供示例与明确标签。


## 0.13.0

- 新增 DSH 浏览器半边，在「设置 → 插件 → 插件配置」显示「RefractAgent 路由」卡片。
- 通过 `refractagent` settings namespace 编辑 provider/model 配置、全局与三模式
  reasoning effort、三模式候选模型池，以及预算和上下文限制开关。
- 设置使用 DSH 用户层持久化并热加载；保存失败保留草稿，重置清除用户覆盖并恢复部署值。
- 浏览器 bundle 按 DSH lazy-CJS factory 格式构建，发布包继续保持零运行时 npm 依赖。

## 0.12.0

- `providerConfig` 新增 `defaultReasoningEffort` 与 `strategies`，支持按省成本／均衡／
  质量优先三种模式配置默认推理档位与候选模型池；模型显式档位优先于模式与全局默认。
- 插件配置新增 `limits` 开关：`relaxBudget` 放开预算拦截但保留逐次记账，
  `relaxContext` 将对话上下文上限放宽到 1000000 字节并同步放宽节点输入预算定尺上限。
- 运行记录与结果保存 `limits` 实际状态；配合 Python 核心 0.4.0。
- 增加显式可选的 `outputConstraints` 透传，无默认字数限制。
- Python 核心检查最终正文长度；DSH 分别展示生成、语义评审和长度检查状态并保存回放。
- 原始答案、评审与用量保留；超限不自动截断、修复或换模型。

## 0.11.0

- 增加 OpenAI Responses 协议、推理参数和独立用量明细，正确结算无正文截断响应。

- 支持用户配置 providers 与 models，Ark Agent Plan 改为显式可选预设。
- 复用 DSH 原生 provider 和凭证，或按 provider 解析直接 HTTP 凭证。
- Python 统一编译配置、校验计费单位与选模；结果保留 provider 和实际模型。
- 真实模式迁移需添加 `providerConfig` 或 `preset: "ark-agent-plan"`，配合核心 0.3.0。

## 0.10.0

- 新增 `refractagent` 原生模型提供方，提供省成本、均衡与质量优先三个文本任务接口。
- 模型接口通过已安装的 Python 核心运行，默认演示，保留 DSH 凭证、沙箱与进程边界。
- 原验证和文本任务工具保留；路由、评分及记账继续由 Python 管理。

## 0.7.0

- 新增 `refractrouter_task` 与 `taskProfilePath`，由 Python 完成文本 DAG 规划、A/B 选模、执行和独立评审。
- 合并既有基准候选策略时按 runner 职责区分参数，避免将基准选模选项传入文本任务。

- 文本任务新增有界并发、provider 并发上限及启动间隔参数；默认串行。
- 结果增加执行模式、最大并发、观测峰值和预测时延，Python 负责调度与原子预算。
- A/B 使用完整 DAG 调度时延；B 不再奖励对总耗时没有贡献的分支加速。
- 支持分层 profile 与固定校准/测试协议，提供零调用预检及完整模拟对照。
- 取消或失败后停止新派发并结算在途调用；真实组合收益仍待完整对照验证。

## 0.6.0

- 新增 `acceptanceCriteria`，原样转交 Python 核心并冻结规划验收条件。
- 模型规划采用 `text-task-plan-v2`，明确依赖字段与理由、节点契约、能力需求和验收覆盖。
  旧版显式计划仍可使用并标注缺少交接契约，模型生成计划不得降级。
- 零调用预览改为单节点，避免把固定模板当成任务拆分；提供并行机会、依赖深度及汇总
  诊断产物。运行时仍串行，质量 profile 仍是迁移预测。
- 核心校验结构化交接输出，失败时保存原文与费用并阻止后续执行；插件只负责接入。

## 0.9.0

- 新增 `stage: "resume"`，复用已验证的 K3 基线，只执行参考路线与节点探针，最多 28 次。
- Python 验证阶段、任务、模型、硬契约、费用和代码兼容记录；不改写历史产物。
- 本阶段新增费用与已有 K3 费用分开留证；未知用量不计为零。
- 增加真实历史基线的原生零调用恢复验证，默认仍关闭付费执行。

## 0.8.0

- 新增 `stage: "baseline"`，只执行一次 K3 整任务调用，成功或失败均不进入参考路线及探针。
- Python 将该单次阶段的等待上限设为 300 秒，保留 8192 token 输出上限和零自动重试。
- 增加原生子进程单次预检与成功／失败停止回归；其他阶段仍使用原有 120 秒时限。

## 0.7.0

- 新增 `k3-baseline` 类型化阶段及独立评审交接路径，支持准备、组合两个原生调用阶段。
- 保持默认零调用、单轮零重试、Agent Plan 专用端点与部署额度限制。
- 本阶段允许内部评审额度为零；外部评审费用另计，未知费用不按零处理。
- 新增原生工具到 Python 的零调用验证；成本选模、评审校准、材料冻结和核算由 Python 负责。

## 0.6.0

- Add the typed `execution-modes` phase for Python's explicit v0.4 A/B/C report comparison.
- Default that phase to v2 selection, require zero retries and at most three repeats, and retain
  disabled paid runs, exact Agent Plan endpoint and both deployment ceilings.
- Validate a real zero-call subprocess preflight through the registered tool. Evidence ownership,
  experimental comparisons, accounting and judging remain in Python.

## 0.5.0

- 新增有类型的 `selectionPolicy`，经 DSH 基准 runner 原样传给 Python。
- 保留 v1 默认行为，支持显式 v2 排除已知契约拒绝；未知失败继续阻断。
- 选模语义与配对样本规则留在 Python，并补充参数契约回归。

## 0.4.1

- Migrate plugin and service contracts to strict TypeScript, with explicit host/config/tool/result
  types and validated Python evidence projection. Malformed evidence fields fail closed.
- Build the ESM entry and declarations into `dist/`; pack only the runtime distribution, with no
  runtime dependencies. Retain endpoint, credential, budget and replay safeguards.

## 0.4.0

- Add `contract-replay` for the seven frozen issue #25 writer failures. Default to preflight,
  limit repeats to three, prohibit retries, stop after the first failure, and retain all existing
  Agent Plan credential and budget controls. Replay results establish contract validity only.

## 0.3.0

- Send AFP benchmark calls directly to the Agent Plan OpenAI-compatible Chat Completions endpoint,
  avoiding the DSH stdio bridge that could stall before dispatch.
- Reject AFP manifests unless every model uses provider `ark-plan` and the exact
  `https://ark.cn-beijing.volces.com/api/plan/v3` base URL, preventing fallback to ordinary Ark
  pay-as-you-go billing.
- Resolve the Agent Plan key through DSH credentials only for a paid operation, inject it into the
  scrubbed child environment, and persist prompt-free `model-progress.ndjson` request evidence.

## 0.2.2

- Enforce per-request timeouts locally while consuming DSH streams, including providers that ignore
  the supplied abort signal.
- Persist prompt-free request start and finish records so long paid runs expose their current model
  and completed-call progress.

## 0.2.1

- Reject DSH model routes whose provider-owned retry policy is not normal mode with zero retries.
- Carry the runner's per-model timeout across the stdio bridge and abort stalled DSH streams.

## 0.2.0

- Add an AFP-billed Volcengine Agent Plan manifest and generic billing-unit budgets.
- Route Agent Plan calls through the hosting DSH `llm` service over a bounded stdio bridge, so the
  provider credential remains owned by DSH and is never copied into the Python child.
- Validate the frozen provider/model routes before a paid run and expose the billing unit in
  structured preflight and evidence results.
- Reject paid ceilings below the conservative preflight estimate, reserve an estimated call before
  each invocation, and default DSH runner retries to zero.

## 0.1.1

- Bound evidence and standard-stream capture, fail on truncation, and redact resolved credentials
  from returned diagnostics.
- Declare and test the v0.1 DSH, Node, and pnpm compatibility contract.
- Add clean-profile installation lifecycle validation and release, troubleshooting, upgrade, and
  rollback documentation.

## 0.1.0

- Add the `refractrouter_validate` Cordis tool with preflight-safe defaults and two-level paid-run
  budget enforcement.
- Use DSH subprocess, sandbox, policy, and credential services while keeping benchmark logic in the
  Python runner.
