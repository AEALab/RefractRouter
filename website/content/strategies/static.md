# Static · 静态

Static 在新任务开始时选一个执行模型，工具续接沿用选择。它不调用 Task Judge 或审核器。

<figure class="doc-diagram"><img src="/strategy-static.svg" alt="Static 在任务开始固定或按权重抽样一次，任务内保持"/><figcaption>Static 是最简单的策略：选一次、用到底，零 Judge 零审核。</figcaption></figure>

## 当前设置的真实含义

| 模式 | 当前实现 |
| --- | --- |
| Fixed | 固定使用共用设置中的“高效执行模型”及其推理等级 |
| Random | 按高效／强执行两个角色的冻结权重，每任务随机选择一次 |

::: info 当前 Random 的范围
当前版本不是任意数量模型的独立 Static 池。Task／Composite 有多模型池，Static 随机仍是
两个角色的加权对照。这里如实记录实现边界，不把计划中的产品形式描述为已完成。
:::

“固定高效角色”是程序默认值，不表示用户曾主动配置，也不表示 Router 已经判断这个
模型对任务最合适。你选择哪个模型承担该角色，Static 就使用哪个。

## 哪些配置必要

Fixed 只需要高效执行角色、真实推理参数、价格、能力、数据域和预算。
不需要强执行、任务判别和 Advisor 审核角色。

Random 需要两个执行角色及权重。权重 `1:1` 表示同等抽样概率；`3:1` 表示 75% 与 25%。
随机种子便于复现对照，不是模型质量或费用参数。续接不会重新抽样。

## 典型用途

先验证真实模型和原生工具，再作为其他策略的固定基线。随机模式适合实验，
不能保证每次选择质量达标或更省钱。

## 系统设置示范

打开 **设置 → 插件 → RefractAgent 规划路由 → 正在编辑的策略：Static**。

<figure class="doc-screenshot compact"><a href="/screenshots/dsh-20261014/strategy-static-settings.png" target="_blank" rel="noopener"><img src="/screenshots/dsh-20261014/strategy-static-settings.png" alt="实际 Static 设置：固定或随机模式、随机种子 4、两角色权重各 1"/></a><figcaption>2026-10-14 实际界面：模式下拉框决定固定或随机；种子与权重只参与随机路径。</figcaption></figure>

截图里的种子 `4` 和权重 `1:1` 是配置示例。先在共用模型资料中配置两个角色，再选择
随机模式；角色模型与推理等级一并冻结。若只希望验证一个模型，选择 Fixed 即可。
按权重抽取的是每个新任务的执行器；同一任务读文件、运行测试、总结时沿用它，
不会每轮重新抛一次硬币。

## 轨迹应该看到什么

固定／随机理由、选中的真实模型与推理等级、调用用途、费用和耗时。
如果 Fixed 产生额外 Judge 调用，需核对是否实际选择了其他策略。

### 真实案例

2026-09-29 验收批次的 static-01 任务（`reports/dsh-strategy-stability-20260929-v3/records.jsonl`）：
用户要求“只回复 `STATIC_01_OK`，不要调用工具，也不要添加其他文字”。
冻结随机种子选中 `deepseek-v4.1-flash`，1 次受管调用，费用 3.116 AFP，首字 1.79 秒，
总延迟 1.80 秒，决策原因 `static-random-selected`。同一批次 12 项 Static 任务里，
随机策略同时覆盖了 `deepseek-v4-flash`（如 static-02：0.622 AFP）与 V4.1 两条执行路线。

业务场景可用“读取已有说明并改写成三条要点”作为固定基线：先记录固定模型的质量、
总费用和等待，再与其他策略比较。随机模式的用途是产生对照，抽到便宜模型不等于任务已验收。
本页截图是当前配置示范；案例调用使用[历史冻结配置](../planning.md#六策略真实运行案例)。
