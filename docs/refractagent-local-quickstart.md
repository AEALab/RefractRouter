# 本机安装 RefractAgent 与 DSH 策略模型

RefractAgent 是本仓库提供的本地应用入口，Python 安装包仍名为 `refractrouter`。
安装核心和 DSH 插件后，DSH 中会出现三个模型：

| 模型接口 | 显示名称 | 选择方式 |
| --- | --- | --- |
| `refractagent/economy` | RefractAgent · 省成本 | 满足 profile 质量底线后最小化预测成本 |
| `refractagent/balanced` | RefractAgent · 均衡 | 综合预测质量、成本与时延 |
| `refractagent/quality` | RefractAgent · 质量优先 | 在费用与时间限制内优先预测质量 |

它们共用 Python 路由器，不是三套重复实现。相同任务、配置和候选池可能选到相同模型；
当前内置整任务配置分别选出 DeepSeek V4 Flash、MiniMax M3、DeepSeek V4 Pro。
这是给定 profile 下的选择，不保证每次都更便宜、更快或回答更好。

第一版支持文本分析与生成、对话上下文、整任务处理和预设 DAG。
这些模型不生成 DSH 工具调用；需要 Shell、浏览器或文件操作时，继续使用原有具备工具能力的模型。
原 `refractrouter_task` 和基准验证工具保持可用。

## 1. 构建安装包

需要 Python 3.11+、uv、Node 22.19+（22.x）和 DSH `0.1.1-rc.2`。
从本仓库构建一次；分发给其他成员时只需提供 wheel 和插件 tgz，无需复制实验报告或源码树。

```bash
uv build --wheel
npm ci --prefix validation/dsh/plugin
npm pack ./validation/dsh/plugin --pack-destination ./dist
```

生成的安装包为 `dist/refractrouter-0.2.0-py3-none-any.whl` 和
`dist/dsh-refractrouter-validation-0.10.0.tgz`。依赖与编译输出不提交到 Git。

## 2. 安装核心与插件

在任意目录用绝对路径指向收到的安装包：

```bash
uv tool install /absolute/path/refractrouter-0.2.0-py3-none-any.whl
refractagent models
dsh plugin --profile web add /absolute/path/dsh-refractrouter-validation-0.10.0.tgz
```

`uv tool` 会建立隔离 Python 环境，并安装 `refractagent` 和原 `refractrouter` 命令。
若 shell 找不到命令，运行 `uv tool update-shell` 后重新打开终端。
核心附带所需的模型清单、profile 和示例计划；运行不再依赖源码工作目录。

若使用 headless，也要把插件装入该 profile：

```bash
dsh plugin --profile headless add /absolute/path/dsh-refractrouter-validation-0.10.0.tgz
```

## 3. 先跑零调用演示

进入准备用作任务工作区的目录，生成配置覆盖文件：

```bash
refractagent dsh-config --output ./refractagent-demo.json \
  --runs-dir ./.refractagent/runs --mode demo --strategy balanced
dsh --profile web --patch ./refractagent-demo.json
```

首次打开 DSH，先选择任务工作目录。macOS 默认使用系统文件夹选择窗口。
点击输入框旁的模型按钮，再进入 `Model`，选择 `RefractAgent 本地路由` 下的省成本、
均衡或质量优先；新建会话后输入一个文本任务。模拟模型名称带有“模拟”，
结果以 `[SIMULATED]` 标注。
演示验证安装、选路、进程、会话与记录，不解决真实任务，也不提供真实质量分数。

没有网页时可直接验证完整 headless 会话：

```bash
dsh --profile headless --patch ./refractagent-demo.json \
  "请用两句话比较小规模试点和全面推广。"
```

headless 在没有已保存模型选择时使用覆盖文件中的默认模型。
DSH 网页曾保存的默认选择会优先于覆盖文件；需要固定策略验收时，使用独立的
`DSH_HOME` 安装 headless profile，或先在 DSH 中更新默认模型。
在没有已保存选择的环境中，要换成省成本，生成另一份配置并启动新会话：

```bash
refractagent dsh-config --output ./refractagent-economy.json \
  --runs-dir ./.refractagent/runs --mode demo --strategy economy
dsh --profile headless --patch ./refractagent-economy.json "比较两个方案的成本与风险。"
```

`--strategy quality` 对应质量优先。配置生成器不会覆盖已有文件。

## 4. 启用真实模型执行

按团队批准范围设置每次任务的生产和评审预算。以下 40 / 80 AFP 是保守准入上限示例，
不是预计费用，也不表示余额。实际费用按每次调用的服务端 usage 和清单费率记录。
完整 DSH 系统上下文也会传入节点和评审，包括启用的工作区指令和技能目录，
因此发送范围与预算不能只按用户输入的几句话估算。
只做题目验收时可使用独立工作目录和 `DSH_HOME`，并通过 DSH 覆盖配置关闭
`agent-instructions`、`skill-filesystem`，设置 `system-prompt.includeRuntimeContext=false`
及不含工作目录的通用 `persona`；先用 demo 的 `request.json` 核对完整上下文。

```bash
refractagent dsh-config --output ./refractagent-live.json \
  --runs-dir ./.refractagent/runs --mode live --strategy balanced \
  --production-budget 40 --evaluation-budget 80
```

在该覆盖文件的 `refractagent` 配置中，把 `allowPaidRuns` 改为 `true`。
生成器始终默认关闭，切换 `executionMode` 本身不会授权调用。
这是部署时的一次性配置；启用后，应用不会为每个请求再次询问许可。
AFP 记录用于追踪用量；订阅账户不能直接把它解释为额外现金扣费。
在启动 DSH 的终端安全地设置 `CODEX_ARK_API_KEY`，或让 DSH 凭证服务提供该环境引用；
不要把密钥写入覆盖文件。然后启动：

```bash
dsh --profile web --patch ./refractagent-live.json
```

确认模型名称不再带“模拟”，选择策略后提交任务。
Ark 使用 Agent Plan `/api/plan/v3`；插件通过 DSH 原生凭证服务解析密钥，
Python 执行调用、路由、预算和评审。自动重试为零。
整任务模式每个成功任务通常是一次生产调用和一次独立评审，不先运行全模型探针。

任务结束后，DSH 正文是答案；独立的运行说明包含策略、真实模型、质量状态、费用及记录位置。
“生成完成但质量未通过”和“评审不可用”会保留已有答案，不冒充质量通过。
取消或超时会停止新派发；已经发出的调用仍可能结算，未知费用继续保留预留。

## 5. 查看结果与复用计划

每次执行生成新的任务目录，保存 `request.json`、`manifest.json`、`profile.json`、
`result.json`、`summary.json`，以及有输出时的 `answer.md`。

```bash
refractagent show /absolute/path/to/run-directory
```

查看 `strategy`、`models`、`status`、`costs`、`quality` 与 `simulated`。
模拟费用必须与真实费用区分。`usage` 汇总任务内部调用，包含评审，
不把它当作单次物理模型的上下文长度。

默认 `single` 直接处理完整任务。成本与风险比较可选 `compare`，复用已校验的三节点计划：

```bash
refractagent run --task "根据以下材料比较 A/B 成本与风险……" \
  --strategy balanced --template compare --mode preflight \
  --runs-dir ./.refractagent/runs
```

DSH 中可在 `refractagent` 配置增加 `"template": "compare"`，新会话复用同一计划。
也可以通过 CLI 的 `--request-file` 传入已有 `plan`。普通使用不需要手写节点权重。

## 6. 常见问题

| 现象 | 处理 |
| --- | --- |
| 找不到 RefractAgent 模型 | 确认插件安装在当前启动的 profile，重启 DSH；核心可先运行 `refractagent models` |
| 找不到 Python 核心 | 使用已安装的 `refractagent dsh-config` 重新生成覆盖文件，它会固定对应 Python 路径 |
| 一直得到 `[SIMULATED]` | 当前仍为 demo；按真实执行步骤配置模式、预算与付费开关 |
| `no-feasible-route` | 当前 profile 或资源约束无法支持任务；调整经批准的配置，系统不会静默放宽条件 |
| `budget-exhausted` | 查看任务账本；本次输入、输出上限或评审超出剩余额度，不自动重跑 |
| 沙箱拒绝写记录 | 在有写权限的工作目录中启动，设置目录内的 runs 路径；沿用 DSH 的 workspace-write 权限 |
| 修改默认模型后旧会话未切换 | 旧会话保留其选择；在 UI 切换会话模型或新建会话 |
| 已切到真实模式，上方仍有 `[SIMULATED]` | 历史演示回答不会被重新生成；新建会话、选择真实模型并发送新的 Query |
| headless 忽略 `--strategy` 生成的默认选择 | 已保存的 DSH 模型设置优先；更新 DSH 默认选择，或用独立 `DSH_HOME` 验收 |
| 工作目录选择后才能输入 | 首次使用需先选择本机工作文件夹；macOS 的系统选择窗口可能位于浏览器后面 |

质量 profile 来自固定材料的报告任务，其他任务可能迁移不佳；应用会保存最终评审与用户可用答案。
本次真实验收发现 M3 的长度控制偏松，且模型评审可能漏检；严格字数或格式要求需另行复核。
需要拓展模型或修改预测数据时，由维护者发布新配置，不在一次失败后自动探测所有模型。
