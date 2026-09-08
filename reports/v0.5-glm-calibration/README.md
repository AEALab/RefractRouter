# GLM 独立校准的零调用准入材料

下一步范围已收敛到 GLM-5.3 对两份冻结报告各评审一次。
本归档只有预检，不包含真实评分；新增真实请求和付费支出均为零。

- [主实验新预检](main-preflight/README.md)：新代码快照及校准材料，旧归档保持不变。
- [两次请求与费用预留](calibration-preflight/preflight.json)：固定模型、开启思考、零重试、
  每次输出上限 8192 token；不向评审模型提供历史分数或样本预期标签。
- [校准预检结果](calibration-preflight/summary.json)：保守预留 23.4693 AFP，实际调用零次。
- [准入方案](../../docs/independent-calibration-admission.md)：请求约束、费用和停止条件。

完整 `uv run pytest` 为 195 项通过，其中新增校准测试 11 项。
覆盖两次模拟评审、真实调用前的方案与预算检查、盲化、无效 JSON、截断、错误引用、
缺失用量、超时留证，以及识别不了负例时拒绝校准。测试不调用付费模型。
既有 DSH TypeScript 构建与契约也包含在完整测试内；本次没有修改插件接口。

官方文档重新核对了 GLM-5.3 的计费与思考模式，来源和读取内容哈希见
[文档核对记录](source-verification.json)。模型可列出不代表账户请求已验证成功，
也不代表独立评分已经校准，当前保留待验证状态。

待申请范围：**仅 GLM-5.3 两次校准请求、零重试、评审额度 25 AFP**。
预留使用提示字节数和输出上限，是保守控制，不能作为服务端硬账单上限。
发生截断、非法评分或用量未知时停止；无有效用量不把费用记成零。
校准通过也不自动启动 K3 基线、节点探针或 DAG 生产实验。

以下是获批后的执行命令，当前未执行：

```bash
uv run python experiments/run_blind_calibration.py \
  --input-dir reports/v0.5-glm-calibration/main-preflight \
  --approved-preflight reports/v0.5-glm-calibration/calibration-preflight/preflight.json \
  --execute-paid-run --max-review-cost 25 \
  --output-dir reports/v0.5-glm-calibration/paid-admission-1
```

本阶段通过 Python 外部评审入口调用专用 Agent Plan 客户端，不新增外层模型请求。
不得将预检文件或上述命令视为用户已授权执行。
