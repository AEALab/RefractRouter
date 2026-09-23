# 规划路由实现与验收（2026-09-23）

## 交付范围

实现 P0—P5 的六类策略：Static、Stage、Task、Composite、Advisor、Escalation。
新入口为 `refractagent/planning`，默认 Stage。保持 DSH 原生工具、审批、上下文及委派循环；
不创建 DAG，不进入内部工具执行桥。P6 父子共享预算独立后续验收。

Python 核心版本 0.10.0，插件版本 0.23.0，宿主实际验证版本 0.1.5-rc.1。
未进行付费模型实验，以下费用全部来自本地模拟用量。

## 已安装功能基线

初始版本及哈希见 [baseline.json](baseline.json)。
本次工作树从 `256c1bd` 开始，但本机插件 0.22.0 包含 `ca19c88` 的开发功能。
仅核对版本和哈希不足以证明功能兼容；实际设置注册暴露了旧校验器拒绝
`liveExecution.maxProductionCost: unlimited` 和工具额度字段的问题。

已三方合入该开发基线的人民币预算、冻结汇率、单节点输出与任务输出额度、
工具权限设置、设置保存诊断、DAG 角色与动态拓扑展示，并保留本次规划路由改动。
没有修改用户现有预算或模型配置。设置服务作为明确启动依赖注册，注册失败不再隐蔽遗漏卡片。

## 自动化验收

| 检查 | 结果 |
| --- | --- |
| 最终 `uv run pytest` | 1207 passed，338.86 秒；包括 TypeScript 契约与插件构建 |
| TypeScript 严格类型检查 | 通过 |
| 真实 DSH LlmRuntime + Session + ToolRuntime | 3 次模型请求、2 次原生工具执行、0 次网络模型调用、不生成 DAG |
| 原工具桥真实 SDK 回归 | 成功、拒绝与异常回执通过 |
| Python wheel 脱离源码运行 | 工作进程预检和原生工具验收通过 |
| 源码构建与独立 profile 安装文件 | 关键文件 SHA-256 相同 |
| Git 空白检查 | 通过 |

完整测试输出见 [pytest-release.log](pytest-release.log)。
真实 SDK 摘要见 [native-sdk.json](native-sdk.json)。
安装核对见 [package-verification.json](package-verification.json)。

策略测试覆盖任务隔离、冻结、预算预留、未知用量、取消、进程恢复拒绝重派、
工具配对、真实来源 replay、跨模型准入、判别用途记账、有界审核与丢弃费用。
模拟和记录回放只能证明协议与状态行为，不能证明真实换模收益。

## 实际浏览器验收

在独立 `refract-planning-check` profile 中安装最终包，以本地 fixture 模型和工具运行：

- 六个具名策略选项可见；点击和方向键同步更新原生模型菜单。
- Static 完成两轮工具交互，最终状态 completed，三次 execute 均为 accepted。
- 模拟成本三次各 0.00016 USD，总计 0.00048 USD；不是实际支付费用。
- 刷新后选择和工具历史保留；没有 token 投影错误。
- 切到普通 fixture 模型隐藏策略栏；返回规划路由恢复先前 Task 选择。
- 规划设置能读取独立预算和四个角色；零调用检查与离线模拟正常。
- 原 RefractAgent 设置卡片、任务 DAG 页签与路由轨迹页签共同存在。
- 只读查看已有单节点 DAG 历史，实际图形节点及模型标签可见。
  多节点连线和动态拓扑由已有契约测试覆盖；本次没有新增付费 DAG 运行。

新自动路由模拟请求曾被现有配置的 `ark/glm-5.3` 不可用路线在派发前拦截。
保留该诊断，不以修改用户模型配置或放宽权限规避。
日常 `web` profile 的插件包未被替换；验收包只安装到独立 profile。
DSH 的设置与历史存储可能跨 profile 共享，因此本次未保存修改现有用户设置。

## 验收中修复的问题

1. DSH rc.1 使用 `Session.snapshotEvents()`，适配器兼容该接口与原模拟结构。
2. 消费者可在 finish 处结束流，完成标记必须先于 finish 交付，避免 finally 误取消。
3. 列表插槽使用 `id`，设置 keyed 插槽使用 `key`。
4. 模型发现请求必须携带 provider；诊断使用 local，历史查询使用真实 session ID。
5. 同版本 tar 路径可能复用安装缓存；采用独立产物路径并验证安装文件哈希。
6. 离线 fixture 的工具 render 签名为 `render(args, value)`。
   错误签名曾将对象写入文本块；已修复并补入真实 SDK 文本回执断言。
   原失败验收历史保留，后续成功轮次另行记录。

## 明确边界

- 尚未创建真实会话的欢迎页，宿主不渲染 composer dock。
  首条任务前可通过原生模型菜单选择策略；会话创建后横向控件出现。
- 尚未验证的真实跨 provider 组合默认不准入，需显式兼容清单和对应验证。
- 首版文本与宿主工具；多模态、Prefill、P6 共享预算及真实收益实验不在本次验收范围。
- 规划路由的角色价格与明确预算仍需用户配置。Stage 为产品默认，不代表效果优于其他策略。
- Python 证据包含原始调用内容，仅存受限本地目录；历史列表不返回原始提示词。
- 源码与证据留在当前工作树，未创建提交或 PR。

具体配置与实现说明见 [规划路由文档](../../docs/trajectory-routing-strategies.md)。
