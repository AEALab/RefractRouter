# Codex CLI 接入

Codex CLI 可通过独立标准模型网关使用规划策略。Router 不替 Codex 执行工具、组织技能、
压缩上下文或安排任务，也不向标准模型请求注入 DAG。

## 启动独立模型服务

准备网关的版本化 JSON 配置，引用自己的 provider、模型、价格、策略及凭证环境变量。
配置示意与完整边界见[仓库中的独立模型接口说明](https://github.com/AEALab/RefractRouter/blob/main/docs/independent-model-router.md)。
空 `planningRouting` 不是可运行配置，DSH 设置不能直接当作独立网关凭证。

```bash
refractrouter-gateway --config /绝对路径/gateway.json \
  --runs-dir /绝对路径/router-evidence --preflight
refractrouter-gateway --config /绝对路径/gateway.json \
  --runs-dir /绝对路径/router-evidence --host 127.0.0.1 --port 8088
```

预检不调用模型。服务认证由配置中的 `authTokenEnv` 指定；这个 Router token 与上游模型 key 分开。
非回环部署另需要 TLS、访问控制和运维措施，本版不把本机验收称为完整团队部署。

## 模型与协议

Base URL：`http://127.0.0.1:8088/v1`。

虚拟模型：`refract/static`、`refract/stage`、`refract/task`、`refract/composite`、
`refract/advisor`、`refract/escalation`。`/v1/models` 只列出配置预检可用的策略。
Chat Completions 与 Responses 提供已接通的文本/function 子集。

Codex 自定义 provider 使用 `wire_api="responses"`，设置 `request_max_retries=0`、
`stream_max_retries=0`，保留原有模型目录和提示。根据网关能力配置执行推理断言；
混合或未配置推理档位时不要强行传一个不匹配值。

项目提供 `validation/codex/model_catalog.py` 为本机目录追加路由项。它保留宿主指令，
不把目录中的提示上传给 Router。使用方法和 CLI 参数以安装的 Codex 版本与仓库指南为准。

## 哪些能力不能假设已接通

当前网关不能悄悄忽略媒体、托管 web search、custom tool、加密推理历史或
`previous_response_id` 增量存储。请求须符合完整文本/function 历史与 `store=false` 的范围。
本机 CLI 验收不代表 Codex App、远程代理或所有品牌客户端完整兼容。

## Stage / Composite 的工具证据

纯 Base URL 工具结果通常没有可信退出状态。基本工具往返可工作，结果仍可能标为无法分类，
不能证明自然重复失败接管。

可选客户端证据适配利用 Codex 原生事件与 PostToolUse hook 进行唯一配对，再提交工具事实。
接线、hook 信任及限制详见[客户端工具证据说明](https://github.com/AEALab/RefractRouter/blob/main/docs/client-tool-evidence.md)。
不要为了接入绕过日常 hook 信任或覆盖已有 hooks。无法唯一匹配的并行结果保持未知。

## 验证范围

DSH 与 Codex CLI 是当前维护的接入范围。Static 工具往返、协议转换和部分策略接线已有证据；
每策略、每 Judge 的真实质量与客户端矩阵分别核对。历史 Hermes 实验保留，不作为本次新增支持承诺。
