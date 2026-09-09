# DSH 验证与接入边界

本目录集中存放 DSH 插件及其 Python 调用与验证入口，与 `src/refractrouter/` 核心
保留在同一仓库。Router 是项目核心；DSH 插件用于验证核心功能的可行性，也是未来
“DSH + 插件连接核心 Router”产品形态的适配层。

## 用户安装入口

普通用户请从 [Wiki：安装与启动指南](https://github.com/AEALab/RefractRouter/wiki/安装与启动指南) 开始，
或阅读 [仓库内同版说明](../../docs/refractagent-local-quickstart.md)。
RefractAgent 模型入口安装 wheel 和插件 tgz 后即可使用，不需要单独启动 Router HTTP 服务。
用户可通过插件的 `providerConfig` 自行配置 providers 与 models，Ark Agent Plan 为可选项；
详见 [配置指南](../../docs/provider-configuration.md)。
本页其余内容主要说明开发集成与历史工具验证。

## 目录与职责

| 路径 | 用途 |
|---|---|
| `plugin/src/` | TypeScript 工具注册、参数与结果类型、宿主进程及凭证对接 |
| `plugin/tests/` | 插件契约与打包测试 |
| `task_runner.py` | 接收文本任务请求，调用 Python 核心任务运行时并保存证据 |
| `real_runner.py` | 组织真实模型基准的预检、执行及证据验证 |
| `canonical_runner.py` | 在隔离目录验证固定基准的五种策略及实验产物 |
| `runner.py` | 调用固定 RefractRouter CLI，记录命令、退出状态、哈希及产物检查 |

任务规划、DAG 校验、节点选模、执行、评分和预算记账归属 Python 核心及运行时。
插件只适配宿主请求、部署限制和结果；不能在 TypeScript 中复制这些业务决策。
完整边界见 [项目架构](../../docs/architecture.md)。

## 两种工具入口

- `refractrouter_validate`：冻结基准验证，默认预检；付费执行需部署开关、明确预算和凭证。
- `refractrouter_task`：文本任务入口，调用核心完成 DAG 规划、节点选模、执行和评估。
  `preflight` 使用标注的预览，`demo` 使用模拟输出，`plan` 和 `run` 会调用真实模型。
  使用方式见 [文本任务与节点路由](../../docs/text-task-routing.md)。

DSH 负责工具调度、会话、沙箱、进程生命周期和凭证服务。插件通过 `ctx.subprocess`
启动固定参数列表，不让模型组装 Shell 命令。直接 HTTP 调用仅向受控子进程传递凭证；
通用 `dsh-llm` 基准清单通过受限 stdio 桥使用 DSH provider，凭证留在宿主内。
DSH 外层助手的模型配置与核心对 DAG 节点的选模分别管理。

上述历史工具仍依赖匹配的 RefractRouter 源码环境。RefractAgent 三策略模型入口使用
已安装的 Python 核心，已支持脱离源码目录执行。两类入口均由 DSH 启动本地 Python 进程；
当前尚未提供独立部署的 Router HTTP 服务。

## 安装与验证

当前兼容范围为 DSH `0.1.1-rc.2`、Node `>=22.19.0 <23`、pnpm `10.15.0`。
插件保持私有，按仓库路径或同一提交生成的 tarball 安装。完整配置、故障诊断、升级和
回滚方法见 [插件指南](plugin/README.md)。以下命令从仓库根目录执行：

```bash
npm install --global pnpm@10.15.0 @deepseek-ai/dsh@0.1.1-rc.2
npm ci --prefix validation/dsh/plugin
npm run --prefix validation/dsh/plugin build
dsh plugin --profile headless add ./validation/dsh/plugin
dsh --profile headless --dump-config | rg refractrouter-validation
```

在临时 `DSH_HOME` 中验证安装、配置覆盖、卸载、重装和启动，不发起模型调用：

```bash
python3 scripts/validate_dsh_plugin_lifecycle.py
python3 scripts/validate_dsh_plugin_lifecycle.py --packed
```

通过 DSH 调用基准预检：

```bash
dsh --profile headless \
  '仅调用一次 refractrouter_validate，参数为 {"phase":"final","executePaidRun":false}，原样返回工具结果。'
```

该工具预检不调用候选或评审模型；DSH 外层助手仍可能产生模型费用。运行 DSH 会话前，
需获得向所配置外部模型发送仓库上下文的授权。执行器需要写入临时产物，应使用
`workspace-write` 或明确授权的适当沙箱策略。

## Python 验证入口

无需启动 DSH，也可以直接运行同一 Python 验证入口，例如基准预检：

```bash
uv run python validation/dsh/real_runner.py \
  --dataset data/benchmarks/v0.1.json \
  --manifest data/model-manifests/openai-gpt-5.4.json \
  --phase dry-run \
  --output-dir /tmp/refractrouter-real-preflight \
  --evidence /tmp/refractrouter-real-preflight-evidence.json
```

默认预检验证数据集与模型边界、记录输入和代码哈希，并估算调用计划，不调用候选或评审
模型。付费运行还要求 `--execute-paid-run`、生产和评审预算，以及清单指定的凭证。
每次执行应使用新输出路径，保留已完成实验的原始证据。

AFP 清单要求 `ark-plan` 和精确的 Agent Plan `/api/plan/v3` 端点。
部署预算、调用预算、重试策略与凭证要求见 [插件指南](plugin/README.md)。
固定 CLI 的本地调用和证据格式另见 [runner 说明](runner.md)。

## 验收含义

插件生命周期、契约与模拟执行验证的是宿主接入路径。核心路由收益必须通过真实组合执行
及独立的质量、成本、时延对照评估判断，不能从插件成功安装或预检通过推导。
本目录的验证结果用于支持研究和产品入口探索，不代表其他产品形态已交付。


## 实际任务入口验证

2026-09-07 已在隔离 DSH `0.1.1-rc.2`、插件 `0.7.0` 中验证一次完整自然任务：
助手调用 `refractrouter_task`，请求不含预设 plan；Python 核心自动规划成本分析、风险分析
和汇总三个节点，两个分支并行执行，最终独立模型评审通过（100 分）。
会话证据确认参数原样传递且工具仅调用一次。详见
[完整报告与原始证据](../../reports/dag-decomposition/issue-32-dsh-live-20260907/README.md)。

该任务三个节点均由 A 选中 `cheap`，使用迁移 profile，不是任意任务的分层校准证明；
完整路由收益和异构交接验收仍待完成。此前容量不足和最终交付遗漏的失败均已保留。
本机 DSH 配置若仅需关闭外层推理，不应声明仅含 `off` 的 `reasoningEfforts` 字典；
本次隔离路由使用 `reasoningEfforts: false`，不修改日常 DSH profile。

DSH 进程退出码 0 仅表示助手完成回复；任务成功须同时核对工具 `status`、
`task.status` 和 `task.evaluationPassed`。当前共享返回结构中的顶层 `phase: dry-run`
来自基准入口占位，不能据此认定文本任务未调用模型；文本任务阶段以 `task.mode` 为准。
