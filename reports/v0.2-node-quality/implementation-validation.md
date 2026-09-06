# 节点质量与重复对照验证

跟踪：[issue #22](https://github.com/AEALab/RefractRouter/issues/22)。
日期：2026-09-06。本文记录代码与离线验证，尚无本协议的真实模型分数或 Go 结论。

## 评估协议

候选池固定为 DeepSeek V4 Flash、MiniMax M3、DeepSeek V4 Pro；独立评审为 Kimi K3。
节点不再以英文关键词、引用出现次数或旧 verification 文本前缀评质量。
确定性检查验证格式、来源 ID/title/hash、真实标题覆盖和验证结论的机械一致性，
只施加质量上限；机械检查通过不能证明语义正确。独立评审使用冻结的
`data/judges/node-v0.2.md`，评正确性、证据支持、完整性和下游可用性。

每个任务每轮执行三种单模型完整 DAG，用 strong-all 的直接上游输出分别探测三模型。
保存 7×3 的原始输出和评审矩阵，节点选最高有效语义分，同分选该次实际成本更低者。
组合后重新执行完整 DAG，再独立评估最终报告。局部贪心选择不能证明全局最优；
不能为了出现混合或 Go 而修改选模结果。

node-oracle 与固定 node-type-rule 分别对照 strong-all 和 task-oracle。
后者是本任务本轮三个实测单模型中最终质量最佳者，不等同于最贵模型。
报告按 task/repeat 配对，保存逐轮分差、成本差、延迟差和均值/标准差，
并区分相同分配造成的生成/评审波动。三轮是描述性观察的最低设计，不是显著性证明。

节点请求或评审失败时保留失败单元、停止生成 node-oracle 分配；没有静默便宜模型回退。
缺少三个单模型的最终评审时，task-oracle 不提供有效对照。
不完整证据、少于三轮或两种 oracle 始终同分配均标为 Insufficient-evidence。

## 已完成的零模型调用验证

- 全套测试：`uv run pytest`，73 passed，5 subtests passed（含 Node 合约测试）。
- `tests/test_node_quality.py` 的三轮离线完整执行产生 63 个矩阵单元、9 份单模型结果、
  12 组配对比较，168 次 fake 生产调用及 78 次 mock 评审调用；未请求任何真实 endpoint。
- 回归覆盖中文分析、重复/伪造来源、错误 JSON、正文冒充章节标题、验证结论、
  不支持的证据、非有限/布尔评分、截断评审的费用记录、预算耗尽、缺失评审时禁止回退。
- canonical fake-model DSH wrapper 验证：pass。
- Agent Plan 三轮 DSH wrapper preflight：pass，未使用付费开关；精简结果见 `preflight.json`。

## 尚待批准的真实执行

调用固定 Agent Plan `https://ark.cn-beijing.volces.com/api/plan/v3`，重试为零。
最多 168 次生产 + 63 次节点评审 + 15 次最终评审 = 246 次 benchmark 调用。
保守估算生产 1126.54 AFP、评审 1262.98 AFP，共 2389.52 AFP。
建议调用准入预算为生产 1200、评审 1300，DSH 外层 Flash 另留 5，共 2505 AFP。
逐请求准入使用 token 估算，单个请求的实际结算可能超过预留值。

此前 495 AFP 授权对应已完成的 issue #19 单轮；本协议新增调用尚未授权。
获批执行后才能将真实三模型矩阵与重复对照证据提交到独立目录，更新 issue #22 与 #5。
