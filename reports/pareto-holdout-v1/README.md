# Pareto 留出实验证据

本目录归档 #53 与 #76 阶段四正式留出实验的冻结件与排练证据。正式付费执行尚未获用户
授权，当前全部产物均为零调用。

## bound-01（已失效，保留原样）

- 2026-09-18 随 PR #96 冻结：12 题留出 × 3 臂 × 3 重复，`max_calls` 612、
  `online_afp_ceiling` 29523.4848、`offline_afp_ceiling` 14376.96。
- 冻结后 PR #97（隐私放置 A2）改动了 `src/refractrouter/` 下五个被冻结哈希绑定的文件
  （`agent.py`、`application_config.py`、`dynamic_decomposition.py`、
  `task_execution.py`、`task_runtime.py`）。在当前实现上以 bound-01 重放排练会在
  哈希绑定校验处触发 `ValueError: frozen protocol or implementation changed`，
  该冻结件不再可用于执行。
- 按协议不追改已冻结件，保留作为历史证据。

## rehearsal-01（bound-01 的排练，保留原样）

- 2026-09-18 随 PR #96 完成：108 次运行全部走通编排、MoA 门槛接线与包络计数，
  `actual_model_calls` 0、`actual_afp` 0，不发起网关请求。

## bound-02（当前有效冻结）

- 2026-09-18 在 main（`3c7520e`）上重新冻结，选择与 bound-01 完全一致：
  12 题留出 × 3 臂（`direct-strong`、`task-selector`、`direct-or-dag`）× 3 重复，
  `max_calls` 612、`online_afp_ceiling` 29523.4848、`offline_afp_ceiling` 14376.96。
- 冻结过程零模型调用、零 AFP。

## rehearsal-02（bound-02 的排练，当前有效）

- 2026-09-18 完成：108 次运行、状态 completed、`actual_model_calls` 0、`actual_afp` 0、
  墙钟约 40.2 秒；模拟客户端不发起网关请求。
- MoA 门禁证据复用 #96 的合流材料评审（12 题全部共识 pass）与 moa-purpose-06
  用途确认，`execute()` 的哈希绑定与门槛断言全部通过。

## live-01（正式实跑，2026-09-18，已授权执行）

- 以 bound-02 实跑：108 次运行、397 次真实调用、312.7503 AFP（生产 171.3863、
  评审 141.364）、零重试、墙钟约 52.6 分钟；95 交付、11 扣留、2 失败。
- MoA 输出评审及定向补审已完成。三个臂均未达到 90% 质量门槛，
  `confirmed_pareto_frontier` 为空；AFP per accepted task 分别为 `direct-strong` 16.00、
  `direct-or-dag` 20.13、`task-selector` 33.36。
- 主对比：`direct-or-dag` 对 `direct-strong`、`direct-or-dag` 对 `task-selector`；
  主指标为 AFP per accepted task，时间与墙钟只作探索诊断。
- 质量失败归因发现 `direct-or-dag` 的 36 次运行中只有 1 次真正产生多节点 DAG，且该次
  失败；现有臂间差异不能解释为 DAG 拆分收益。详见 `failure-attribution-v1/README.md`。
- 原始运行说明见 `live-01/README.md`，最终统计见 `live-01-analysis-v5.json`。
