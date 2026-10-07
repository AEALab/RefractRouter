# Codex 与 Hermes 的工具证据接入

当前产品验收只覆盖 DSH、Codex。下述 Hermes 适配与结果是保留的历史内容，本批不扩展其支持范围。

## 为什么需要客户端适配

标准 Chat Completions／Responses 的工具结果通常只有模型可读的内容，没有可信的进程退出状态。
Router 不执行客户端工具，也不从内容中的“失败”字样猜测成败。缺少宿主事实时，Stage／Composite
继续将结果记为 `unclassified`。这不妨碍基本工具往返，但不能验证自然重复失败后的换模。

`refract-tool-evidence-v1` 将宿主事实与 Router 已交付的 `callId` 配对；Router 校验调用属于
当前服务、工具结果确实出现在后续历史中，并保存事实后才推进策略状态。新增的
`POST /v1/tool-evidence` 只收状态、类别、指纹和调用 ID，不收工具正文。它使用与模型接口相同的
Bearer 认证。直接 Base URL 接入仍可使用，只是没有增强的工具结果判断。

## Hermes

可选插件位于 `validation/hermes/refract-tool-evidence/`。安装到当前 Hermes profile 的
`plugins/` 时需复制符号链接目标内容；在该 profile 的 `config.yaml` 中把
`refract-tool-evidence` 加入 `plugins.enabled`。插件只依赖 Python 标准库，无需改动
Hermes 管理的 Python 环境。启动 Hermes 时设置：

```sh
export REFRACTROUTER_URL=http://127.0.0.1:8088/v1
export REFRACTROUTER_TOKEN=你的本机Router令牌
```

插件读取 Hermes `post_tool_call` 的终端 JSON 包络与 `tool_call_id`。非零退出码是任务失败；
权限拒绝、后端故障和转后台分别记录为拒绝、基础设施故障、未确认，不以换模型代替宿主处理。
插件送达失败时，Hermes 工具仍按原方式运行，Router 将该结果保留为无法分类。插件不读取
Hermes 凭证，也不执行或改写工具。

当前安装版本的无付费验收入口：

```sh
HERMES_DISABLE_LAZY_INSTALLS=1 \
  /绝对路径/hermes-agent/venv/bin/python validation/hermes/probe_tool_evidence.py
```

此入口在临时 profile 中加载真实插件，只用本机模拟模型，不修改日常 profile。

## Codex CLI

当前 Codex `PostToolUse` 钩子提供原始工具调用 ID，但 Bash 的 `tool_response` 是模型可读文本；
`codex exec --json` 事件提供结构化退出码，但其 `item.id` 与模型 `call_id` 不同。客户端适配层
必须同时观察两者，以命令和完整输出唯一匹配后，才向 Router 提交事实。重复且无法区分的并行
命令保持无法分类。适配器是 `validation/codex/run_with_evidence.py`，只转发模型请求和证据，
不负责 Codex 的工具、权限或任务推进。

先在当前 Codex 配置添加并信任以下钩子；保留已有钩子，不要覆盖它们：

```toml
[[hooks.PostToolUse]]
matcher = "^Bash$"

[[hooks.PostToolUse.hooks]]
type = "command"
command = "/绝对路径/RefractRouter/.venv/bin/python -m refractrouter.client_tool_evidence"
timeout = 5
```

Codex 会要求通过 `/hooks` 审查并信任新增钩子。运行时先保持原来的模型目录与 provider
配置，再由适配器临时把该 provider 的 Base URL 指向本机转发端口：

```sh
uv run python -m validation.codex.run_with_evidence \
  --router-base http://127.0.0.1:8088/v1 --provider refract -- \
  -m refract/stage "请处理这个任务"
```

若 Router 配置了认证，把 `REFRACTROUTER_TOKEN` 提供给适配器。适配器强制使用
`codex exec --json`；原有的 `request_max_retries=0`、`stream_max_retries=0` 和模型目录设置
仍需保留。增强适配器为 Responses 请求设置
`metadata.refract_tool_evidence_policy="confirmed"`。没有启用钩子时会提示证据不可用；
显式要求执行工具的最终候选因状态无法确认而停止，不会猜测退出成功。
该模式在任务开始冻结，任务内不能切换验收强度。

普通 Base URL 不经过增强适配器时默认使用 `receipt` 模式：要求当前任务中实际存在
Router 发出的工具调用及宿主返回结果，但没有结构化退出事实仍显示 `unclassified`。
工具回执已收到与退出状态已确认分别记录，不能据此声称任务语义正确。
两种模式都拒绝模型没调用工具就猜出答案；缺少回执的候选缓冲且不交付，费用照常结算。

无付费模拟验收：

```sh
uv run python validation/codex/probe_tool_hook.py
uv run python validation/codex/probe_tool_requirements.py
```

此脚本只在隔离的临时 Codex 配置中绕过钩子信任，以测试项目自身的固定脚本；日常接入不使用
该选项。Codex 桌面端、其他 Codex 执行模式尚未通过这条 CLI 适配验收。

Codex 钩子字段与信任流程依据
[OpenAI Docs 的 Hooks 说明](https://learn.chatgpt.com/docs/hooks)。

## 已验证范围

两个无网络端到端探测均完成两次相同命令的非零退出，并观察到执行模型序列
`small → small → large`。这验证工具事实传递和 Stage 重复失败切换；不证明真实模型的
任务质量或费用收益。DSH 的原生事件接入保持原合同。标准 Base URL 单独接入时仍没有
宿主执行状态；其它客户端需要提供等价、可核验的工具事实。

2026-10-07 使用实际 `codex-cli 0.154.0` 完成四条接线：正常退出、非零退出、
没执行却猜答案、缺少增强证据。前两条保留真实状态，后两条不交付候选。
另以真实命令连续两次非零退出验证 Stage 的 `small → small → large`；
全部模型为本机模拟上游，付费调用为零。详见
[有限验收记录](../reports/automatic-reliability-20261007/README.md)。
