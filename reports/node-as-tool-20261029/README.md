# 专家节点工具零付费验证

关联 Issue #200。分支 `codex/planning-node-as-tool`。
本批只验证工程契约，收益结论仍为 `Insufficient-evidence`，没有真实模型费用。

## 真实宿主验收

使用已安装 DSH 0.1.5-rc.3 的真实 `LlmRuntime + Session + ToolRuntime`，
与当前 worktree 的 Python 核心通信。模型回复来自确定性夹具。
Static 和规则 Stage 分别完成 3 次专家工具调用、4 次主模型请求，
每条路线的 7 次模拟请求共用一个父 run 和父账本；不创建 DAG。

| 路线 | 最新原始证据 | 主请求 | 专家请求 | 真实模型网络调用 |
|---|---|---:|---:|---:|
| Static | [验收](../node-as-tool-20261029-static-05/acceptance.json) | 4 | 3 | 0 |
| Stage | [验收](../node-as-tool-20261029-stage-05/acceptance.json) | 4 | 3 | 0 |

最新两条验收包含源码与锁文件哈希、宿主版本、会话事件、原始账本和网络保护代码。
源码哈希已与当前 worktree 复核；工具调用、结果与账本关联另行逐项核验。
Python 保护通过 ready 标记确认已加载，任何 TaskDAG 构造都被拦截。
Node socket/http/fetch、Python socket/DNS 被阻断，实际尝试数为 0。
[宿主模块版本和文件哈希](host-versions.json) 单独归档。
`simulatedCost` 只是对夹具用量的记账值，不是节省或真实支出。

较早的 static-01、stage-01 也保留，覆盖基础 HTTP/fetch 与 Python socket 禁网；
它们没有最新源码哈希及 Node socket/DNS 保护，不与 -05 混充同一次冻结运行。
-02、-03 是加上源码哈希与 socket/DNS 保护的过程验收；-04 加上 DAG 构造拦截；
-05 再确认保护已加载。全部保留，不把同一夹具的重复当成独立质量样本。

## 负向行为与回归

Python 测试覆盖默认关闭、定义冲突、工具总数、伪造及重复调用、父金额和调用数上限、
调用期限、隐私拒绝、取消后的迟到结算、未知用量、递归工具拒绝及逐字引文检查。
Stage 的既有保持状态复用由 Python 行为测试验证；真实 DSH 夹具没有制造任务失败，
因此它不证明真实任务中的模型升级命中率。

初次完整测试发现打包白名单漏列新 `node-tools` 模块；已补齐清单。
额外负向测试发现已结算的无效专家输出会误标为未知用量；已区分为失败并保留实际费用。
[初次契约失败日志](contracts-initial-failed.log) 保留，不抹去失败记录。
最终完整 `uv run pytest`：**2116 passed**；包括 20 项节点工具行为测试和插件契约测试。
严格 TypeScript 检查通过。详见 [验收汇总](validation-summary.json)、
[pytest 日志](pytest.log)、[类型检查日志](typecheck.log)。

## 尚未完成的效果验证

本批不能回答专家工具是否优于 one-shot 或 DAG，不能宣布路由质量或成本收益。
下一阶段沿用 [五臂对照草案](../../docs/node-as-tool-eval.md)。
[数据审计](dataset-audit.json) 发现旧 test 中 5 题同时属于 pilot；
另一个 quality-study-v1 仍是 draft，formal_run_ready=false，不能直接声称已有全新且已审查的留出集。
仍需准备统一交付合同的真实五臂运行器、开发集基线优化、明确任务及模型、最坏费用预检，
再按 AGENTS.md 取得规划模式真实对照的明确范围和预算授权。
真实模型调用尚未发生，Issue 提议的 60 AFP 尚未验证足够覆盖整个对照。
已按现有公共投影函数导出 [六个开发候选输入](p2-development-candidates.json)，
不含私有参考、split、结构标签或审查记录；它们仅是草案，不是已批准的执行批次。

## 选模信号的适用性发现

[实际策略轨迹](policy-applicability.json) 显示本批 Stage 的 7 次请求全部使用 small，
实际切换次数为 0。Python 单测验证既有保持状态能选择 large，两者的证据范围不同。
规则 Stage 依赖工具执行失败等信号，不自动识别格式正确但内容错误的专家回答；
专家输出合同失败则停止父任务。纯文本报告任务可能无法产生预期升级信号。
付费前必须核对任务和选模策略的适配性；未触发切换须标记 policy-not-exercised，
不能把固定与 Stage 的差解释为模型分配收益。

## 复现

先构建插件，在仓库根目录运行以下命令，并替换为全新证据路径：

```bash
node validation/dsh/plugin/scripts/check-node-tools.ts \
  /已安装DSH/node_modules /当前worktree/.venv/bin/python \
  reports/新的证据目录 static --enable-node-tools
```

将 `static` 替换为 `stage` 可运行规则 Stage。脚本拒绝覆盖已有证据目录。
默认产品 `apply` 不调用研究工具安装器，实验不改变日常模型、额度或策略配置。
