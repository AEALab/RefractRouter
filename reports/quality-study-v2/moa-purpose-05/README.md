# MoA 用途确认评审第 5 轮（Issue #79 第三项门槛）

本目录由 `experiments/run_moa_review.py --kind purpose` 生成，评审对象是控制性探索的
`statistics_policy` 是否与本研究用途相符。运行前已按冻结预检绑定上限，运行中不重试。

## 载荷

- 研究目的描述：`RESEARCH_PURPOSE` 常量（PR #94，合并提交 `5434636`），说明本批为控制性探索、
  不做总体确认性推断、不宣称用户可接受性。
- 统计策略：`statistics_policy` sha256 `56694f60eec90621d45087ebe2da4318d574f318dd9a184abd6891ee1649e0d2`。
- 评审策略：`policy_sha256` `2ae5b345f61a9a6be896663ff23f09499d98185ca6e13f7ceae3de0a50c1b902`。
- 冻结协议：`reports/quality-study-v1/final-live/frozen.json`。

本轮相对第 4 轮（`../moa-purpose-04/`）只多出研究目的描述；第 2 轮及以前只给哈希，
评审因证据不足全部判 pending，故第 4 轮起把实际策略内容一并写入载荷。

## 调用

| 阶段 | 评审 | 模型 | thinking effort | 结束码 | 用时（秒） | 判定 |
|---|---|---|---|---:|---:|---|
| 初审 | ds-deepseek-v4-pro | `ds/deepseek-v4-pro` | max | 0 | 76.5 | pass |
| 初审 | claude-opus | `opus` | high | 0 | 27.0 | pending |
| 升级 | codex-ark-kimi-k3 | `ark/kimi-k3` | high | 0 | 32.7 | pass |
| 升级 | claude-opus-max | `opus` | max | 0 | 308.2 | pass |

## 结论

- 逐 criterion 共识：`overall = pass`；分歧 criterion 1 项（升级后两票一致通过）；失败记录 0 条。
- 初审分歧集中在门槛的冻结时点与判定语义：按精确区间界解释时，12 题留出全部通过也达不到 0.9
  的概率下界，因此初审要求载荷写明判定规则。升级评审接受现有表述并判 pass，其中一位同时提示
  需要把该判定语义补进策略文本。
- 冻结文档 `docs/quality-study-freeze.md` 第 95–100 行已经把 90% 定义为研究操作观察门槛，
  与总体置信保证区分开，并采用精确二项反演与家族错误控制；该段文字未进入本轮载荷，
  是初审提出疑问的直接原因。

## 边界

- 本评审是跨 provider 多模型共识，`reviewer_identity_verified=false`，不构成真人审查，
  也不证明真实用户接受度；`human_gate` 仍要求真人用途确认。
- 汇总账号为 `external-cli-account`，AFP 记为未知，不参与 AFP 成本比较。
- `artifact-index.json` 记录本目录除索引自身外的全部文件摘要。
