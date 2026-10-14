# 架构：Python 核心与 DSH 插件

RefractRouter 是单仓库、分层职责的结构：Python 核心拥有所有路由决策，TypeScript
插件只是宿主适配层。理解这条边界，是理解项目所有行为的第一步。

<figure class="doc-diagram"><img src="/architecture-layers.svg" alt="宿主层、插件层、Python 核心层与模型层的四层职责图"/><figcaption>策略、准入、账本与证据只在 Python 核心出现一次；插件与网关都是这条权威实现的接入方式。</figcaption></figure>

## 为什么要这样分

模型路由的价值取决于决策的一致性和账目的可信度。如果选模规则同时存在于 Python 和
TypeScript，两边的行为偏差会直接导致实际调用与记录不符。因此项目约定：

- 路由、评分、预算记账、Go/No-go 判定只实现一次，全部在 Python。
- 插件只做三件事：把宿主请求转成核心协议、把核心签发的调用交给宿主模型服务、
  把结果和轨迹展示给用户。
- 核心不绑定 DSH：标准模型网关走 HTTP，Codex CLI 不需要 DSH 也能使用六策略。

插件位于 validation/dsh/plugin/ 是历史原因；它现在是产品化入口之一，不是验证工具。
包名保留 dsh-refractrouter-validation 仅为兼容已安装版本。

## 各层的具体职责

| 层 | 位置 | 负责的事 | 明确不做的事 |
| --- | --- | --- | --- |
| 宿主 Agent | DSH / Codex CLI | 工具执行、权限审批、技能、上下文压缩、子 Agent | 不决定用哪个模型 |
| DSH 插件 | validation/dsh/plugin/src/ | 宿主适配、设置卡片、DAG 图形、路由轨迹、进程生命周期 | 不计算路由、评分、预算 |
| 标准网关 | src/refractrouter/model_gateway.py | HTTP Base URL、refract/* 虚拟模型、协议转换 | 不隐式进入 DAG |
| Python 核心 | src/refractrouter/ | 六策略状态机、自动路由求解、Judge 合同、准入、账本、证据 | 不执行宿主工具、不管理会话 |
| 模型层 | 用户配置的 provider | 实际推理与判别 | — |

## 一次规划路由调用的旅程

以 DSH 中的一次 Stage 调用为例，数据这样流动：

<figure class="doc-diagram"><img src="/planning-call-journey.svg" alt="规划路由调用旅程：请求、选模、签发、返回、记账，工具证据回到核心"/><figcaption>绿色两步在 Python 核心完成；宿主工具语义不进入核心，核心只消费证据状态。</figcaption></figure>

1. DSH 原生循环准备发起模型请求，插件拦截这个请求，通过本机子进程发给 Python 核心。
2. 核心按冻结的任务状态和策略规则选出目标模型，原子预留预算后签发调用指令。
3. 插件把调用转给 DSH 的模型服务，模型流式返回；工具调用原样交回 DSH 执行。
4. DSH 的工具结果作为结构化证据随下一轮请求回到核心，核心据此决定下一轮用哪个模型。
5. 每次调用的费用、判别、接受或丢弃都写入本机证据文件，界面读取这些记录展示轨迹。

这个循环里没有任何一步需要核心理解 DSH 的工具语义；核心只消费证据状态
（completed / failed / denied / unconfirmed），这正是它能同时服务 Codex 的原因。

## 一次自动路由任务的旅程

自动路由由核心独立调度（仍属研究入口）。任务整体进入核心后，先过零调用准入，
再判断是否值得为拆分付费；只有结构信号支持时才调用规划模型，然后比较 Direct 与
DAG 的完整成本。详见[自动路由](automatic.md)的流程图。

## 核心模块速查

| 模块 | 职责 |
| --- | --- |
| [planning_runtime.py](https://github.com/AEALab/RefractRouter/blob/main/src/refractrouter/planning_runtime.py) | 规划路由主状态机：任务冻结、六策略流转、预算包络、证据持久化 |
| [planning_policy.py](https://github.com/AEALab/RefractRouter/blob/main/src/refractrouter/planning_policy.py) | Stage 信号计算、工具事件归一、Static 抽样 |
| [stage_hybrid.py](https://github.com/AEALab/RefractRouter/blob/main/src/refractrouter/stage_hybrid.py) | Stage 协作模式的判别合同与状态转换 |
| [planning_decision.py](https://github.com/AEALab/RefractRouter/blob/main/src/refractrouter/planning_decision.py) | Task 候选过滤、Judge 合同、结果严格校验 |
| [advisor_decision.py](https://github.com/AEALab/RefractRouter/blob/main/src/refractrouter/advisor_decision.py) / [escalation_decision.py](https://github.com/AEALab/RefractRouter/blob/main/src/refractrouter/escalation_decision.py) | 两个审核策略的独立判别合同 |
| [automatic_routing.py](https://github.com/AEALab/RefractRouter/blob/main/src/refractrouter/automatic_routing.py) | 自动路由两级求解：门控 + Direct/DAG 比较 |
| [model_gateway.py](https://github.com/AEALab/RefractRouter/blob/main/src/refractrouter/model_gateway.py) | 标准模型 HTTP 服务，refract/* 虚拟模型 |
| [task_budget.py](https://github.com/AEALab/RefractRouter/blob/main/src/refractrouter/task_budget.py) | 原子预留、派发、结算，规划与 DAG 共用 |

完整文件表见[仓库的架构文档](https://github.com/AEALab/RefractRouter/blob/main/docs/architecture.md)。

## 语言边界的硬规则

- TypeScript 中不得出现路由、评分、预算或 Go/No-go 判定逻辑；插件可以在调用 Python
  前检查部署级限制（比如宿主预算上限），但不能替核心做决策。
- 编译生成的 dist/ 是运行产物，不手写、不提交。
- 新增实现语言或跨层复制业务逻辑，须先在架构 Issue 或 ADR 中提案并获维护者批准。

这些规则不是风格偏好，而是防止两个权威实现漂移的机制。历史事故与恢复核对记录在
[DAG 恢复核对](https://github.com/AEALab/RefractRouter/blob/main/docs/dag-restoration-audit.md)中。
