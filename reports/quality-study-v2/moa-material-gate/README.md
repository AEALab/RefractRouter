# MoA 材料评审合流记录

本目录由 `experiments/merge_moa_records.py` 生成，是付费留出实验 MoA 门槛的唯一读取文件。
合流不发起模型调用，也不改写任何评审记录，只做口径校验、去重与冻结顺序重排。

- MoA 策略哈希：`2ae5b345f61a9a6be896663ff23f09499d98185ca6e13f7ceae3de0a50c1b902`
- 记录数 12：过门禁 12 题，未过门禁 0 题
- 共识分布：{'pass': 12, 'fail': 0, 'pending': 0}
- 未过门禁任务：[]
- 无效评审记录数 0；升级 criterion 数 0

## 分片来源

- `reports/quality-study-v2/moa-material-04/moa-results.json`（sha256 `a7648350f158bdf448e7e7bd5d4c38acacb27b3ddaf73bc2ab4a3613477e8be0`，18 条）
- `reports/quality-study-v2/moa-material-05/moa-results.json`（sha256 `0aa6d23cb5376b56db4cb0d05ad595b0152e343342ac85cf7f3fd7add2f08407`，2 条）
- `reports/quality-study-v2/moa-material-06/moa-results.json`（sha256 `dc82470ecb0de5b9fd58bcd28d0e00cb829943f8efcac8e3888bd26d6a42a499`，1 条）

## 门槛口径

- 逐 criterion 两位初审一致则采用；不一致升级两位重审；升级后仍不一致记 pending。
- 只有六项 criterion 全部共识 pass 的记录才算该题过门禁；pending 与 fail 都不放行。
- 确定性关键检查仍然一票否决，MoA 共识不能覆盖确定性 fail。
- 本门槛是本地多模型共识门槛，不是真人审查，也不能证明用户可接受性。

## 未纳入合流的记录

- ['analysis-01', 'analysis-02', 'rules-01', 'rules-02', 'decision-01', 'decision-02']（不在目标任务集合内）

## 被覆盖的旧记录

同一任务的定向重审会取代旧结论；下表逐条留痕，旧记录仍保留在分片文件中。

- decision-03：`reports/quality-study-v2/moa-material-04/moa-results.json`（pending） → `reports/quality-study-v2/moa-material-05/moa-results.json`（pending）
- decision-06：`reports/quality-study-v2/moa-material-04/moa-results.json`（pending） → `reports/quality-study-v2/moa-material-05/moa-results.json`（pass）
- decision-03：`reports/quality-study-v2/moa-material-05/moa-results.json`（pending） → `reports/quality-study-v2/moa-material-06/moa-results.json`（pass）

## 备注

留出门槛解锁合流：material-04 复用 10 题，material-05 重审 decision-06（有序字段比较修正后 pass），material-06 重审 decision-03（材料歧义修订后 pass）。material-04 中 6 条开发集记录不在本批留出任务集合内，已列入 dropped_task_ids；decision-03 与 decision-06 的旧结论被定向重审覆盖，明细见 superseded。
