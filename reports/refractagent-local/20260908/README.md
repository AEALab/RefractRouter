# RefractAgent 本机应用验收

日期：2026-09-08。核心版本 0.2.0，DSH 插件版本 0.10.0。

## 已验证

- 完整回归：396 项测试与 5 项子测试通过；见 `regression.txt`。
- TypeScript 类型检查和构建通过。
- 使用 wheel 与 tgz，在源码目录外以独立 `uv tool` 环境和全新 DSH profile 安装。
- 原生 DSH headless 模拟会话已覆盖省成本、均衡、质量优先三个接口。
  物理模型分配分别为 DeepSeek V4 Flash、MiniMax M3、DeepSeek V4 Pro。
- 模拟调用不访问真实模型，结果明确标记模拟；模拟费用不能当作实付费用。

完整安装步骤、版本、安装包哈希和三种策略记录见 `installed-demo.json`。
该记录证明对应安装包的模拟链路，不证明真实回答质量或普遍降本。

## 网页验收

已在真实 DSH 网页选择三种策略、分别新建会话、提交同一任务并取回模拟结果。
界面、实际物理模型分配和 Python 账本一致，用户任务原文得到保留。
最终安装包在重启后的网页完成三种策略复验，记录见 `web-demo.json`，
截图为 `economy-demo-v3.png`、`balanced-demo-v3.png`、`quality-demo-v3.png`。
网页与 headless 中实际安装的适配器文件均与最终 tgz 内容一致。
模型菜单见 `three-strategy-models.png`。自动化使用 DSH 自带的网页目录选择器，
不以命令行改默认模型替代网页点击选择。

网页验收曾发现宿主注入消息被误认为用户任务，修复及回归说明见
`ui-task-attribution-regression.json`。修复前的模拟安装和回归记录单独保留，
最终通过版本以 `installed-demo.json` 和 `regression.txt` 为准。

## 真实验收结果

最终安装包通过原生 DSH headless 运行同一份 A/B 方案比较题，三种策略各完成一次生产
和一次 Kimi-K3 独立评审，共 6 次真实调用，均正常返回，重试和未知用量均为 0。

| 策略 | 生产模型 | 生产 AFP | 评审 AFP | 整任务耗时 | 独立评审 |
| --- | --- | ---: | ---: | ---: | ---: |
| 省成本 | DeepSeek V4 Flash | 0.0841 | 1.828 | 20.310 秒 | 100，通过 |
| 均衡 | MiniMax M3 | 0.4395 | 1.958 | 16.253 秒 | 95，通过 |
| 质量优先 | DeepSeek V4 Pro | 0.9273 | 1.823 | 11.786 秒 | 98，通过 |

生产合计 1.4509 AFP，评审合计 5.609 AFP，总计 7.0599 AFP，均在授权上限内。
AFP 按服务端 token usage 与清单费率折算，用于订阅用量核算，不证明额外现金扣费。
三种答案均正确计算 A 为 14400 元、B 为 8400 元，并基于数据约束建议选择 A。
完整结果、用量、检查和原始记录哈希见 `live-results.json`，答案见 `live-answers.md`。

**已知限制：** MiniMax M3 原文为 283 个字符，去掉空白后为 263 个字符，
超过严格的 250 字符上限；独立评审仍判定长度通过，属于本次评审漏检。
保留原始答案和评分，不能据此宣称全部格式要求通过或评审可替代确定性检查。
本次证据证明三个接口真实跑通，不证明跨任务节省收益或质量优先每次得分最高。
该长度问题作为后续应用可用性问题记录，不影响本阶段的安装、选模、执行及记录交付。
后续追踪：[应用开发 #41](https://github.com/AEALab/RefractRouter/issues/41)、
[确定性输出约束 #42](https://github.com/AEALab/RefractRouter/issues/42)。

PR 准备阶段再次执行完整回归，396 项测试、5 项子测试通过，见 `pr-regression.txt`。
其余状态与配置哈希保留验收当时的记录；是否已合并以关联 PR 为准。

## 授权与故障过程

初始授权见 `live-acceptance-request.json`，用户已回复“执行”。
最终执行请求与安装包哈希见 `live-acceptance-execution-request.json`，
用户后续回复“允许”并要求在 Ark 订阅范围内直接推进，记录见 `live-authorization-update.json`。

- 自动审批最初拒绝附带工作区指令和技能清单的请求。使用独立工作目录与 `DSH_HOME`，
  关闭上述注入、运行信息和标题模型后，三种零调用检查确认只含题目及通用 DSH 指令；
  完整发送范围见 `live-payload-review.json`。
- 随后在派发模型前发现 DSH 原生凭据引用格式错误，已修复、补齐回归并重新安装。
  该次 0 调用失败见 `live-credential-integration-failure.json`。
- 最终包的两次审批超时均未启动进程。用户再次授权后完成上述 6 次调用，无 HTTP 重试。

最终源码、安装与网页证据分别以 `regression.txt`、`installed-demo.json`、`web-demo.json` 为准。
修复前记录、旧截图和失败证据保留。验收脚本的临时付费开关均已关闭；
本机交付网页另使用用户已授权的真实执行配置，后续由用户主动提交任务。

## 运行与历史证据边界

应用安装包包含模型清单、profile 和计划，RefractAgent 模型入口无需源码目录。
历史 `refractrouter_validate`、`refractrouter_task` 工具继续依赖对应源码环境。
当前应用支持文本任务，不生成 DSH 工具调用；团队集中服务不在本阶段范围内。

本次新增一条精确的 K3 成功基线恢复兼容记录。原有记录及原始实验产物保持不变，
只有指定成功基线允许进入当前版本的 resume；既有节点探针不能跨版本 compose/finalize。
完整测试覆盖该兼容路径，本次没有重新运行旧付费实验。

安装方法见 [本机上手说明](../../../docs/refractagent-local-quickstart.md)。
