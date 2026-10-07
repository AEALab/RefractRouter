# 自动路由与 Codex 工具证据有限验收

## 本批范围

核心 0.16.7、插件 0.32.1，当前客户端范围为 DSH 与 Codex；Hermes 暂缓。
本批未启动新付费实验，不修改日常任务预算、模型、凭证或信任设置。

标准模型 API 仍不进入 DAG，也不代替宿主执行工具。DAG 仅在独立自动路由研究入口运行。
本报告区分真实客户端＋模拟模型、确定性核心流程和已有真实模型记录。
流程通过不证明模型质量提高或 DAG 比直接执行省钱。

## 两项实现改进

1. 标准入口补齐显式工具要求的当前任务回执检查。候选没有发出工具调用时，即便猜对答案
   也不会交付；费用先结算，被丢弃候选留在审计中，不追加 Judge 或重跑工具。
   普通 Base URL 的默认 `receipt` 模式只证明收到宿主结果，没有退出事实标为
   `unclassified`。Codex 增强适配使用 `confirmed` 模式，要求结构化事实确认状态。
   状态事实不能替代操作／答案的语义质量审核；非零退出也不能改写为执行成功。
2. DSH 混合拆分模式先读取 Python 的零调用预检。明确禁止／强制 DAG，以及命中现有
   简单任务规则时，不调用拆分 Judge。模型配置未通过执行准入时同样不先付判别费用。
   本地和云端 Judge 使用同一准入顺序；插件只消费 `decomposition_judge.required`，
   不复制 Python 的路由规则。核心不支持该合同就明确要求升级。

## Codex 实际接线

实际客户端为 `codex-cli 0.154.0`。测试使用临时验收配置和本机模拟模型，
不修改用户 Codex 日常配置。三个命令均由实际 Codex 工具执行：两次固定 `printf`，一次 `false`。

| 案例 | 实际工具状态 | 候选交付 | 模拟模型调用 |
|---|---|---|---:|
| 正常退出 | `completed`，退出码 0 | 交付 | 2 |
| 非零退出 | `failed`，退出码 1 | 交付，并保留失败状态 | 2 |
| 未执行就猜答案 | 无当前任务回执 | 阻止 | 1 |
| 缺少增强证据 | `unclassified` | confirmed 模式阻止 | 2 |

以上四条接线全部符合冻结预期，付费调用为零。非零退出案例仅验证事实传递，
`semanticQualityVerified=false`，不宣称模拟模型的最终正文通过语义审核。
另以实际 Codex 的两次相同失败命令验证 Stage 序列 `small → small → large`。
权限拒绝、基础设施故障、未知结果、旧任务证据隔离及流式候选不泄漏由确定性测试核对。

原始证据：`codex-initial-policy.json`、`codex-final-policy.json`、`codex-stage.json`。
最终版本为明确选择 confirmed 的接口合同；原先默认严格的中间结果也保留，避免覆写证据。
不将 Codex CLI 的验收范围扩展为 Codex 桌面端或任意 Agent 已兼容。

## 自动路由五条有限路径

使用真实 Python 路由／调度／账本和固定模拟模型，配置画像仅用于控制测试分支。
全部采用自动选择，未强制 DAG；多节点路线实际执行，不以单节点图冒充拆分。

| 路径 | 结果 | 模拟模型调用 | 关键证据 |
|---|---|---:|---|
| 直接执行 | completed | 1 | 不调用 planner、Judge |
| 三节点 DAG | completed | 5 | 规划＋facts／risks／answer＋评审，两个根节点独立 |
| 节点截断失败 | failed | 2 | 截断调用已结算，不运行下游及最终评审 |
| 预算不足 | no-feasible-route | 0 | 预检停止，未派发 |
| 取消 | cancelled | 2 | 已返回调用结算，不继续下游，无未知用量 |

最终原始记录与汇总在 `paths-final/`。模拟本地路线费用为零，不把该金额解释成实际云端价格。
`paths-fixture-01/`、`paths-fixture-02/` 保留夹具修正过程：第一版固定画像使直接路线被
质量／数据域联合准入排除，且任意文本本来是合法节点输出；第二版改用明确截断，
实际已停止，但检查器误期待节点状态 `invalid-output`。最终依据记录的 `failed`、
`finish_reason=length` 及 billed 调用核对。没有修改产品门槛使测试通过。

复现（需要匹配源码与测试夹具环境，输出目录必须全新）：

```sh
uv run python -m validation.dsh.probe_automatic_paths --output /tmp/新的验收目录
uv run python validation/codex/probe_tool_requirements.py
uv run python validation/codex/probe_tool_hook.py
uv run pytest
npm run --prefix validation/dsh/plugin typecheck
npm run --prefix validation/dsh/plugin test:contracts
```

## 当前完成边界

- #178：DSH 的已有真实工具验收继续有效；本批补齐 Codex CLI 当前版本的证据接线与
  标准入口验收。普通 Base URL 缺失结构化事实时不能承诺退出成功。
- #113：本批核对真实核心的自动多节点分支及失败处理；来源隔离留出集、任务质量与
  direct／DAG 净收益研究尚未完成，因此不能关闭整个研究 Issue。
- 旧实验、旧费用与质量分数不追改。新运行沿用公开价格参考估值／新增现金分开记账；
  旧 AFP 配置继续兼容读取，不为了这轮测试改写历史。

## 发布核对

完整 `uv run --offline pytest`：1775 项通过，227.54 秒；插件契约 205 项通过，
严格类型检查通过。第一次完整运行唯一失败为插件旧版本号断言，修正后重跑整套通过；
其余 1774 项第一次也通过，没有放宽行为验收。

0.16.7 wheel 与 0.32.1 插件分发包已构建并安装到用户原有 DSH web profile，
原服务重新加载，未新增 profile。全部核心 Python 文件和插件 dist 与源码／构建一致。
设置与凭证的 SHA-256 和升级前相同，生产现金 5 CNY、评审现金 1 CNY 继续沿用。
安装环境原本未含 Laya／MLX；本轮未修改用户独立本地模型环境。

浏览器验证原会话、自动路由、两个独立设置卡片、任务 DAG 图及路由轨迹正常。
界面证据：[路由轨迹](dsh-route-trace.jpg)、[DAG](dsh-dag.jpg)、[设置卡片](dsh-settings.jpg)。
版本与哈希核对见 [发布记录](release.json)。这些截图回放已有真实模型记录，不是新付费运行。

收尾按 Craft Wiki 评估一个候选：宿主回执、退出事实和语义质量不能相互替代。
既有 `host-lifecycle-structured-tool-evidence` 已覆盖其跨项目规则，跳过重复条目，
新增项目验证证据留在本报告；该评估不阻塞发布。
