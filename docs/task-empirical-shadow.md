# 整任务经验费用与影子选择

关联 [#205](https://github.com/AEALab/RefractRouter/issues/205)、
[总计划 W04](https://github.com/AEALab/RefractRouter/issues/201)。新配置
`refractagent-planning-v8` 在原金额合同上显式增加 `taskShadow`，对独立 Task 模型池记录
经验建议。执行仍由当前这一次分类的首次调用成本合同选择，任务内固定模型；不额外生成
比较答卷，不追加分类，也不引入 Stage。旧 v1–v7 保留原合同，默认不启用影子。
DSH 只传递配置、请求与结果，统计与判断均在 Python。

## 完整费用

`task_cost_observation.observe` 从 #203 的 `task-result-v1` 原账本投影提取整任务逐调用费用，
包含分类、执行、返工、审核与丢弃候选。逐调用金额须与原总账一致，遗漏或重复不能当作
更低成本。已结算的 `billed-failed`、`billed-cancelled` 使用实际计价值，不恢复已释放预留。
未知状态保留最大已占用/预留数值；尚未派发预留不伪造调用ID。失败终态也保留全部已结算
费用。本地推论单列零现金记录，CPU与等待仍非免费生产审核。观测不释放或改写账本。

金额按币种和计费模式保留。订阅参考估值与计量预算分账；有原 CNY 参考总账时可比较
包含两类调用的完整参考值，不能再与现金重复相加。
已知 token 计价也不等于 provider 实际扣款。实际扣款继续标记为本视图未建立，
不把原有研究的未知 AFP/CNY 预留当作零。缓存用量不完整时不假定已命中缓存。
范围限于 Router 管理的调用，外层 Agent 与子 Agent 未覆盖费用保持原状态。

## 独立验收与分层

离线输入 `task-calibration-input-v1` 固定 `kind` 和样本。每个样本含完整 W02 `result`、
独立 `assessment`、经维护者核实的 `sourceClusterId` 和 `split=calibration`。
留出任务不能建 profile。独立记录必须绑定真实最终候选ID/哈希、完整准则哈希和全部检查，
其摘要还须进入 W02 的 `hidden-evaluation` 通道。用户点赞、普通模型审核、多数票、旧候选
通过和局部事实不能代替完整验收。首版接收冻结完整任务检查或明确人工裁定；尚无独立
资格的模型评审保持未知，后端准入依照 [#207](purpose-judge-regression.md) 和 #210 冻结。

`task-empirical-profile-v1` 按任务类型、路线配置、实际模型/声明修订、归一化价格和汇率、
有效期及缓存条件分层。相同任务输入或同源重复不能增加独立分母；未知验收/费用不能
被悄悄剔除以提高通过率。价格时段在任务内变化时不借旧价格取得资格。
分类后指导变化会使影子过时，执行模型继续固定，也不重新分类。

每组先满足样本下限和正确交付比例的单侧95% Wilson 下界，再按完整费用均值排序。
报告中位数、观察最小/最大、样本量与逐样本留一均值绝对误差。这是已知轨迹描述，
不是新任务区间保证、一般成功率或因果省钱证明；适合度0.9不是90%正确率。
数据不足、类型/缓存不明、版本/价格漂移、过期、跨单位/维度和预算不足均不产生确定排序。
只记录已通过本次能力/数据域及预算准入的配置备援，否则备援为空。

## 配置与分类

v8 的模型可声明 `revision`；缺失或未固定时经验资格未知。声明身份不是供应商签名认证。
`taskShadow.schemaVersion=task-expected-cost-shadow-v1`，显式包含：

- `profile`、`profileSha256`：离线 profile 与规范 JSON 摘要。
- `families`：类型ID、说明、准则哈希及完整检查ID。
- `routeVersion`、`pricingDate`、`expiresOn`：冻结路线与价格有效期。
- `cacheCondition`：`cold`、`warm`、`observed-mixture` 或 `unknown`；描述条件而非命中保证。
- `minSamples`、`qualityMin`：独立样本下限及质量下界门槛。

同一次 LLM 判别使用 `task-decision-with-family-v3`，同时返回逐候选评价和 `taskFamily`。
新提示可能改变分类结果，不能宣称 v7/v8 分类行为完全相同；影子对照复用当前这一次分类。
profile 和历史答卷不进入分类提示。类别缺失/未知只让影子未知，不修复响应或追加请求。
当前 Jev Choice 或本地判别缺少逐候选/类型证据时保留 `costBasis=unavailable`，不能由单个
选项概率补造全池资格。本版没有验证免 Judge 固定规则，因而不会自动开启直选。

硬预算仍由原账本按原生容量和保守单次上界执行，包含必要参考预算。均值不放宽额度或
减少未知占用。运行时只输出聚合来源摘要，原任务ID与详情留在受信离线材料。
导入方对完整裁定及来源独立性负责，程序验证合同/绑定，不认证人类身份或自然语言裁定。

## 零调用构建与验收

```bash
uv run python experiments/build_task_empirical_profile.py \
  --input reports/冻结观测目录/samples.json --output-dir reports/新的profile目录
```

输入与输出目录分离、输出全新。保留输入/实现摘要、profile、结果与失败记录；不读取凭据，
不调用模型，不在线学习。配置摘要从构建 `result.json` 读取，不能直接用缩进文件字节哈希。
`simulation` 明确标记，不能当作真实质量获证。

模拟测试覆盖单次便宜但反复执行更贵、实际模型固定、独立通道与各类拒判；DSH真实核心
进程及安装包分别验收。`validate_task_shadow_worker.py` 只模拟回执。实际独立质量、预测
误差与整批省钱由 #210 验证，不能据合同检查宣布通过。
