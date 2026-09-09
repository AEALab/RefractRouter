# 历史基准验证交接

本交接处理 #1、#5、#6、#7、#8、#22、#36。当前结论为 `incomplete`，没有完成
pilot、final 或正式人工抽检。应用集成、#32 与 #38 的结果保留各自范围。
2026-09-10 的零调用证据、调用数和预算见
[本轮报告](../reports/issue-backlog-20260910/README.md)。

## 依赖与完成条件

| Issue | 已具备的证据或入口 | 尚缺的验收 |
|---|---|---|
| #36 | K3 基线、参考路线、21 份探针、已通过的 GLM 校准；新增独立评审入口 | 21 份评分、可行性决定、组合 DAG、两份最终盲评及费用汇总 |
| #22 | 最新 v2 三轮 63 格节点矩阵与三条完整混合路线；新增零调用复核 | 第三轮最佳单模型比较不完整；需新的、预先冻结的有效三轮对照 |
| #5 | 5 train / 5 test、七策略、三轮调用计划与历史用量情景 | #22 的完整对照、独立授权、真实 pilot 及进入 final 的决定 |
| #6 | 10 train / 10 test、七策略、三轮预检 | pilot 通过、最终配置与预算冻结、真实 final |
| #7 | 绑定四个产物的人工审核模板生成与严格 finalizer | 真实 final 产物及人工填写的四份审核 |
| #8 | 自动复算的阶段预算、原始证据链接、当前不完整结论 | 完整 final、人工审核、DSH evidence 和最终中文报告 |
| #1 | 汇总上述依赖和范围 | 子项达到原验收条件后更新总体结论 |

#36 是独立单任务对照，不能代替 #22 的三轮对照；#22 放行 pilot 所需的是完整、可解释
的证据，不要求预设正收益。失败样本不能补零、删去或跨轮拼接。历史 v2 的已知拒绝排除
协议保持原样，新预检没有给旧路线增加回退或更换评分标准。

## 独立 worktree 与冻结版本

开发分支为 `codex/issues-1-5-6-7-8-22-36`。继续 #36 生产阶段时使用冻结提交
`89ad6323b89b654763b6ef3651d0c53af96a3370`，例如：

```bash
git worktree add --detach /tmp/refractrouter-issue36-frozen-89ad632 \
  89ad6323b89b654763b6ef3651d0c53af96a3370
```

本轮已建立此 worktree 并验证 `compose` 预检通过。若使用另一个工作区的 Python，必须
将冻结工作区的 `src` 放在 `PYTHONPATH` 首位，避免导入新代码。生产执行仍经该版本
DSH 原生插件入口；独立评审工具在开发版本读取原始材料，不迁移生产代码快照。
不得为使测试通过而登记未经审查的兼容白名单。已有精确迁移单元测试继续验证登记规则；
当前 Python 和 TypeScript 回归均明确拒绝将历史基线迁移到未经登记的新代码。

## #36 独立评分

预检只读取冻结材料与现有校准，生成每个样本的准确请求、材料哈希、调用范围及费用预留。
不再次生成校准、K3 基线或节点探针：

```bash
uv run python experiments/review_k3_outputs.py \
  --input-dir reports/v0.5-k3-resume-admission-2/output \
  --calibration-reviews reports/v0.5-glm-calibration/paid-admission-1/reviews.json \
  --output-dir /tmp/k3-node-review-preflight
```

获批后使用完全相同的输入、校准与代码，并写入新目录：

```bash
uv run python experiments/review_k3_outputs.py \
  --input-dir reports/v0.5-k3-resume-admission-2/output \
  --calibration-reviews reports/v0.5-glm-calibration/paid-admission-1/reviews.json \
  --approved-preflight /tmp/k3-node-review-preflight/preflight.json \
  --execute-paid-run --max-review-cost 210 \
  --output-dir /tmp/k3-node-reviews
```

范围为最多 21 次 GLM-5.3 `/api/plan/v3` 独立节点评审，串行、120 秒超时、底层零重试。
预留 209.72025 AFP，建议额度 210 AFP；按请求 UTF-8 字节数加余量计算输入预留，
输出上限 8192。额度检查不能取代服务端用量控制。当前文档和预检不构成调用授权。

只将公开任务、来源、单份样本、上游和冻结 rubric 交给评审模型，不包含私有映射或费用。
原始输出中的模型自述仍可能破坏盲化。每项必须有维度分、原文引用和中文理由；最终报告
另需实质比较、取舍和结论三项布尔检查。非法 JSON、样本错配、原文不匹配、截断、
未知用量或证据写入异常都停止后续调用，不自动补跑。缺失评分保持缺失。

成功时 `reviews.json` 可直接交给冻结生产入口，含原校准及 `nodes` 评分；失败时保留
`responses.ndjson`、`partial-reviews.json` 与错误，不生成可导入的完整评分包。
节点选模仍由原 Python 核心按 `max(85, 最佳分 - 5)` 门槛选择最低费用候选。
无可行路线应保存明确停止结论；可行时经单独获批的 DSH `compose` 执行七节点 DAG。

`compose` 成功后，将新材料目录传给同一评审入口，自动识别两份最终材料并生成新的
零调用预检。最终评审额度按届时的实际材料冻结，不从 21 次节点额度自动扩展。
随后在冻结 worktree 用 `run_k3_baseline.py --stage finalize` 零调用汇总。
最终路线费用、参考/探针费用、DAG 首次使用费用、独立评审与 DSH 外层必须分列；
历史未知费用保留未知。单轮结果依然为 `Insufficient-evidence`。

## #22、pilot 与 final 的预检

三轮用于观察任务内波动；训练只执行一次。预检命令如下，`phase` 依次为
`dry-run`、`pilot`、`final`，各使用新目录：

```bash
uv run python experiments/run_real_v0_1.py --phase pilot --repeats 3 \
  --manifest data/model-manifests/volcengine-agent-plan.json --max-retries 0 \
  --selection-policy exclude-known-contract-rejections-v2 \
  --output-dir /tmp/refractrouter-pilot-preflight
```

生产调用数包含训练、完整单模型路线、独立节点探针及组合路线；评审包含训练节点、
探针节点和最终报告。生产调用中的训练不可重复相加。详细公式与历史均费情景见
[预算核对](../reports/issue-backlog-20260910/budget-analysis.json)。旧单轮 USD 估算及
已结束实验的 AFP 余额不构成这些新阶段的预算。

已冻结的 pilot 测试任务 `report_011` 至 `report_015` 也在 final 测试集中。
训练与测试拆分保持不交叠，但 final 不能称为全部未观察的新测试任务。如果依据 pilot
修改策略、prompt 或阈值，应披露观察范围，另行设计未观察验证集；不能静默重写 v0.1
任务集合或把同一题的重复当成独立任务。

## 正式人工抽检与最终报告

从真实 final 产物运行 README 中的 `--prepare-audit`，得到 v0.2 审核格式。
审核对象固定为 `report_011`、`report_020` 的第一轮 task-oracle 与 node-oracle，共四份。
人工按 v0.1 五维 rubric 填写总分、维度分、逐条主张/来源判断、原文依据、理由、姓名或
审核者标识及带时区时间。AI 模拟评分不得填入正式人工审核。

finalizer 核对整个原始索引、四个运行哈希、任务/策略/轮次身份及独立评审分数。
拒绝 NaN、Infinity、布尔分数、重复/缺失样本、修改后的 rubric 或差异门槛、
未定位的引用以及未核对的主张。原文核对无法自动证明人工真的阅读了来源，也不认证身份；
仍需人工审核实际来源、引用哈希、遗漏及事实错误。

固定 10 分门槛包含等于 10 的情况。任一差异大于 10，或有严重事实错误时，审核失败。
已有完整 oracle 的 Go 会因此变成 No-go；oracle 本来证据不足时最终保持 `incomplete`。
结果及提交审核文件写入冻结输入之外的新目录，禁止覆盖原始产物或旧审核结果。

#8 的报告须同时复算原门槛：成本差小于 5% 且质量提升至少 5 分，或质量差小于 2 分
且生产费用降低至少 20%；共同检查 p95 时延不超过 120%、成功率不退化和评审覆盖完整。
并解释 statistical-q 距 oracle 的差距。当前尚无真实 pilot/final，不为这些指标填入模拟值。
