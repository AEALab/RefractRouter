# 真实执行先导批次：预检与材料审查

本批次已完成编排与零调用预检，尚未取得本批次 AFP 上限授权，因此没有发起真实调用。
它是 #39/#40 正式研究前的真实执行链路验收，不是完整收益实验，不能据此关闭两项 Issue。

## 来源与独立性核查

2026-09-09 使用 Playwright 有头浏览器逐页访问以下官方材料，读取页面快照中的关键段落。
所述审查由 AI 完成，不登记为 #40 要求的人工复核。

| 任务 | 官方来源 | 核对的事实与问题结构 |
| --- | --- | --- |
| SQLite 外键迁移 | [SQLite Foreign Key Support](https://www.sqlite.org/foreignkeys.html) | 连接级启用、事务内切换无效、即时与延迟检查；审核错误操作顺序 |
| Python 分组迭代 | [Python 3.13 itertools](https://docs.python.org/3.13/library/itertools.html) | 相邻分组、共享输入、及时消费；解释错误代码并给出修正 |
| 图表文本替代 | [W3C Complex Images](https://www.w3.org/WAI/tutorials/images/complex/) | 简短替代文本和详细说明、数据与趋势、可见说明；撰写无障碍发布稿 |

三项任务没有沿用原费用比较模板，来自不同来源和不同问题结构。封闭材料使用中文摘要，
保留来源 URL，不要求被测模型联网或执行工具。历史任务正文哈希检查未发现完全重复。
三组字符相似度约为 0.227、0.231、0.230；该数值只是排重辅助，不证明统计独立性。
另用本地 SQLite 3.50.4 与 Python 执行可确定性检查的材料事实，结果全部符合预期；
见 [material-audit.json](material-audit.json) 与 [审查脚本](audit_materials.py)。
任务均为短输入，数量只有三个，不支持总体或分层迁移结论，也没有覆盖完整规划挑战矩阵。
这批材料运行后仅作开发证据，不能再次用作正式新留出。

## 冻结范围与包络

- 3 个任务，每任务运行直接回答、人工计划、每次自动规划、计划复用四条路线。
- 每任务单独生成一次缓存计划并评审，费用计入设置；共 12 条计划对照。
- 生成与规划固定为 DeepSeek V4 Pro，独立评审使用 Kimi K3。这不是校准后的 A/B 比较。
- 自动计划最多 8 个节点；输入消息保守字节界为 16384，评审为 65536，完整模型输出上限为 8192。
- 最大 84 次调用：66 次生产、18 次评审。
- 生产上限 **892.1088 AFP**，评审上限 **1327.1041 AFP**，合计 **2219.2129 AFP**。
- 以上是最坏情况准入界，不是实际费用预测；实际成本按服务端已确认用量记账。
- 每样本 300 秒、生产约束 300 AFP；并发 2，provider 派发间隔 100 毫秒。
- HTTP 零重试、节点零回退、规划零修复；使用新输出目录。
- 已结算输出失败保留并继续后续样本；未知用量、证据、认证或账本故障停止整批。

冻结协议：[issue-39-40-live-pilot-v1.json](../../../data/research/issue-39-40-live-pilot-v1.json)。
协议摘要：`864bee8d98f279c19e0b606bc26b9eab7829e1ca662b8151cd7285faeb11fdfe`。
完整包络：[preflight.json](preflight.json)。

默认命令不会调用模型：

```bash
uv run python -m experiments.run_research_live_pilot \
  --protocol data/research/issue-39-40-live-pilot-v1.json \
  --output-dir /tmp/research-live-pilot-new-preflight
```

真实执行还须显式提供 `--execute-paid-run`、匹配的 `--approved-protocol-sha256`、
`--max-production-cost` 和 `--max-evaluation-cost`。参数不匹配时，在创建真实客户端前拒绝。
凭证只读现有 `CODEX_ARK_API_KEY`，不写入协议或报告。

## 验证

付费入口专项测试 3 项通过，包括默认零调用、无授权参数拒绝，以及假客户端下的完整编排。
测试中的 `--execute-paid-run` 由假客户端接管并禁止网络，不代表已发起真实模型请求。
完整回归结果：580 passed、5 subtests passed，耗时 62.62 秒。
