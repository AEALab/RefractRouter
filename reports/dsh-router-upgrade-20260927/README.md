# DSH 升级与独立路由验收

日期：2026-09-27。变更基于尚未合入的 Escalation 分支；Task 与 Escalation 历史证据保留。

## 版本与安装

- 核对 npm 渠道后，将实际 DSH 从 `0.1.5-rc.1` 更新为官方 `latest` 的 `0.1.5-rc.3`。
  `next` 为 `0.1.7-rc.2`，不将预览渠道自动安装到用户当前环境。
- 发现实际安装 Python 核心仍为 `0.12.0`、规划协议 `/3`，与开发源码不一致。
  最终构建并安装 Router `0.14.0`、协议 `/4`；DSH 插件为 `0.27.0`。
- 保留原 `web` profile 和原服务地址 `http://127.0.0.1:53611/`，重启加载新包。
- 安装前备份设置、凭证及 profile 清单。安装后六个原文件的 SHA-256 全部一致；
  没有改写 provider、模型、预算、默认策略和会话。
- 分发包校验值与版本清单见 [versions.json](versions.json)。不提交安装密钥或 profile 副本。

## 验证结果

| 验收 | 结果 | 证据 |
| --- | --- | --- |
| 完整 `uv run pytest` | 1317 passed，195.01 秒 | [完整日志](pytest.txt) |
| TypeScript 契约 | 157 passed | [契约日志](plugin-tests.txt) |
| 严格类型检查 | 通过 | [类型检查](typecheck.txt) |
| Python wheel、插件构建与 npm pack | 通过 | [产物校验值](versions.json) |
| DSH 最新核心的插件安装/覆盖/移除/重装/启动 | 本地源码和 tarball 均通过 | [源码](lifecycle-local.txt)、[打包](lifecycle-packed.txt) |
| 实际 DSH + 实际已安装 Python + 插件 | 3 次模拟模型请求、2 次宿主原生工具执行、无 DAG | [安装环境合同](installed-native-tools.txt) |
| 原 profile 浏览器 | 两个设置卡片、原模型选项、路由模式、历史费用、DAG 入口均可读 | 下述实际界面检查 |

首轮完整测试发现三个冻结版本断言仍期待旧值，修正后重新执行完整套件；不删去失败覆盖。
Stage 新批次记录 `stage-v4`，启动时拒绝混入旧规则批次，不改写历史实验结果。

真实模型调用为 **0**；全部模型响应来自确定性模拟。浏览器读取的费用是旧记录，
不是本轮新增费用。本轮不声称证明了某策略省钱或提高质量。

## 实际界面检查

在用户原有 `web` profile 检查：

- 规划路由与自动路由独立设置卡片共同存在。
- 模型下拉仍含 Ark 的 DeepSeek、GLM、Kimi、MiniMax 等原配置；DeepSeek 官方路线保留。
- 模型菜单仍显示规划路由与“路由模式”，没有恢复输入框底部的六模式控件。
- 历史 Task 记录能显示两次已接受调用，原累计 `6.48775 AFP` 可读；没有重新执行任务。
- 历史 DAG 页签能显示已完成的 `deliverable` 节点；多节点/连线由既有拓扑契约测试覆盖，
  本轮浏览器选取的两个历史记录均为单节点，未将其写成多节点视觉验收。
- 查看设置时系统会自动填充资料草稿；本轮没有点击保存，没有改变运行参数。

## 实施范围

新增独立标准模型接口，使用相同 Python 策略与账本；不启动 DSH、不执行客户端工具、
不注入宿主提示或管理其上下文。旧 DAG 研究入口继续保留。

修复 Static 互斥候选预算累加、Stage 重放和旧失败信号、Escalation 请求上限与 Judge
实际超时，以及并发 step 误停原请求。DSH 原生字段解析移到适配文件，核心增加中立工具事实合同。

详见 [独立接口及职责边界](../../docs/independent-model-router.md)、
[Switchyard 与五篇原始论文的审查](../../docs/router-strategy-review-20260927.md)。

## 尚未验收的范围

- 标准网关只支持文本/function 的 Chat Completions、Responses 全历史子集。
  上游仅 Chat Completions；媒体、托管工具、私有 reasoning 与增量 response ID 未接通。
- SSE 在完整回复接受及结算后输出；不是上游逐 token 透传，不能宣称改善首字时延。
- Codex、Hermes、OpenClaw、Claude 尚未按具体版本分别真实接入。
- 标准模型协议不保证任务身份；普通工具文本不保证退出码。
  不把首条提示 hash 当成任务 ID，也不猜测工具失败。
- Task 质量门槛与费用排序并不证明团队任务的成功率或全局最优成本。
  本地 Laya 的 Escalation 质量验收限制仍保留，P6 不在本轮范围。

## 经验库评估

按 Craft Wiki 只评估“以实际安装产物为升级基线”这一候选。
现有主题《以已安装功能为基线逐层验收插件升级》已覆盖此规则，跳过重复记录。
