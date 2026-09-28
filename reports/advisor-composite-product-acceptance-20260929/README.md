# Advisor Gate 与 Composite 产品接线验收

## 范围与冻结上限

本批使用用户原有 DSH `web` profile 的模型绑定，验证 DSH、Codex、Hermes 各一条
Advisor 正常审核工具任务和一条 Composite 初始选模工具任务。每条最多 5 次远程模型
调用、5 分钟，关闭委派和 HTTP 自动重试。执行模型输出上限 2048 tokens；Advisor
Judge 为 1024，当前 Composite Judge 为 4096。输入按实测客户端请求分别冻结：
DSH／Hermes 为 98,304 字节，Codex 为 300,000 字节。

六条真实流程的保守合计上限为 **1272.24 AFP**；历史最坏占用、此前验收和本批
失败预留统一向上保守计入 **140 AFP**，合计 1412.24 AFP，低于已授权累计
2000 AFP。用户 profile 的生产预算仍为 `0`，上述限制只用于本批验收驱动。
每条预检、实际请求大小、调用回执和账本保留在本地忽略目录
`.refractagent/acceptance/advisor-composite-product-20260929*`。未写入凭证。
供代码审阅的无凭证汇总见 [真实运行摘要](live-runs.json)。

## 真实模型正常流程

| 客户端 | 策略 | 执行结果 | 调用用途 | 已结算费用 | 工具归属 |
| --- | --- | --- | --- | ---: | --- |
| DSH | Advisor | 通过 | 执行 2、审核 1 | 0.23115 AFP | DSH |
| DSH | Composite | 通过 | Task Judge 1、执行 2 | 0.09685 AFP | DSH |
| Codex | Advisor | 通过 | 执行 2、审核 1 | 31.46460 AFP | Codex |
| Codex | Composite | 通过 | Task Judge 1、执行 2 | 6.67735 AFP | Codex |
| Hermes | Advisor | 通过 | 执行 2、审核 1 | 2.13295 AFP | Hermes |
| Hermes | Composite | 通过 | Task Judge 1、执行 2 | 0.46410 AFP | Hermes |

六条合计 **18 次已结算调用、41.06700 AFP**。每条均收到一次宿主工具结果，
Router 没有执行工具、创建 DAG 或自动重试。费用差异受到客户端输入体积影响；
Codex Advisor 的上游记录包含 136,361 个输入 tokens，故本表不能用于比较策略
收益或推断日常平均费用。
最早一批 DSH Advisor 的本地 `summary.json` 将账本内部标识误写为调用用途；
其原始 `runs/planning/*.json` 的 `calls` 与决策记录显示执行两次、审核一次。
验收脚本已改用实际调用记录生成后续摘要，原始文件仍保留。

## 受控流程与可信工具证据

三客户端的 Advisor 错误候选返工流程再次通过确定性上游夹具：均完成首次拒绝、
宿主工具续接与第二次审核，共 5 个模型步骤、零付费调用。Composite 正常工具
续接也在三客户端夹具中通过，各有 1 次 Task Judge、2 次执行调用。

DSH 插件契约新增 Composite 结构化失败序列：两次同类原生 Bash 失败后切至
指定接管模型，保持一次，随后返回 Task 选定的常用模型。Python 标准接口中
附带版本化、与工具调用 ID 配对的可信元数据时，同一序列也通过确定性测试。
这些是受控功能证据，不是自然任务收益证据。

纯 Base URL 下，Codex 与 Hermes 的普通 function 工具结果没有可信退出码。
Router 将这类结果标为无法分类，正常续接可用，不能据此宣称两端会自动识别
重复失败并动态接管。未来若客户端提供可核验的版本化工具证据，可使用现有协议；
Router 不从工具正文猜测退出状态。当前 Codex 的 `gpt-6-astra` 宿主基线还会发送
`custom` 工具，超出已接通的 function 合同；本批使用已验收的 `gpt-5.5`
宿主工具目录基线，当前 Codex 程序版本为 0.154.0。

## 本批发现与修正

1. Composite 的 Task Judge 原先沿用模型目录的巨大输出容量。首次受控护栏在
   网络派发前拒绝，记录上游派发数为 0；Router 保留 0.23485 AFP 的待核对
   预留。此数不是确认扣费，不计入已结算费用。
2. 新版为 Task／Composite LLM Judge 增加独立、默认 1024 tokens 的输出上限，
   预算预检与实际派发使用同一上限。当前 `glm-5.3-flash` 实测在 1024 tokens
   内使用 1018 个推理 tokens，形成截断；该失败已结算 0.07980 AFP。
   仅把当前 Composite 设置提高到 4096，再次调用已返回完整 JSON。
3. 该 JSON 将模型 ID 中的 `-v4-1-`写成 `-v4.1-`，严格校验按设计拒绝，
   此次已结算 0.08010 AFP。现使用 `C1`、`C2` 等短候选 ID，由 Python
   映射回冻结的模型池；不接受模糊模型名或额外候选。修正后的 DSH Composite
   真实工具任务通过。
4. Hermes 对未声明档位的虚拟模型会发送 `reasoning_effort: none`。Router
   现将此值视为客户端不要求覆盖档位；真实调用仍按角色冻结的推理等级执行。
   其他不匹配档位继续在调用前拒绝。

上述失败各保留原批次，不在原路径重复派发。两次已结算失败共 0.15990 AFP；
本批全部可核对的已结算调用合计 **41.22690 AFP**，另有 0.23485 AFP
预留待核对。

## 当前 profile 与发布边界

DSH 为 `0.1.5-rc.3`。其 `web` profile 已通过 symlink 安装本仓库插件，
插件构建完成并重载原服务；原有 provider、凭证、会话和 Stage 默认选择未被覆盖。
用户配置已升级至 `planningRouting v6`，Advisor／Composite 零调用诊断均可用。
当前 Composite 的独立 Judge 为 `glm-5.3-flash`，输出上限 4096。设置变更前的
本地备份位于 DSH profile 的 `backups/` 目录。

网页快照确认“任务 DAG”和“路由轨迹”页签共存。自动化浏览器中的设置与模型菜单
点击未产生状态变化，因此**没有完成设置页的交互视觉验收**；不能以源码构建或
配置检查替代这一项。Advisor Laya 仍属实验，原 24 条审核题集的有限结果见
[前批报告](../advisor-acceptance-20260928/README.md)。本批没有重做 Judge 质量题集，
也没有验证图片／影片审核、三客户端自然重复失败收益或 P6 共享预算。

## 客户端可用清单

| 能力 | DSH | Codex | Hermes |
| --- | --- | --- | --- |
| Advisor 真实正常审核与宿主工具 | 通过 | 通过，function 工具基线 | 通过 |
| Advisor 错误候选返工复审 | 受控夹具通过 | 受控夹具通过 | 受控夹具通过 |
| Composite 真实初始选模与工具续接 | 通过 | 通过，function 工具基线 | 通过 |
| Composite 可信重复失败接管 | 原生事件契约通过 | 纯 Base URL 未取得可信证据 | 纯 Base URL 未取得可信证据 |
| 现有 `gpt-6-astra` 的 `custom` 工具 | 不适用 | 未接通 | 不适用 |

“通过”仅针对以上冻结流程。客户端功能边界由各自实际请求与受控证据决定。
