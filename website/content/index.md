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

## Python 核心与 DSH 插件

<figure class="doc-diagram"><img src="/router-boundary.svg" alt="Agent、Router 与模型的职责：Agent 保持原生执行循环，Router 选模与记账"/><figcaption>Agent 保持工具、权限与任务推进；Router 只做选模、判别、费用与轨迹。分层图见[架构](architecture.md)。</figcaption></figure>

很多人第一次接触会以为 DSH 插件就是 RefractRouter。实际上插件只是宿主适配层：
它把 DSH 的请求转给独立的 Python 核心，核心决定用哪个模型、如何审核、怎么记账，
插件再把结果和轨迹展示出来。Codex CLI 走的是另一条路：标准模型网关按 Base URL
接入，不装插件。两条路最终调用的是同一套 Python 策略实现。

分层细节、模块速查和语言边界见[架构](architecture.md)。

## 一次真实运行留下的证据

每次路由都会在本机留下可核对的记录：实际模型、判别、费用与决策理由。
下图是 2026-10-07 一次自动路由任务的路由轨迹：Jev 判为可拆分，但比较 Direct 与 DAG
的预测成本后选择整任务直接执行——候选计划 4 个节点，最终只用 1 个。

<figure class="doc-screenshot"><a href="/screenshots/auto-route-summary.jpg" target="_blank" rel="noopener"><img src="/screenshots/auto-route-summary.jpg" alt="真实路由轨迹：可拆分但最终选择整任务 Direct 执行"/></a><figcaption>「可拆分」与「应该拆分」是两个判断；读法详解见[运行记录](traces.md)，完整案例见[自动路由](automatic.md)。</figcaption></figure>

## 适用场景

- **代码任务**：由 Agent 读写文件、运行测试，[Stage](strategies/stage.md) 根据可信执行证据切换模型。
- **研究与写作**：[Task](strategies/task.md) 在任务开始时选择主模型；[Advisor](strategies/advisor.md) 对最终候选进行审核。
- **成本受控的探索**：[Escalation](strategies/escalation.md) 先使用起始模型，必要时由指定接管模型接手。
- **独立子问题研究**：通过[自动路由](automatic.md)尝试 DAG；同时核对规划、汇总和审核的额外开销。

每条场景都附有真实验收案例与设置截图，不只停留在概念描述。

## 从哪里开始

1. [下载安装](installation.md)：下载 wheel 与插件包，保留已有 DSH profile。
2. [第一项任务](quickstart.md)：先用 Static 验证真实模型与工具接线。
3. [六种策略](strategies/index.md)：了解各自的选模、审核和接管行为。
4. [运行记录](traces.md)：检查实际模型、图形、执行时间、费用和失败原因。

::: tip 目标与证据分开看
降低成本和等待时间是产品目标。目前没有证据证明所有策略或 DAG 在开放任务上普遍优于
固定模型。Judge 的概率与分数也不是任务成功率。请结合[验证范围](status.md)判断是否适合你的工作。
:::
