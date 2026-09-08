# 用户 provider 配置验证

本次将 Ark Agent Plan 从隐式运行依赖调整为显式可选 provider／预设。
Python 核心 0.3.0 编译用户配置并执行路由，DSH 插件 0.11.0 处理配置、凭证和宿主调用。
配置范围与迁移见 [使用说明](provider-configuration.md)，关联 [应用交付 #41](https://github.com/AEALab/RefractRouter/issues/41)。

## 行为验证

- 同名 API 模型分属不同 provider 时，策略选择与结果中的 provider 一致。
- 一个候选加一个评审可以完成短任务，自动生成计划按实际输入设置容量要求。
- 预设比较 DAG 保留依赖结果；生产和评审可指定不同 provider。
- 不同计费单位、无效价格、未知 provider、配置中的原始密钥和递归路由在执行前拒绝。
- 用户预测 profile 使用 `configured` 且 `samples: 0`，不能通过历史研究的实测数据条件。
- HTTP 请求使用各自端点、凭证和 token 上限参数；无认证服务可以显式省略凭证引用。
- DSH 的多凭证通过专用子进程环境传递；原生 provider 凭证保留在宿主；错误包含多个凭证时逐一脱敏。
- 插件配置注册后复制并冻结，避免调用期间候选或凭证引用发生变化。

## 已安装包与真实 DSH 联调

复现命令使用全新输出目录：

```bash
python3 scripts/validate_refractagent_install.py --configured-providers \
  --output /tmp/refractagent-provider-acceptance
```

脚本在源码目录以外安装 wheel 和 tgz，以独立 DSH profile 运行三个策略的零调用演示。
随后启动仅监听本机随机端口的确定性 HTTP 模拟服务，使用已安装的核心执行以下路径：

| 路径 | 生产 | 评审 | 本机 HTTP 调用数 |
| --- | --- | --- | ---: |
| 直接 provider | Python Chat Completions | Python Chat Completions | 2 |
| DSH 原生 provider | DSH 原生 SSE 调用 | DSH 原生 SSE 调用 | 2 |
| 混合 provider | Python Chat Completions | DSH 原生 SSE 调用 | 2 |
| Responses | Python Responses | Python Responses | 2 |

四种路径均完成答案、独立评审和 USD 用量归档，未确认费用为零。
脚本核对请求端点、凭证归属、最终模型、调用次数与任务文件中没有凭证值。
这些是本机模拟响应，外部模型调用为零，不是各厂商模型可用性或路由收益验收。

## 历史 K3 兼容

首次回归发现新增模型字段影响历史序列化，因此将 HTTP 扩展字段移到应用专用模型子类型。
基础模型类型及历史非代码配置保持完全一致。共享客户端仍按历史默认要求认证并发送
`max_completion_tokens`；已有归档解析与费用测试继续核对输出、用量和 9.154 AFP 成本。

兼容清单仅追加原始成功基线、原始索引和本次精确目标代码快照的对应记录。
恢复测试验证零模型调用和原始证据哈希不变；未登记代码仍被拒绝，已完成节点材料的
跨版本 compose/finalize 仍被拒绝。没有修改历史任务、价格、评审或实验结果。

## Responses 补充验证

- Responses 请求使用 `input`、`reasoning`、`text.format` 与 `max_output_tokens`，不自动注入采样参数。
- 大于 8192 的推理用量按完整输出上限预留并结算；推理明细不重复计费。
- 截断、拒绝和失败先结算已知用量，再拒绝作为成功正文；缺失或非法用量保留未确认预留。
- reasoning 条目与工具调用不会被拼入最终正文，未知工具输出不能当作成功文本节点。
- 基础模型序列化和历史上限不变；追加仅适用于新协议代码快照的 K3 兼容记录。

## 回归结果

- `uv run --frozen pytest -q`：446 项测试、5 项子测试通过（53.34 秒）。
- `npm run --prefix validation/dsh/plugin typecheck`：严格类型检查通过。
- 安装联调包含三策略演示及四种 provider 路径；所有外部模型调用数为零。

## 验证边界

单元与契约测试不调用付费模型；安装联调仅调用本机模拟服务。
新增配置未对外部厂商逐一做真实调用验证。直接接口支持 Chat Completions 与 Responses；
其他协议通过 DSH provider 适配，RefractAgent 仍只处理文本任务。
