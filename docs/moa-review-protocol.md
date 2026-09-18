# MoA 评审协议：本地 CLI 多模型共识质量评审

对应 Issue #52 的质量门槛修订。评审从「真人双审」改为「本地 codex CLI 与 claude CLI 的
多模型共识评审」，不再宣称任何真人签署。确定性事实检查仍然优先且不可被模型共识覆盖。

## 证据等级

- 评审者都是模型调用，origin=model，reviewer_identity_verified=false。
- 所有结论只能表述为「跨 provider 多模型共识下的质量判定」，不能写「已获真人确认」。
- 任务构造者是 Codex；codex CLI 评审不是独立来源，只作为第二模型视角，
  跨 CLI / 跨 provider 的共识只能降低单一 judge 偏差，不能证明真实用户接受度。

## 评审成员与 thinking effort

所有 thinking effort 在策略文件中冻结，实际调用必须携带对应参数；缺失或不一致视为无效记录。

| 角色 | CLI | 模型 | thinking effort |
|---|---|---|---|
| 初审判定 A | codex CLI | ds/deepseek-v4-pro | max |
| 初审判定 B | claude CLI | opus | high |
| 升级判定 A | codex CLI | ark/kimi-k3 | high |
| 升级判定 B | claude CLI | opus | max |

- codex CLI 通过「-c model_reasoning_effort=<effort>」传入，并显式携带「--model <model>」。
- codex CLI 的「--output-schema」按模型能力冻结：ds/deepseek-v4-pro 不携带该参数，
  依靠系统提示中的严格 JSON 约束；升级判定 A 的 ark/kimi-k3 同样不携带该参数。
- claude CLI 通过「--effort <effort>」与「--model <model>」传入。
- codex CLI 通过本机 opencodex 配置解析 ds/deepseek-v4-pro；不携带
  「--ignore-user-config」。重试在顶层配置为 0。
- claude CLI 的 JSON schema 必须以内联 JSON 字符串传入，不得传文件路径。
- 模型名称以本机 CLI 实际接受的别名为准，冻结在策略 JSON 中；CLI 拒绝别名时该记录为 failed。

## 调用约束

- 零重试：任何超时、非零退出、无输出或 JSON 不合规都记为 failed / pending，不自动重发。
- 单次调用默认超时 480 秒，冻结在策略文件里；评审调用不注册工具，claude 使用
  「--tools ""」并设置「--permission-mode dontAsk」，codex 使用「-s read-only」。
- 超时可用「--timeout-seconds」或环境变量「MOA_REVIEW_TIMEOUT_SECONDS」覆盖：
  覆盖值只作用于本次运行，不写入策略文件，所以策略摘要不变、既有材料评审记录继续有效。
  预检会记录实际生效秒数并据此计算包络；live 启动时校验与冻结包络一致，
  不一致必须换新目录重新预检。长评审题目的定向重跑用 900 秒（见下方解锁记录）。
- 每次调用输出严格 JSON，由 parse_review 校验：必须逐字覆盖全部 criteria，
  总体 verdict 必须服从「任一 fail 则 fail，否则任一 pending 则 pending，否则 pass」。
- 原始响应、prompt 哈希、CLI 版本、退出码和耗时逐次存档，未知用量不填零。

## 判定流程

1. 先运行确定性检查。任一已支持检查 fail，则整体 fail；MoA 不得覆盖。
2. 两位初审模型对每个 criterion 独立给 pass / fail / pending。
3. 两位一致时采用该判定；任一 criterion 两位不一致，该 criterion 升级给
   ark/kimi-k3 与 opus（max）重审。
4. 升级后两位一致时采用该判定；升级后仍不一致，该 criterion 为 pending。
5. 整体：任一 criterion fail 则 fail；否则任一 pending 则 pending；全部 pass 才 pass。

用途确认采用同一规则：两位初审一致 pass 才通过；不一致升级，仍不一致为 pending。

## 成本记账

- MoA 评审消耗的是本机 CLI 账号，不在 Ark AFP 账本内。评审成本单独报告
  moa_review_cost：包含调用次数、CLI、模型、thinking effort、耗时与已知用量字段。
- 未知的外部用量保持 unknown，不折算成零，也不混入 Ark AFP 的
  afp_per_accepted_task 分子；该指标口径改为「Ark AFP per accepted task」，
  并在报告中并列 MoA 评审的外部成本证据。
- 评审耗时计入研究准备成本，不计入用户路线在线时间。

## 升级评审身份变更（2026-09-17）

升级判定 A 原定 gpt-6-astra，因本机 Codex 用量上限未恢复而改用 ark/kimi-k3，
经用户确认并在证据中标注偏离。历史冻结记录（moa-calibration-07 的零调用包络）
保持原策略不变；升级实跑使用新策略哈希并重新冻结。恢复 Codex 额度后如需回到
原身份，须再次冻结并注明变更。

升级判定 B 原定 fable，本机 claude CLI 回报「Fable 5.1 requires usage credits」，
三次调用均在 2 秒内以 exit code 1 失败并记为 failed / pending（证据见
moa-calibration-08）。经用户确认改用 opus 并将 thinking effort 提到 max。该选择的
代价是升级判定 B 与初审判定 B 同属 opus 系列，升级侧不再是独立模型来源，
共识只能按「同模型更高 effort 复核」解读，不能声称跨模型独立验证。
恢复 fable 额度后如需回到原身份，须再次冻结并注明变更。

## 证据文件

- moa-material-reviews.json：每任务每 criterion 的初审、升级与共识结果。
- moa-output-reviews.json：每交付输出的 criterion 级共识与绑定哈希。
- moa-purpose-review.json：用途确认共识与策略哈希绑定。
- 全部记录绑定 task_sha256 / output_sha256 / policy_sha256（MoA 策略哈希），防止事后改判；
  用途确认记录额外绑定 statistics_policy_sha256（统计协议哈希）与 task_bindings。

## 冻结与预检

- 运行前必须用「experiments/run_moa_review.py --preflight」生成冻结策略与调用包络，
  零模型调用。付费评审运行必须使用新的输出目录并显式指定「--live」。
- 策略、模型、thinking effort、prompt、JSON schema、超时与零重试规则改变时，
  必须重新冻结；历史记录保留原策略标签。
- 超时覆盖不属于策略改变：策略文件里的 480 秒不动，包络只记录本次实际生效的秒数。

## 留出门槛解锁（2026-09-18）

12 题留出实验此前被两处阻塞挡住：decision-03 先是评审调用超时
（claude 侧 480 秒内未返回，记 exit_code=124），decision-06 是参考检查把有序字段
当成无序集合比较。前者超时解除后，又暴露出第二处真实的材料歧义。

- decision-06 的参考检查由 set_equal 改为 equal（有序），任务与参考的
  semantic_criteria 同步补上「顺序必须满足全部依赖方向，并与 finish_minute 相互一致」，
  并重算该题 task_sha256 与两个 artifact 哈希；其余 11 题材料、参考与哈希未动，
  因此 10 份已通过的材料评审记录继续有效。
- decision-03 与 decision-06 用「--task-ids」定向重跑，超时用 900 秒，
  产物为 reports/quality-study-v2/moa-material-05/。
- 超时解除后 decision-03 仍判 pending：s1 的硬条件是「无障碍通道」，而 s2 起初只对 A 写
  「无障碍通道」，对 B、D 写「有通道」、C 写「无通道」。若「有通道」不等同硬条件所指，
  D 即硬条件不合格，rejected_ids 应为 {B,C,D} 而非参考的 {B,C}。修订只把 s2 的通道描述
  统一为「有无障碍通道」／「无无障碍通道」，房间、容量、报价与参考答案一字未改，并重算
  该题 material_sha256、task_sha256 与两个 artifact 哈希；decision-03 因此在
  reports/quality-study-v2/moa-material-06/ 再重审一次。
- 上述修订只落在 data/quality-study-v1：MoA 材料评审记录（含六个开发任务）都由 v1 生成，
  而 v2 的 protocol.json 哈希已被已完成开发对照的 frozen.json 绑定，改动会让那批付费结果
  无法复算。v2 的 decision-06 与 decision-03 保持原样，改用 v2 跑留出前必须先同步修订。
- 旧分片与新分片通过 experiments/merge_moa_records.py 合成单一 records 文件，
  门禁（moa_gate）只读这一个文件，避免同一任务出现多份互相矛盾的记录。

运行参数：`--task-ids` 只作用于 `--kind material`，用于定向重跑；`--timeout-seconds`
（或环境变量 `MOA_REVIEW_TIMEOUT_SECONDS`）只覆盖单次调用超时，preflight 会记录本次
实际生效秒数，`MOA_POLICY` 里的 480 秒不动，策略摘要因此保持不变。

解锁结果（2026-09-18，均为本机 CLI，未消耗 Ark AFP）：

- 材料评审：`reports/quality-study-v2/moa-material-gate/moa-results.json`，12 题六项 criterion
  全部共识 pass，升级 0 条、无效记录 0 条。合流默认拒绝跨分片重复任务；被定向重审取代的
  旧结论必须显式使用 `--allow-supersede` 才会被覆盖，并在 `superseded` 字段与 README 逐条留痕。
- 用途确认：`reports/quality-study-v2/moa-purpose-06/`，两位初审
  （codex `ds/deepseek-v4-pro`、claude `opus`）一致 pass，无升级。
- 门禁放行：12 题冻结件为 `reports/pareto-holdout-v1/bound-01/frozen.json`，
  `moa_gate` 判定为 True；排练产物 `reports/pareto-holdout-v1/rehearsal-01/` 为 0 次真实调用。
- 付费执行只登记范围（12 题 × 3 臂 × 3 重复，调用上限 612，估 400–550 AFP），等待放行。

## 升级实跑结果与已知限制（2026-09-17）

升级评审实跑于 moa-calibration-09（6 次调用、5 次有效、1 次 failed），聚合产物为
moa-calibration-10：19 例，共识 pass 9 / fail 6 / pending 4，与未升级的
moa-calibration-06 完全一致。两个已分歧案例（prose-contradiction、missing-required-rule）
的升级判定一致为 fail，结论未变；missing-sampling-limitation 因升级判定 A 输出不合规
保持 pending。本轮升级只提高了分歧 criterion 的证据密度，没有改变任何案例的最终判定。

已知限制：升级判定 A 走无 output-schema 路径，在 1/3 案例返回带代码围栏的 JSON，
按严格 JSON 规则记为 failed / pending。若下一轮要容忍围栏输出，必须先冻结新的解析
规则并使用新的输出目录重跑，不追改本轮证据。另有 3 例（rules-01-positive、
decision-02-positive、analysis-01-equivalent）因初审存在无效输出，按零重试规则保持
pending，本轮不升级。
