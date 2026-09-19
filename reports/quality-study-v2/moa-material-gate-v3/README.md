# MoA 材料评审合流记录

本目录由 `experiments/merge_moa_records.py` 生成，是付费留出实验 MoA 门槛的唯一读取文件。
合流不发起模型调用，也不改写任何评审记录，只做口径校验、去重与冻结顺序重排。

- MoA 策略哈希：`b591b0f80635a0d771e7c0360581dba3f97b7638c6c7e1ef26494be2fc3d0d92`
- 记录数 12：过门禁 11 题，未过门禁 1 题
- 共识分布：{'pass': 11, 'fail': 0, 'pending': 1}
- 未过门禁任务：['analysis-04']
- 无效评审记录数 0；升级 criterion 数 2

## 分片来源

- `reports/quality-study-v2/moa-material-gate-v2/moa-results.json`（sha256 `3a41d56bfbd9ceef8e9009ec2db89f48314ffb8f0edf828291535bb2b627a271`，12 条）
- `reports/quality-study-v2/moa-material-gate-v2-retry/moa-results.json`（sha256 `d0e44d0ba61d9b816c4ed7cf224d64b35e97893a7a4e52ad4d59cd97d3c661ba`，2 条）

## 门槛口径

- 逐 criterion 两位初审一致则采用；不一致升级两位重审；升级后仍不一致记 pending。
- 只有六项 criterion 全部共识 pass 的记录才算该题过门禁；pending 与 fail 都不放行。
- 确定性关键检查仍然一票否决，MoA 共识不能覆盖确定性 fail。
- 本门槛是本地多模型共识门槛，不是真人审查，也不能证明用户可接受性。

## 被覆盖的旧记录

同一任务的定向重审会取代旧结论；下表逐条留痕，旧记录仍保留在分片文件中。

- analysis-04：`reports/quality-study-v2/moa-material-gate-v2/moa-results.json`（pending） → `reports/quality-study-v2/moa-material-gate-v2-retry/moa-results.json`（pending）
- rules-04：`reports/quality-study-v2/moa-material-gate-v2/moa-results.json`（pending） → `reports/quality-study-v2/moa-material-gate-v2-retry/moa-results.json`（pass）

## 备注

新阵容（policy b591b0f8）重跑：gate-v2 10 过 2 pending，retry 重审 rules-04 通过；analysis-04 在「公共输入未泄漏参考答案」上初复审均分裂待定。

## 记录在案的显式例外（human-tiebreaks.json）

- analysis-04 的「公共输入未泄漏参考答案」在 MoA 上平票 pending（deepseek/kimi pass，
  claude opus/max pending）。冻结机械规则没有平票机制，且该题材料已绑定已完成的 live-01
  实验、不可修改。
- 研究负责人 Acrobaticat 于 2026-09-20 定向裁决：不构成实质泄漏（西站无旧流程基线，
  unknown 可直接由材料推出；east_change 数值与 pooled 结论未被提示），按 pass 放行。
- 本裁决是对冻结机械规则的显式例外，不修改规则本身；裁决人、依据与绑定哈希逐条留痕，
  供复核与审计。
