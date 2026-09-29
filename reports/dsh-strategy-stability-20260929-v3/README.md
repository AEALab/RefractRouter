# DSH 六策略稳定性验收

验收日期：2026-09-29。

本批次扩大 Static、Stage、Task、Composite、Advisor 和 Escalation 的真实 DSH 验收次数，
重点检查策略能否在独立任务中稳定完成选模、工具续接、审核与费用结算。Router 只负责模型
路由与模型费用；工具执行、权限、会话和任务推进继续由 DSH 负责。

## 冻结范围

- DSH `0.1.5-rc.3`、插件 `0.29.0`、Python 核心 `0.15.4`。
- 12 个 Static、24 个 Stage、20 个 Task、24 个 Composite、24 个 Advisor、
  24 个 Escalation，共 128 个独立任务。
- 理论最坏路径上界 4685.3888 AFP；用户授权本批次最多 5000 AFP。
- 最多 340 次受管模型调用、每任务 5 分钟、零 HTTP 自动重试、关闭委派和媒体。
- 模型：`deepseek-v4-flash`、`deepseek-v4.1-flash`、`glm-5.3-flash`。
- 所有任务、提示、调用上限、配置摘要和停止规则见 [preflight.json](preflight.json)；
  执行顺序见 [schedule.json](schedule.json)。

## 正式结果

v3 正式批次 **128/128 全部成功**，发生 268 次受管模型调用，实际使用
**215.58545 AFP**。每个任务均产生唯一 planning 记录，全部调用用量已确认并结算，未观察到
HTTP 自动重试。

| 策略 | 成功数 | 受管调用 | AFP | 验收行为 |
|---|---:|---:|---:|---|
| Static | 12/12 | 12 | 19.96470 | 冻结随机种子与权重，实际选择两条执行路线 |
| Stage | 24/24 | 48 | 30.12820 | 每项一次宿主工具调用，依据新证据保持高效模型 |
| Task | 20/20 | 40 | 15.48340 | 每任务一次 Judge，随后固定所选执行器 |
| Composite | 24/24 | 72 | 33.82835 | 一次 Task 选模，工具续接由 Stage 判断且不重新分类 |
| Advisor | 24/24 | 48 | 88.08255 | 候选缓冲，独立审核批准后才交付 |
| Escalation | 24/24 | 48 | 28.09825 | 起始候选缓冲，Judge `PROCEED` 后才交付 |

实际调用分布为 `deepseek-v4-flash` 171 次、`glm-5.3-flash` 68 次、
`deepseek-v4.1-flash` 29 次。Task 和 Composite 的常规任务均在满足质量门槛后选择了成本更低的
Flash；Static 的冻结随机策略同时覆盖 Flash 与 V4.1 Flash。

逐任务摘要、实际模型、决策原因、费用、首字时间、总延迟及原始证据哈希见
[records.jsonl](records.jsonl)，汇总见 [summary.json](summary.json)。本机保留每项 DSH stdout、
stderr 和原始 planning 记录；仓库只保存紧凑记录与 SHA-256，避免重复提交 128 份宿主系统提示。

## 失败批次与修正

历史失败没有从统计中删除：

1. v1 首项正确回复 `STATIC_01_OK`，但 DSH headless 没有模型菜单，未传递
   `rr:static`，Router 回退到默认 Stage。批次在 1 次调用、0.62245 AFP 后停止。
2. v2 改为在每个 headless patch 中冻结 `defaultStrategy`，六策略冒烟的前五项通过。
   Escalation 使用 `deepseek-v4-flash` 审核时虚构了一个不存在的证据 ID，严格合同拒绝判定；
   批次在 12 次调用、11.39970 AFP 后停止。
3. v3 将 Escalation Judge 恢复为已有真实验收证据的 `glm-5.3-flash`，六策略冒烟及
   后续 128 项正式任务全部通过。

三批合计发生 281 次真实受管调用、使用 227.60760 AFP。v1 和 v2 的预检、紧凑记录、
汇总及冻结 patch 分别保存在相邻的 `v1`、`v2` 目录。

## 自动路由分支

真实 DSH 批次覆盖各策略的常用路径：Static 随机选模、Stage 证据续接、Task 一次分类、
Composite 分类后逐轮判断、Advisor 审核放行，以及 Escalation 审核放行。真实模型不应为了
测试而被诱导产生错误，所以重复失败升级、返工和强模型接管使用确定性宿主与上游夹具验证。

本轮另运行 13 项关键分支测试，覆盖：

- Stage 重复可信失败升级、强模型保持、旧证据去重及降回；
- Composite 接管、保持与返回常用模型；
- Advisor `REDO`、工具续接、复审和第二次不通过时停止；
- Escalation `DEFECT`、`STALL`、`UNCERTAIN`、连续停滞和强模型固定接管。

## 回归结果

- `uv run pytest -q`：1412 passed，5 subtests passed。
- DSH 插件 TypeScript 类型检查：通过。
- DSH 插件构建：通过。

## 结论边界

本次证明六种策略能在当前 DSH headless 接入中稳定完成 128 个受控文本与原生工具任务，
并按各自合同记录自动路由轨迹、真实模型、费用与时延。它不证明这些策略在开放任务上普遍
优于 Static，也未覆盖图片、影片、子 Agent 共享预算或自然发生的错误候选。收益比较与更复杂
的开放任务质量验收应使用独立冻结的数据集和判分协议。
