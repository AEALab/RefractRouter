# 联合研究 v1 实测与关闭条件

此报告仅覆盖分别编写的虚构封闭案例，不代表线上任务分布；长表格中的每行不算独立任务。
风险为冻结契约的场景标签，未测量现实机构损失；输入规模与风险相互关联，不能据此分离风险的因果作用。
所有判定依据冻结协议，质量失败、无可行路由和缺评审均保留，不根据留出成绩重新校准。

批次状态：`finished`。计划测试 104 条，实际记录 104 条，交付通过 30 条。
独立审计核对 431 份原始文件、430 次已结算调用；未知用量 0 次。

已确认 AFP：生产 368.7130，评审 716.2970，合计 1085.0100。
AFP 为订阅用量计量，不等于额外现金付费；未知用量保留预留，不能计为零。

## 材料、校准与交接

- small-medium：独立材料评审 100 分，通过。材料包含7个独立虚构封闭场景，校准与测试任务之间无仅换数字或实体的复刻；各任务事实、限制与交付要求明确，冻结参考的计算与逻辑均核对无误（如排程容量、去重并集170、招募24人及候补数、方案筛选仅乙满足）；所标挑战均可从材料检验，短任务未强行拆分，且每个任务均声明结论限于封闭案例、不代表真实机构或线上总体，未把共享输出结构当作重复。
- large-high：独立材料评审 92 分，通过。材料整体满足独立校准与测试要求：7个任务（3个校准、4个测试）在解题目标、规则设定和数据结构上各不相同，并非同一问题仅换数字的复刻；各任务的事实、限制和交付要求明确可评分，冻结参考经抽样核验与来源数据一致；所标挑战（parallel、serial、handoff、bottleneck）均可从材料与交付要求检验，且所有任务均明确声明为虚构封闭场景，结论限于案例内。个别参考字段命名（如「第一列总和」「第二列总和」）较为通用，需结合任务文本解读，但不影响可评分性。

节点 profile 可用 9 项，排除 9 项。
可用项只接受至少三个独立校准任务；不足或层外能力不强制匹配。

- 整任务 small-medium：A = mid；B = mid
- 整任务 large-high：A = 无可用模型；B = 无可用模型

逐边核对实际下游请求，共验证 95 条被消费依赖，其中跨模型 16 条。
交接核验指字段确实进入下游请求；不能单凭传参成功证明模型充分理解或使用了内容。最终交付单独评审。

| 校准任务 / 模型 | 固定参考下最终节点独立分 | 同模型完整 DAG 最终分 | 完整交付 |
| --- | ---: | ---: | --- |
| cal_workshop / cheap | 95 | 100 | 通过 |
| cal_workshop / mid | 90 | 95 | 通过 |
| cal_workshop / strong | 95 | 95 | 通过 |
| cal_catalog / cheap | 95 | 100 | 通过 |
| cal_catalog / mid | 97 | 92 | 通过 |
| cal_catalog / strong | 98 | 95 | 通过 |
| cal_recruit / cheap | 95 | 98 | 通过 |
| cal_recruit / mid | 96 | 98 | 通过 |
| cal_recruit / strong | 98 | 100 | 通过 |
| cal_transit / cheap | 78 | 82 | 不通过 |
| cal_transit / mid | 62 | 22 | 不通过 |
| cal_transit / strong | 93 | 12 | 不通过 |
| cal_sensor / cheap | 88 | 42 | 不通过 |
| cal_sensor / mid | 95 | 88 | 不通过 |
| cal_sensor / strong | 95 | 45 | 不通过 |
| cal_archive / cheap | 95 | 30 | 不通过 |
| cal_archive / mid | 95 | 62 | 不通过 |
| cal_archive / strong | 88 | 45 | 不通过 |

节点探测使用冻结参考上游，组合使用实际上游。上表不同调用的差异还包含生成随机性，不能单独归因于交接。

## 全计划分母与主比较

下表均值仅描述已有评分或已执行记录，不替代共同配对结论；缺评审不补零。

| 条件 | 计划 | 记录 | 通过 | 有效评分数 / 均分 | 完整运行 AFP | 已记录尝试墙钟均值（秒） |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| dag-node-a | 8 | 8 | 4 | 4 / 98.25 | 4.9783 | 9.74 |
| dag-node-b | 8 | 8 | 3 | 4 / 92.00 | 6.3820 | 10.34 |
| dag-single-a | 8 | 8 | 4 | 4 / 100.00 | 6.4394 | 9.26 |
| dag-single-b | 8 | 8 | 4 | 4 / 99.50 | 8.1130 | 10.83 |
| dag-quality | 8 | 8 | 4 | 7 / 78.29 | 48.9650 | 36.97 |
| dag-strong-serial | 8 | 8 | 4 | 7 / 62.14 | 68.5399 | 33.36 |
| dag-strong-parallel | 8 | 8 | 4 | 8 / 61.25 | 68.1505 | 31.48 |
| direct-a | 8 | 8 | 0 | 4 / 75.75 | 7.0705 | 10.72 |
| direct-b | 8 | 8 | 3 | 4 / 96.25 | 5.3340 | 7.48 |
| auto-cold-a | 8 | 8 | 0 | 0 / — | 52.4484 | 48.42 |
| auto-cold-b | 8 | 8 | 0 | 0 / — | 50.6380 | 36.16 |
| auto-reuse-a | 8 | 8 | 0 | 0 / — | 0.0000 | 0.01 |
| auto-reuse-b | 8 | 8 | 0 | 0 / — | 0.0000 | 0.01 |

### #39 主比较

- overall，dag-node-a 对 dag-single-a：4/8 完整配对，4 个任务；判定 `insufficient-paired-evidence`。
  score：均值 -1.75，97.5% 区间 [-4.25, 0]。
  deployment_cost：均值 -0.365275，97.5% 区间 [-1.0658125, 0.009762500000000035]。
  wall_time_ms：均值 958.4334069804754，97.5% 区间 [-5885.334186983528, 7201.396323973313]。
  cost_saving_fraction：均值 0.11421985052667308，97.5% 区间 [-0.015373539942219211, 0.31398037616717656]。
  latency_ratio：均值 1.073783930172692，97.5% 区间 [0.762244572825732, 1.3367161364349374]。
- overall，dag-node-b 对 dag-single-b：4/8 完整配对，4 个任务；判定 `insufficient-paired-evidence`。
  score：均值 -7.5，97.5% 区间 [-22.5, 0]。
  deployment_cost：均值 -0.4327375，97.5% 区间 [-1.3215249999999998, 0.023937500000000056]。
  wall_time_ms：均值 -969.4884165364783，97.5% 区间 [-4713.571833213791, 4660.861020704033]。
  cost_saving_fraction：均值 0.1041082183977434，97.5% 区间 [-0.0245608315915829, 0.3369005496352777]。
  latency_ratio：均值 0.9033719254626293，97.5% 区间 [0.7534358993135994, 1.1184756952303718]。
- small-medium，dag-node-a 对 dag-single-a：4/4 完整配对，4 个任务；判定 `does-not-meet-frozen-benefit-thresholds`。
  score：均值 -1.75，97.5% 区间 [-4.25, 0]。
  deployment_cost：均值 -0.365275，97.5% 区间 [-1.0658125, 0.009762500000000035]。
  wall_time_ms：均值 958.4334069804754，97.5% 区间 [-5885.334186983528, 7201.396323973313]。
  cost_saving_fraction：均值 0.11421985052667308，97.5% 区间 [-0.015373539942219211, 0.31398037616717656]。
  latency_ratio：均值 1.073783930172692，97.5% 区间 [0.762244572825732, 1.3367161364349374]。
- small-medium，dag-node-b 对 dag-single-b：4/4 完整配对，4 个任务；判定 `does-not-meet-frozen-benefit-thresholds`。
  score：均值 -7.5，97.5% 区间 [-22.5, 0]。
  deployment_cost：均值 -0.4327375，97.5% 区间 [-1.3215249999999998, 0.023937500000000056]。
  wall_time_ms：均值 -969.4884165364783，97.5% 区间 [-4713.571833213791, 4660.861020704033]。
  cost_saving_fraction：均值 0.1041082183977434，97.5% 区间 [-0.0245608315915829, 0.3369005496352777]。
  latency_ratio：均值 0.9033719254626293，97.5% 区间 [0.7534358993135994, 1.1184756952303718]。
- large-high，dag-node-a 对 dag-single-a：0/4 完整配对，0 个任务；判定 `insufficient-paired-evidence`。
  score：均值 None，97.5% 区间 None。
  deployment_cost：均值 None，97.5% 区间 None。
  wall_time_ms：均值 None，97.5% 区间 None。
  cost_saving_fraction：均值 None，97.5% 区间 None。
  latency_ratio：均值 None，97.5% 区间 None。
- large-high，dag-node-b 对 dag-single-b：0/4 完整配对，0 个任务；判定 `insufficient-paired-evidence`。
  score：均值 None，97.5% 区间 None。
  deployment_cost：均值 None，97.5% 区间 None。
  wall_time_ms：均值 None，97.5% 区间 None。
  cost_saving_fraction：均值 None，97.5% 区间 None。
  latency_ratio：均值 None，97.5% 区间 None。

### #40 主比较

- overall，auto-cold-a 对 direct-a：0/8 完整配对，0 个任务；判定 `insufficient-paired-evidence`。
  score：均值 None，97.5% 区间 None。
  deployment_cost：均值 None，97.5% 区间 None。
  wall_time_ms：均值 None，97.5% 区间 None。
  cost_saving_fraction：均值 None，97.5% 区间 None。
  latency_ratio：均值 None，97.5% 区间 None。
- overall，auto-cold-b 对 direct-b：0/8 完整配对，0 个任务；判定 `insufficient-paired-evidence`。
  score：均值 None，97.5% 区间 None。
  deployment_cost：均值 None，97.5% 区间 None。
  wall_time_ms：均值 None，97.5% 区间 None。
  cost_saving_fraction：均值 None，97.5% 区间 None。
  latency_ratio：均值 None，97.5% 区间 None。
- small-medium，auto-cold-a 对 direct-a：0/4 完整配对，0 个任务；判定 `insufficient-paired-evidence`。
  score：均值 None，97.5% 区间 None。
  deployment_cost：均值 None，97.5% 区间 None。
  wall_time_ms：均值 None，97.5% 区间 None。
  cost_saving_fraction：均值 None，97.5% 区间 None。
  latency_ratio：均值 None，97.5% 区间 None。
- small-medium，auto-cold-b 对 direct-b：0/4 完整配对，0 个任务；判定 `insufficient-paired-evidence`。
  score：均值 None，97.5% 区间 None。
  deployment_cost：均值 None，97.5% 区间 None。
  wall_time_ms：均值 None，97.5% 区间 None。
  cost_saving_fraction：均值 None，97.5% 区间 None。
  latency_ratio：均值 None，97.5% 区间 None。
- large-high，auto-cold-a 对 direct-a：0/4 完整配对，0 个任务；判定 `insufficient-paired-evidence`。
  score：均值 None，97.5% 区间 None。
  deployment_cost：均值 None，97.5% 区间 None。
  wall_time_ms：均值 None，97.5% 区间 None。
  cost_saving_fraction：均值 None，97.5% 区间 None。
  latency_ratio：均值 None，97.5% 区间 None。
- large-high，auto-cold-b 对 direct-b：0/4 完整配对，0 个任务；判定 `insufficient-paired-evidence`。
  score：均值 None，97.5% 区间 None。
  deployment_cost：均值 None，97.5% 区间 None。
  wall_time_ms：均值 None，97.5% 区间 None。
  cost_saving_fraction：均值 None，97.5% 区间 None。
  latency_ratio：均值 None，97.5% 区间 None。

质量差为左减右；节省比例为 1−左/右，时延比为左/右。
三个单节点短任务中，同一方法的节点路由与同图单模型路线实际选模相同；整任务直接回答 A/B 也都选择 M3。
这些重复调用仍有生成与评审波动，不能把分数差异都归因于选模策略。只有调查任务的节点路线形成不同于全图单模型的异构分配。
确认性门槛为全部计划配对交付、质量下界 ≥ −3 分、费用节省下界 ≥ 20%、时延比上界 ≤ 1.1。
分层样本仅四个，区间为目的性选题条件内的近似描述，不报告总体 p95。辅助比较见原始 analysis。

## 规划、失败与实际时序

测试状态计数：`{'completed': 30, 'no-feasible-route': 49, 'quality-failed': 16, 'planner-failed': 7, 'generation-failed': 1, 'evaluation-unavailable': 1}`。
测试失败数不等于规划请求失败数；缓存计划失败会传播到复用条件，但没有重新发起规划。

自动冷计划与缓存设置共 32 条；结构合法计划节点数分布：`{1: 12, 4: 1, 2: 4, 3: 4, 5: 4}`。
有效语义评分 25 条，通过 23 条。
缺失语义评审与语义不通过分开保留；缓存复用原评分不算新的独立计划评分。

结构合法自动计划中，共 52 个节点没有同能力层的校准模型。
详见 [automatic-capability-coverage.json](automatic-capability-coverage.json)。缺少匹配层说明准入证据不足，不能直接推断模型在该层能力差。

实际阶段与节点排队 / 重叠记录见 [timing.json](timing.json)。失败前的部分阶段不补成完整执行。

## 完整成本

| 阶段 | AFP |
| --- | ---: |
| material_review_evaluation | 32.2680 |
| baseline_calibration | 79.0112 |
| baseline_calibration_evaluation | 135.7630 |
| node_calibration | 52.6126 |
| node_calibration_evaluation | 323.0790 |
| handoff_validation | 20.5192 |
| handoff_validation_evaluation | 21.2660 |
| cache_planning_setup | 51.3959 |
| cache_planning_setup_evaluation | 42.0360 |
| runtime_execution | 114.1627 |
| runtime_execution_evaluation | 161.8850 |
| runtime_planning | 51.0114 |

| 分析范围 | 运行 AFP | 共享设置 AFP | 首次合计 AFP |
| --- | ---: | ---: | ---: |
| #39 | 223.97269999999997 | 757.9509 | 981.9236000000001 |
| #40 | 126.85119999999999 | 757.9509 | 884.8021 |

上述首次合计使用联合批次全部设置费用，包含另一项研究专用开销，是完整实验视图，不是单项部署报价；两项设置不能相加。
以下按原始调用用途拆解已确认设置费用，只作费用归属说明，不改变冻结的主比较或选择：

| 设置用途 | 已确认 AFP |
| --- | ---: |
| shared_material_node_and_handoff | 449.7448 |
| issue39_whole_dag_calibration | 123.2033 |
| issue40_direct_and_cache_setup | 185.0028 |

| 缓存 | 一次设置 AFP | 复用执行 AFP | 该计划首次使用 AFP |
| --- | ---: | ---: | ---: |
| test_notice-a | 2.4298 | 0 | 2.4298 |
| test_notice-b | 2.3012 | 0 | 2.3012 |
| test_minutes-a | 2.58535 | 0 | 2.58535 |
| test_minutes-b | 3.2032999999999996 | 0 | 3.2032999999999996 |
| test_grant-a | 2.7346500000000002 | 0 | 2.7346500000000002 |
| test_grant-b | 2.97415 | 0 | 2.97415 |
| test_surveys-a | 4.7748 | 0 | 4.7748 |
| test_surveys-b | 4.5859000000000005 | 0 | 4.5859000000000005 |
| test_seating-a | 10.35435 | 0 | 10.35435 |
| test_seating-b | 9.571100000000001 | 0 | 9.571100000000001 |
| test_workorders-a | 10.96595 | 0 | 10.96595 |
| test_workorders-b | 4.0733 | 0 | 4.0733 |
| test_shipments-a | 6.4229 | 0 | 6.4229 |
| test_shipments-b | 12.1881 | 0 | 12.1881 |
| test_energy-a | 7.3194 | 0 | 7.3194 |
| test_energy-b | 6.9476 | 0 | 6.9476 |

计划语义检查与最终评审均为冻结运行协议的必要步骤，计入实际墙钟和运行费；校准/交接检查另列。
两项分析共享同一批设置成本，不能把两份报告中的 first_use_cost 相加。所有失败与实验评审仍在总账中。
本地选模计算无模型 AFP；校准结束至首个缓存设置的间隔可作包含持久化的准备时间上界，不冒充纯 CPU 用时。
没有调用 DSH 外层，费用为零。保留生产与评审原始分类，便于按其他部署口径另行分析。

## 人工复核与关闭状态

结项判断见[结项评估](结项评估.md)。真人复核未完成，可先阅读[按题目整理的阅读版](human-review.md)。
[复核包](human-review-packet.json)按事前规则抽样，隐藏模型、路线和自动分数；
映射另存，评审者须填写身份、日期、判断与理由，不能用模型评审代替。
本报告不自动关闭 #39 或 #40：须分别核对采集完整性、合并交付及 #40 真人复核，再回填 #1，关联 #22、#8。
