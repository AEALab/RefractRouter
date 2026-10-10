---
title: 项目简介
---

<div class="doc-kicker">REFRACTROUTER · 析衡</div>

# 让团队的模型，按任务各尽其用

<p class="doc-intro">RefractRouter 面向小型开发团队提供独立模型路由：先满足可接受的质量，再降低模型总成本，最后减少响应与等待时间。</p>

<div class="doc-badges"><span class="doc-badge">独立 Python 核心</span><span class="doc-badge">DSH / Codex CLI</span><span class="doc-badge">开发预览</span></div>

你可以继续使用已有的 Ark、Kimi、DeepSeek 或其他已适配模型服务。Router 根据策略选择
实际模型，记录判别、接受与丢弃、调用费用及运行原因。模型提供方的凭证由你自己配置。

## 两种路由

<div class="doc-route-links">
  <a class="doc-route-link" href="/RefractRouter/planning.html"><strong>规划路由</strong><span>保留 Agent 原生执行循环。使用 Static、Stage、Task、Composite、Advisor Gate 或 Escalation 选择模型、审核和接管。</span></a>
  <a class="doc-route-link" href="/RefractRouter/automatic.html"><strong>自动路由</strong><span>判断整任务 Direct 与任务 DAG 的适用性；必要时规划节点、分配模型、并行调用和汇总。保留为独立研究入口。</span></a>
</div>

“规划”在这里指**模型调用策略**，不会把你的任务拆成 DAG。“自动”也不表示每次都拆分：
即使任务可以拆分，Router 仍可能选择 Direct。详见[两种路由怎么选](routing.md)。

## 与 Agent 的分工

<figure class="doc-diagram"><img src="/router-boundary.svg" alt="Agent 负责工具、权限和任务推进，Router 负责模型选择、判别、费用与轨迹"/><figcaption>工具执行、审批、技能、上下文压缩、委派与任务推进继续由接入方 Agent 负责。</figcaption></figure>

| RefractRouter 负责 | DSH / Codex 等 Agent 负责 |
| --- | --- |
| 模型准入与选择、Judge 判别、候选审核 | 工具与文件操作、审批、任务推进 |
| 受管模型调用的预留、结算和审计 | 会话、系统指令、技能、上下文压缩 |
| 模型协议转换和回复真实来源 | 子 Agent 与后台生命周期 |

DSH 插件提供模型入口、设置和图形展示。独立标准模型服务则通过 Base URL 接入，
不依赖 DSH，也不在标准模型请求中建立 DAG。

## 适用场景

- **代码任务**：由 Agent 读写文件、运行测试，Stage 根据可信执行证据切换模型。
- **研究与写作**：Task 在任务开始时选择主模型；Advisor 对最终候选进行审核。
- **成本受控的探索**：Escalation 先使用起始模型，必要时由指定接管模型接手。
- **独立子问题研究**：通过自动路由尝试 DAG；同时核对规划、汇总和审核的额外开销。

## 从哪里开始

1. [下载安装](installation.md)：下载 wheel 与插件包，保留已有 DSH profile。
2. [第一项任务](quickstart.md)：先用 Static 验证真实模型与工具接线。
3. [六种策略](strategies/index.md)：了解各自的选模、审核和接管行为。
4. [运行记录](traces.md)：检查实际模型、图形、执行时间、费用和失败原因。

::: tip 目标与证据分开看
降低成本和等待时间是产品目标。目前没有证据证明所有策略或 DAG 在开放任务上普遍优于
固定模型。Judge 的概率与分数也不是任务成功率。请结合[验证范围](status.md)判断是否适合你的工作。
:::
