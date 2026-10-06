# 自动路由有限验收记录（2026-10-06）

## 验收范围

本批使用确定性模拟模型和宿主工具核对控制流程；不发起付费调用。只证明被测试的
选路、预算、工具续接和记录行为，不把模拟回答当作真实任务质量或成本收益证据。

| 场景 | 预期行为 | 对应检查 |
|---|---|---|
| 简单问答 | 直接执行，低风险时不增加规划或评审调用 | `test_simple_v4_preflight_then_live_uses_one_worker_and_skips_judge` |
| 单项工具任务 | 宿主工具只执行一次，模型续答后保留评审 | `test_single_tool_task_executes_without_a_planner_call` |
| 顺序依赖任务 | 保留完整任务和最终评审，不进入 DAG | `test_structural_decisions_execute_full_request_without_planner_and_keep_review[COUPLED]` |
| 明确可拆分任务 | 允许生成 DAG，并比较直接与拆分路线的成本与准入 | `test_live_second_level_uses_dag_when_qualified_profiles_save_cost`、`test_live_second_level_can_discard_a_costly_dag_without_repeating_planner` |
| 拆分无法确定 | 不仅凭关键词调用 planner，完整任务直接执行并评审 | `test_current_uncertain_judge_does_not_turn_keywords_into_paid_planning`、`test_structural_decisions_execute_full_request_without_planner_and_keep_review[UNKNOWN]` |
| 现金与参考价格 | 节点和工具续接、最终评审各自通过现金与参考额度检查 | `test_runtime_blocks_unaffordable_route_before_any_model_dispatch`、`test_live_comparison_stops_after_planner_when_tool_cash_is_insufficient`、`test_second_level_rejects_metered_evaluation_cash_shortfall` |
| 候选解释 | 逐模型记录质量画像和容量原因，轨迹可展示旧记录与无路线比较的运行 | `test_each_configured_model_reports_why_it_cannot_execute_a_node`、插件轨迹契约测试 |

路由比较计入已发生的规划费用、节点执行预测、允许的宿主工具续接额度和共享的
最终评审预测。DAG 的汇总工作属于生成计划中的最终执行节点；比较结果来自模型画像
先验，不能据此声称不同路线已有等质实测。

## 验收结果与边界

完整 Python 回归 1721 项通过、5 项子测试通过，耗时 223.75 秒。完整套件收集后
补入一项现金二次准入的完整流程用例，单独复验现金相关 14 项通过。插件重新构建后
196 项契约测试通过；相关 Python 测试 55 项通过。
未新增真实模型调用、未调整现有 DSH 配置。PR #186 的既有远端检查通过；
当前批次新增代码尚待推送和远端检查。

用户当前安装的核心 0.16.2、插件 0.30.2 尚不包含本批修改。实际界面及真实
模型表现需要在合并与更新安装后单独核对；本报告不将模拟验收写成安装验收。
