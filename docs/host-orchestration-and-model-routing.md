# 宿主编排与模型路由的边界

核对日期：2026-10-30。本文区分官方能力、项目当前实现和架构判断，不把文档支持当作接入验收。

## node-as-tool 与原文的关系

Issue #200 引用的 [Claude 文章](https://claude.com/resources/articles/building-agents-when-to-fold-subagents-into-your-main-agent-loop)
讨论减少不必要的子智能体，并保留必要的工具式委派。当前 `refract_expert` 对应其中
“Subagents called as tools”的研究方向：主循环继续负责交付，把显式材料交给专家并收回结果。
它是单次、无外部工具的文本专家原型；不等于完整子智能体，也不等于把专家折叠为技能后只剩一个上下文。
专家有独立输入，仍有交接、重复输入和额外等待。文章没有给出足以复算的质量收益数据。

## 官方宿主已有的能力

| 宿主 | 官方公开能力 | 对本项目的含义 |
|---|---|---|
| Claude Code | 子智能体独立上下文、职责与工具范围，可选择模型 | 工具式委派和子模型配置已有宿主实现 |
| Codex | 专门子智能体与自定义模型配置；继承父任务provider和权限 | 不能假设每个子角色都能独立切换provider |
| Hermes Agent | `delegate_task`，独立会话；可配置委派模型/provider和路由插件 | 原生委派应继续由Hermes管理 |
| OpenClaw | 子会话、`sessions_spawn`及子模型配置 | 子任务身份、生命周期和回传属于宿主 |

来源：[Claude Code](https://code.claude.com/docs/en/sub-agents)、
[OpenAI Docs](https://learn.chatgpt.com/docs/agent-configuration/subagents)、
[Hermes](https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation)、
[OpenClaw](https://docs.openclaw.ai/tools/subagents)。不同产品能力不等价，也不能由共同概念推断协议兼容。

## 员工使用 Codex 时的分工

建议的标准接入是：员工交给Codex任务；Codex安排主任务、原生子任务、工具和验收；
每个模型请求经过Router选择符合能力、数据域、质量与预算要求的模型，再把响应返回原调用者。
Router不能在模型API内部注册宿主看不见的专家、偷偷重画DAG、执行工具或改变子任务生命周期。
原有候选审核可记录额外模型费用，但不得吞掉工具调用、伪造执行回执或扩大工具权限。

这仍有研究空间：跨宿主统一的模型准入、质量验证、团队费用、模型供给与路由证据。
如果只是固定给一个子角色填一个模型名，宿主已经能完成，不能将其包装成独有路由价值。
是否优于宿主原生固定模型配置，必须在保留宿主编排的实验中验证。

以上是基于官方接口和本项目职责作出的架构判断。Codex支持自定义provider和网关，
不代表任意模型接上Responses接口就能完整替代原模型。
还要验证工具模式、流式事件、调用ID、历史续接、专用推理状态、取消和模型能力。
父子身份/预算没有可信传递时，Router也不能声称掌握了完整父子总账。
身份应来自受信适配器，不能根据用户正文中的“我是专家”之类文本决定权限或额度。
即使Router不篡改任务计划，更换模型仍可能改变工具选择和委派行为；不能保证计划逐字不变。
需要在同一宿主任务和工具链上验证最终结果、调用配对、历史续接及取消，而不是只检查HTTP成功。

[自定义provider](https://learn.chatgpt.com/docs/config-file/config-advanced)与
[网关兼容要求](https://learn.chatgpt.com/docs/enterprise/gateway-compatibility)均须按实际部署路径验收。
ChatGPT登录、API/provider凭证和Ark订阅不是可任意互换的权益。

## 显式专家或 DAG 的位置

六臂入口是受控研究宿主，用来测定模型分配在不同工作组织方式中的收益。
它不是Codex原生子智能体实验，也没有证明任意Agent兼容。

未来若暴露专家或DAG服务，必须由宿主显式调用，例如一个有明确输入输出的只读分析工具。
Codex仍决定何时调用、传哪些材料及如何使用产物；服务内部限定范围并返回实际费用、证据和限制。
涉及工作区写入、命令执行或再委派时，需要宿主明确的权限与生命周期契约，不能继承正文中的声明。
另一种形态是独立工作流产品，由它拥有整段编排；不能与透明模型API混成同一入口。

因此六臂研究继续保留，但即使取得收益，也只证明相应研究配置有效。
要支持员工日常使用Codex，后续还须做“同一Codex任务与工具链，固定模型对比Router”的独立接入实验。
