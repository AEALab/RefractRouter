# v0.4 执行方式对照准备

本目录记录 2026-09-07 完成的代码验证、三轮离线模拟和单轮零调用预检。
**实际付费模型调用 0 次，新增实际费用 0 AFP。模拟分数与费用不能证明真实收益。**

## 已实现

- Python 持有不可变抽取证据；分析与正文只输出内容及引用，不再转抄 evidence 数组。
- A：每个候选模型一次调用生成完整 HTML；B：每个模型执行七节点 DAG；
  C：独立节点评审选出的七节点路线，允许全部节点选择同一模型。
- 同模型 B/A 分离拆解效果，C/B 检验选模效果；相同比较使用相同 task/repeat 集合。
  family-best 需要该组所有候选完成执行及评审，不从失败组中挑选幸存者。
- 原始输出不修补；最终评审的格式错误、截断及非有限分数会使观察不可用，
  但已发生的费用和原始失败响应仍保留。

## 验证证据

| 证据 | 结果 |
|---|---|
| [完整测试记录摘要](verification.json) | 166 项 Python 测试通过，包含 20 项 TypeScript 合约检查 |
| TypeScript 类型检查及构建 | 通过；没有提交生成的 JavaScript |
| [DSH 打包生命周期](dsh-lifecycle.json) | 安装、配置覆盖、移除、重装、启动通过，0 模型调用 |
| [三轮模拟](offline-three-repeat/benchmark-summary.json) | complete；156 次生产模拟 + 84 次评审模拟 |
| [模拟调用核对](offline-three-repeat/simulation-calls.json) | 0 网络调用；63 个完整节点候选单元 |
| [单轮预检](admission-preflight/preflight.json) | 52 生产 + 28 评审 = 80 次计划请求；当前 model_calls=0 |
| [DSH runner 预检](admission-dsh-evidence.json) | pass；直接调用 Python 边界，不是付费宿主会话 |
| 历史归档核对 | 前次真实三轮归档索引的 47 个文件哈希全部一致 |

模拟使用同分 judge fixture，C 自然选中全 Flash。它验证“不强制混用”和成本复用账目，
不能说明 Flash 真实表现最佳。真正注册工具到 Python 子进程的零调用路径由 TypeScript
合约测试覆盖；真实 DSH 宿主的插件加载由生命周期检查覆盖，两者均未发起模型回合。

旧 Flash 第三轮 synthesis 的原始响应没有 evidence，也没有新协议要求的可解析引用。
回归测试保留旧协议的 invalid-evidence 和新协议的 unresolved-citations 判定；
未修改历史结果，未把它重判成成功。

## 下一步边界

初次真实对照继续冻结 Flash/M3/Pro 候选池与 K3 judge，避免同时扩大模型池造成混淆。
单轮预估生产 202.39、评审 453.38，合计 **655.76 AFP**（总计先求和再四舍五入）。
输入估计不是严格上界；建议另行授权的单轮额度为生产 210 + 评审 460 + 外层 0.5，
合计 **670.5 AFP**。该额度尚未授权、未执行。先检查单轮证据，再决定是否追加重复验证。

详见 [协议与实验设计](../../docs/evidence-state-execution-modes.md)。当前材料仅保存在本地，
没有推送公共仓库、发布 PR 或改写 GitHub issue。
