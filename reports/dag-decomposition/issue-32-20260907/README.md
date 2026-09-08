# Issue #32 实施顺序与验收核验

核验日期：2026-09-07。对象为本地工作区，基准提交为
`13827056c0dbf24026f0cdf7fa027c8557aa1ad1`，包含尚未提交的文本任务与 DAG 契约修改。
本报告中的通过表示本地实现及对应测试通过，不表示已合并、已发布或获得真实路由收益。

结论：7 项清单中，2 项本地通过、2 项部分完成、3 项未完成。Issue 应保持打开。

## 逐项验收

| 序号 | Issue 原要求 | 核验结果 | 证据与剩余工作 |
|---|---|---|---|
| 1 | 版本化 DAG 契约与兼容校验 | 本地通过 | `text-task-plan-v2` 覆盖职责、输入输出、依赖理由、验收覆盖、能力需求、执行方式及失败策略。旧显式计划保持兼容并标注限制，新规划不得降级；非法新增字段、覆盖缺失和契约引用错误在调用节点前拒绝。声明一致性通过不代表依赖语义已被证明。 |
| 2 | 六类无调用样例，区分结构与语义 | 本地通过 | 可并行、必要串行、单节点固定计划均在禁止网络的模拟运行中通过；重复工作提示覆盖过度拆分；汇总节点诊断及输入超预算阻断覆盖汇总瓶颈；缺失字段保留原文和账目并阻止下游。测试不证明规划器真实拆分质量或加速收益。 |
| 3 | 有界并发、原子预算、匹配的时延预测 | 未完成 | `task_runtime.py` 仍按 `plan.order()` 串行循环，`node_routing.py` 仍累加串行时延。尚无有界并发调度及并发账本保护，不能验证真实重叠、并发限流/取消或并发失败记账。现有串行预算测试不替代此项。 |
| 4 | 能力、输入规模、风险分层 profile，跨模型交接，A/B 和单模型结果 | 部分完成 | A/B、全同一模型、不拆分、容量筛选及模拟交接已验证。`NodeProfile` 仍按模型与节点类型索引，难度和风险是元数据；尚无分层质量实测或新版契约的真实跨模型组合验证。 |
| 5 | 冻结多任务对照与预算，并零调用预检 | 未完成 | 尚无针对本轮新版拆分的冻结任务集、重复次数、判定阈值及完整成本清单。旧版报告实验和现有 demo 不能替代新的对照计划。 |
| 6 | 获批后真实组合与配对对照 | 未完成 | 本次真实模型调用为 0。旧冻结实验不验收本轮新版机制；需先完成第 5 项并获得对应实验范围的预算授权。 |
| 7 | DSH 插件验证同一核心的实际任务入口 | 部分完成 | 24 项 TypeScript 契约测试包含原样转发新版计划/验收条件到真实 Python 进程的零调用预检；插件 0.6.0 在真实 DSH 隔离 profile 中完成打包安装、覆盖、卸载、重装和启动。未通过真实 DSH 助手执行新版付费文本任务，也未完成并发与真实收益对照，因此保留未勾选。 |

## 验证结果与复现命令

完整测试：180 项测试、5 项子测试通过，包含调用 TypeScript 契约测试的测试项。
其中 TypeScript 契约共 24 项；此数量是嵌套测试细分，不与 180 简单相加。
完整输出保存在 [pytest.log](pytest.log)。

```bash
UV_CACHE_DIR=/tmp/refractrouter-uv-cache uv run --offline pytest -q
```

插件打包生命周期通过，DSH `0.1.1-rc.2`、Node `22.22.3`、pnpm `10.15.0`，
付费调用数为 0。使用临时 `DSH_HOME`，未修改日常 profile。
原始结果保存在 [dsh-lifecycle.log](dsh-lifecycle.log)。

```bash
PATH="/tmp/refractrouter-issue28-tools/node_modules/.bin:$PATH" \
  npm_config_cache=/tmp/refractrouter-npm-cache \
  python3 scripts/validate_dsh_plugin_lifecycle.py --packed
```

临时工具目录仅为本次环境；其他环境应先安装项目规定版本的工具。
`git diff --check` 通过。

## 六类场景对应证据

| 场景 | 对应测试或产物 | 实际验证含义 |
|---|---|---|
| 可并行 | `test_dependency_structures_and_versioned_roundtrip`；[分支运行](parallel-analysis.json) | cost/risk 同属就绪波次，answer 等待两者；执行仍串行 |
| 必要串行 | 同一参数化测试；[串行运行](serial-analysis.json) | risk 消费 cost，保持 cost → risk → answer 的依赖 |
| 过度拆分 | `test_duplicate_work_is_reviewed_without_deleting_required_edges` | 重复指令和输入触发复核提示，不擅自删除依赖；未声称完成经济收益预测 |
| 汇总瓶颈 | `test_join_context_overflow_preserves_branch_costs_and_blocks_merge` | 两分支完成，汇总超出声明输入预算后不发出汇总或评审调用，保留分支费用 |
| 交接缺失 | `test_invalid_handoff_preserves_output_and_cost_and_blocks_descendants` | 缺少声明字段的输出被拒绝，原文与已发生费用保留，下游不执行 |
| 单节点 | `test_zero_call_preview_never_invents_a_semantic_decomposition`、`test_single_model_and_unsplit_task_remain_valid_options`；[单节点运行](single-answer.json) | 零调用预览不虚构拆分；A/B 可以不拆分或全部使用同一个模型 |

三个运行产物均通过 `run_task(..., mode="demo")` 生成；运行期间替换 `socket.socket`
以禁止网络访问，并断言所有节点交接结构通过、最终评审为 null。费用和输出是模拟数据，
不能当成真实质量、费用或时延测量。[场景汇总](scenarios.json) 明确标注真实调用数为 0。

节点测试源：`tests/test_task_decomposition.py`；完整调用、预算和最终评审模拟源：
`tests/test_text_tasks.py`；插件契约源：`validation/dsh/plugin/tests/dsh_plugin_contract.test.ts`。
源文件与产物哈希保存在 [artifact-index.json](artifact-index.json)，以识别本次未提交工作区。

## 下一步顺序

优先完成第 3 项有界并发和共享预算账本，再补齐第 4 项分层 profile 与组合验证设计。
第 5 项冻结多任务对照、阈值和完整预算后，才能请求对应的付费执行授权并推进第 6 项。
第 7 项应在这些核心能力就绪后，通过 DSH 实际任务入口验收同一实现。
历史证据保持原样，不以本次离线通过替换原来的证据不足判定。
