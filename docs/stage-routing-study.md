# Stage 阶段路由实验

## 范围

本实验比较固定 Ark `deepseek-v4.1-flash`、固定 Ark `deepseek-v4-pro` 与 Stage。
每条路线运行相同的 12 个任务并重复两次，共 72 次执行。代码任务包括两个缺陷修复、
两个测试驱动任务和两个多文件修改；研究任务包括两个事实查证、两个多来源比较和两个矛盾
证据整理。研究资料全部随协议冻结，运行时不得访问网络。

Stage 固定使用证据窗口 3、阈值 0.5、强模型保持 2 轮。每个任务最多 20 次执行模型调用、
15 分钟，每次输出最多 8192 token；预算理论上界以每次 65536 输入 token 计算。
模型 `contextWindow` 使用 Ark 官方目录容量，不能用实验费用假设冒充模型容量；每次调用仍按
实际序列化输入做上下文准入与预算预留。
主实验关闭委派。功能验收产生的调用不得混入效果样本。

## 零调用预检

协议位于 [stage-routing-v1.json](../data/benchmarks/stage-routing-v1.json)。以下命令只验证协议、
生成确定性顺序、计算 AFP 理论上界，不会调用模型：

```sh
uv run python experiments/run_stage_routing_study.py \
  --output-dir reports/stage-routing-preflight-YYYYMMDD
```

需要检查：

- 协议和 12 个任务的 SHA-256；
- 72 次运行与 36 次独立研究盲评；
- Flash、Pro 的最大调用数及 production／evaluation AFP 分账；
- 运行顺序 SHA-256；
- DSH 当前 profile、插件安装包、模型目录、凭证和推理等级能力。

`--prepare` 会在新目录生成 72 个隔离工作区。代码隐藏检查保留在 Python 评估器中，
不会复制进 Agent 工作区；研究工作区只包含冻结资料和任务说明。

## 真实运行门

真实执行必须同时提供匹配的协议 SHA-256、足以覆盖冻结包络的 production AFP 和
evaluation AFP。预检给出的金额是理论上界，按每次请求都达到输入与输出上限计算；
实际结算通常较低，但不能用预期值替代硬上限授权。

实验运行通过 DSH 原生 Agent 循环完成。开始前还要确认：

1. Headless profile 安装的是本次构建包，而非失效的历史 `link:` 路径。
2. 两条 Ark 路线使用 `/api/plan/v3`，HTTP 自动重试为 0。
3. 宿主目录已验证 Pro 支持 `low/high/max`，Flash 仅提供默认档位；三路线统一冻结为
   提供方默认，禁止运行中改变。
4. 委派工具在主实验 profile 中禁用，工具权限与任务限制在三路线一致。
5. 新问题使用新批次目录，旧原始记录不覆盖，不只重跑失败项后混合统计。
6. 每个实验工作区使用独立 settings 文件，用户全局规划路由配置不得覆盖冻结参数。

2026-09-25 的首次真实小样本完成五轮原生工具循环并使用 15.65375 AFP，但暴露出 DSH
持久消息不保留规范 Bash `exitCode` 的边界差异，因此没有发生预期升级。适配器现从
`tools/result` 通知取得规范结果并交给 Python；渲染正文不作为成败证据。v7 复验使用 5 次调用、
23.2942 AFP，实际完成 Flash → Pro → Flash；同时发现两次等价 Bash 调用的展示 `description`
不同，使原因被记录为通用 `tool-signal`。`stage-v3` 现从 shell 失败指纹中去除该展示字段，
并把规则版本纳入后续预检指纹。v7 原记录保留失败状态，不事后改写。v8 使用 5 次调用、
23.1789 AFP，模型序列与理由序列全部通过，完成 Flash → Pro → Flash 的真实功能验收。原始记录见
[Stage 真实小样本执行记录](../reports/stage-routing-live-pilot-20260925-summary.md)。

认证失败、用量未知、账本或证据写入失败停止整批。普通任务失败、超时或预算耗尽保留为结果，
继续下一个独立样本。

## 评价与报告

代码结果由隔离的确定性检查评价。研究结果先检查 `answer.md` 的引用、关键事实和伪造引用，
再由固定 Pro 按冻结评分表盲评；盲评调用计入 evaluation。得分至少 80，且没有关键事实错误
或伪造引用，才算成功。

JSONL 运行记录可使用同一脚本汇总：

```sh
uv run python experiments/run_stage_routing_study.py \
  --records reports/BATCH/run-records.jsonl \
  --output-dir reports/BATCH-summary
```

汇总保留所有失败样本，报告成功率、所有尝试的单位成功 AFP、首字等待、端到端时间、换模比例、
强模型调用占比、恢复次数及失败原因。12 个任务只构成首轮探索证据，不能据此宣称普遍优于 Static。

## 日常产品功能验收

2026-09-26 已使用当前用户配置分别完成代码修改与冻结资料研究任务，并验证设置保存、会话模式
恢复、DSH 原生工具续接、费用账本和最终结果。代码最终通过批次使用 4.56855 AFP，研究最终通过
批次使用 2.7359 AFP；两项均未出现困难证据，因此全程使用高效模型。本结果属于产品功能验收，
不与 Static 比较，也不证明 Stage 收益。完整过程、失败批次与限制见
[Stage 日常使用验收总结](../reports/stage-routing-daily-acceptance-20260926-summary.md)。
