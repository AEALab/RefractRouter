# 第一项任务

建议先用 **Static 固定模型** 验证安装、凭证和原生工具，再逐一启用需要 Judge 的策略。
一次运行完成不表示所有策略或 Judge 后端已经通过质量验收。

## 1. 先配置 DSH 的真实模型

进入 DSH 的模型设置，配置自己的 provider、端点、模型 ID 与凭证。
Ark Agent Plan 订阅路线使用 `/api/plan/v3`；普通按量接口按实际 provider 配置。
Router 复用目录与凭证，不另复制一份密钥。

先用 DSH 的普通模型确认该路线可用。价格、上下文、输出和推理等级以实际路线的资料为准，
不能把另一渠道同名模型的资料直接套用。

## 2. 启用规划路由

打开 **设置 → 插件 → RefractAgent 规划路由**：

<figure class="doc-screenshot"><a href="/screenshots/dsh-20261014/settings-cards.png" target="_blank" rel="noopener"><img src="/screenshots/dsh-20261014/settings-cards.png" alt="实际 DSH 设置窗口：规划路由与自动路由两张卡片"/></a><figcaption>2026-10-14 实际界面：两张卡片分别展开、独立配置。规划路由卡片显示「已启用」后即可继续。</figcaption></figure>

1. 启用规划路由，确认正在编辑的是 Static。
2. 选择“高效执行模型”；当前 Static 固定模式使用这个角色。
3. 从支持的值中选择推理等级，或选择提供方默认。
4. 核对数据域；需要发往可信云时登记相应信任策略。
5. 设置任务现金预算、参考估值额度、期限与调用数。
6. 运行零调用诊断并保存。

<figure class="doc-screenshot compact"><a href="/screenshots/dsh-20261014/strategy-static-settings.png" target="_blank" rel="noopener"><img src="/screenshots/dsh-20261014/strategy-static-settings.png" alt="实际 Static 设置：固定或随机模式、随机种子与角色权重"/></a><figcaption>「正在编辑的策略」选 Static 后的实际字段。Fixed 只需高效执行角色；Random 才使用种子与两角色权重。</figcaption></figure>

Static 固定模式不需要强执行、任务 Judge 或审核模型。页面上的通用角色不表示每个策略
都必须配置它们。[Static 的实际设置](strategies/static.md)列出了当前限制。

## 3. 选择路由模式并发起任务

在对话模型菜单选择 **RefractAgent · 规划路由**，再在 **路由模式** 中选择 Static。
这里选的是策略，底层模型推理等级使用前一步的角色设置。

<figure class="doc-screenshot compact"><a href="/screenshots/dsh-20261014/routing-mode-menu.png" target="_blank" rel="noopener"><img src="/screenshots/dsh-20261014/routing-mode-menu.png" alt="实际模型菜单：规划路由的路由模式与自动路由入口"/></a><figcaption>模型菜单中的 RefractAgent 分组：规划路由按策略列出，自动路由分模拟与真实执行两个入口。</figcaption></figure>

先问一个简单问题，例如 `2 + 2`。确认回复来自真实模型，且没有 `[SIMULATED]` 或验收夹具文字。
再提交一个你已允许 DSH 执行工具的短任务，确认工具仍由 DSH 审批与执行。

## 4. 检查实际调用

打开 **路由轨迹**，展开本次记录：

- 实际 provider、模型、推理等级与用途是否符合固定角色；
- 是否只有预期的执行调用，没有额外 Task Judge 或审核；
- 工具调用与结果是否配对；
- 参考估值、按量现金与待核对预留是否分别列出；
- 开始时间、总耗时与首字时间是否可见。

<figure class="doc-screenshot"><a href="/screenshots/planning-history.jpg" target="_blank" rel="noopener"><img src="/screenshots/planning-history.jpg" alt="规划路由真实轨迹示例：Advisor 策略的执行与审核记录"/></a><figcaption>轨迹页示例（2026-10-03 一次 Advisor 真实记录）。Static 记录更简单：应只有执行调用，没有 Judge 行。逐字段读法见[运行记录](traces.md)。</figcaption></figure>

## 5. 再试其他路线

- 工具任务需要逐轮调整模型：[Stage](strategies/stage.md)。
- 每个任务从多个模型中选一个：[Task](strategies/task.md)。
- 最终回复必须审核与复审：[Advisor Gate](strategies/advisor.md)。
- 先尝试起始模型、必要时锁定接管：[Escalation](strategies/escalation.md)。
- Task 初选后允许临时切换：[Composite](strategies/composite.md)。
- 研究显式任务拆分：[自动路由](automatic.md)。

每次新任务冻结设置。运行中的工具续接和追加指导沿用现有预算与计数；保存设置供下个任务使用。
