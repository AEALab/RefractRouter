# Task 本地 Judge 独立资料研究保留题

## 协议与证据

本批次使用 `data/benchmarks/task-research-holdout-v1.json`，在三份隔离工作区
执行同一个此前未运行的 `research-compare-search` 冻结任务。两条固定路线与
`Task choice-v2` 使用同一资料、工具权限和评测规则；Task 的短能力卡只引用
前一批四个已完整结束的校准记录。零调用预检见
`task-research-holdout-preflight-v1.json`，原始结构化运行指标见
`task-research-holdout-paid-v1-records.jsonl`。带完整请求正文的 DSH 证据留在
本机 `/tmp/refractrouter-task-research-holdout-20260926-d/`，不提交到仓库。

## 实际结果

| 路线 | DSH 完整结束 | 确定性检查 | 模型调用 | AFP | 端到端 |
|---|---|---|---:|---:|---:|
| 固定 `deepseek-v4-flash` | 是 | 通过 | 5 | 2.97170 | 39.3 秒 |
| 固定 `deepseek-v4.1-flash` | 否，达到 6 次调用上限 | 中途答案文件通过 | 6 | 22.67525 | 35.7 秒 |
| Task `choice-v2` | 是 | 通过 | 4 | 12.97125 | 28.2 秒 |

本次 Task 真实加载本地 Laya，1 次 `Choice`、1 次 forward，输入 155 tokens；
冷启动约 1029 ms，判别约 135 ms。原始概率为 v4 Flash **0.6871**、
v4.1 Flash **0.1981**、`insufficient` **0.1148**。由于冻结接受门槛为 0.8，
判别被记为不确定，按配置使用 v4.1 Flash 备援；其后四次执行调用全程固定该
模型。路由轨迹标明 `task-local-choice-v2` 与 `choice-probability`，费用和
候选决策均有独立记录。

## 解释边界

这条保留题证明：本地 Judge、DSH 原生 Agent 续接、指定备援、答案文件、
确定性检查和 AFP 结算在真实路线上可以贯通。它也表明当前 0.8 门槛在这题上
拒绝了 Laya 更倾向的 v4 Flash，而固定 v4 Flash 本次完整交付且花费较少。
固定 v4.1 Flash 的中途答案通过检查，但 DSH 以调用上限错误结束，不能当作
完整成功。三条路线的首字等待与端到端时延均为单次观察，不做稳定性结论。

只有一条保留题，且两个模型推理档位分别为 `low` 与 `high`。不能用本次结果
估计 Judge 的总体正确率，也不能据此调低 0.8 默认门槛或声称 Task 的质量／
成本收益。若继续校准，须先冻结多条新的独立保留题和成功判据，再决定门槛；
本题不得在调参后重跑并与原结果混算。

## 累计额度

本批次三条路线确认结算 **38.6182 AFP**。连同前两批确认结算的
78.6968 AFP，目前可确认模型费用合计 **117.315 AFP**。前一批还有
**16.55475 AFP** 未知用量预留；若按全额占用计算，累计为
**133.86975 AFP**，低于用户授权的 1000 AFP。该预留不是已证实扣费。
