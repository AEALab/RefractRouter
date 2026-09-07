# Ark Agent Plan 模型清单

本清单于 2026-09-07 对照用户提供的
[套餐概览](https://console.volcengine.com/ark/region:cn-beijing/docs/82379/2366394?projectName=default&lang=zh)
及相同文档 ID 的[公开页面](https://www.volcengine.com/docs/82379/2366394?lang=zh)整理。
机器可读文件为 [JSON 快照](../data/model-catalogs/ark-agent-plan-2026-09-07.json)，共 **19 个模型**。
型号采用套餐文档中的 model name；实际账户档位尚未读取，文档支持不等于每个账户均有权限。

现有报告 DAG 是文字任务。本次准入实验继续使用冻结的 Flash、M3、Pro 三候选及独立 K3
judge；新清单可用于规划后续模型组合。没有修改原 manifest 的价格、角色、prompt 或实验结果。

## 文本生成：11 个

长度采用文档的十进制 k 表示法；价格为常规输入／输出抵扣系数，每 10,000 token 计 AFP。
字段是模型能力上限，benchmark 的单次输出仍限制为 8192 token。

| Model name | 上下文 / 最大输出 | 常规输入 / 输出系数 | 套餐 | 备注 |
|---|---|---|---|---|
| `doubao-seed-2.0-mini` | 256k / 128k | 0.25 / 0.25 | 全部 | 新增文本候选清单 |
| `doubao-seed-2.0-lite` | 256k / 128k | 0.5 / 0.5 | 全部 | 新增文本候选清单 |
| `deepseek-v4-flash` | 1024k / 384k | 0.5 / 0.5 | 全部 | 已有冻结真实执行证据 |
| `glm-5.3-flash` | 1024k / 128k | 0.5 / 0.5 | 全部 | 官方明确支持图片输入；有期限折扣 |
| `doubao-seed-2.1-turbo` | 256k / 256k | 2.5 / 2.5 | 全部 | 新增文本候选清单 |
| `doubao-seed-evolving` | 1024k / 256k | 2.5 / 2.5 | 全部 | 新增文本候选清单 |
| `minimax-m3` | 1024k / 128k | 2.5 / 2.5 | 全部 | 已有真实执行证据；结构化输出使用 prompt-only |
| `glm-5.3` | 1024k / 128k | 4.5 / 4.5 | 全部 | 文档也列出 `glm-latest`；不能关闭思考 |
| `kimi-k2.7-code` | 256k / 32k | 4.5 / 4.5 | 全部 | 新增文本候选清单 |
| `deepseek-v4-pro` | 1024k / 384k | 5.5 / 5.5 | 全部 | 已有冻结真实执行证据 |
| `kimi-k3` | 1024k / 128k | 10 / 10 | Medium / Large / Max | 当前独立 judge，不可同时作为同一实验候选 |

GLM-5.3 强制开启思考，不能直接继承当前 manifest 的 `thinking: disabled`。
在将其纳入新 benchmark 前应另冻思考策略、输出预算与遥测比较口径。
其他新增模型的 JSON、thinking 和节点契约兼容性均需先验证，不能由型号列表推定。

GLM-5.3-Flash 的输入与输出系数在 **2026-08-28 至 2026-09-11 23:59:59（中国时间）**
限时为 0.25；JSON 同时保留常规系数和活动起止时间，不将临时折扣写成永久价格。
计费与活动来源：[AFP 抵扣规则](https://www.volcengine.com/docs/82379/2516283?lang=zh)、
[限时折扣](https://www.volcengine.com/docs/82379/2533565)。

## 其他能力：8 个

| Model name | 能力 | 套餐与状态 | AFP 计费依据 |
|---|---|---|---|
| `doubao-embedding-vision` | 向量化 | 全部；上下文 128k | 输入／输出系数 0.5，每 10,000 token |
| `doubao-seedream-5.0-lite` | 图片生成 | 全部 | 每成功生成一张图片 99 AFP |
| `doubao-seedance-1.5-pro` | 视频生成 | 文档标为即将下线；档位说明有冲突 | 每 10,000 视频 token，无声 36／有声 72 |
| `doubao-seedance-2.0` | 视频生成 | Large / Max | 系数取决于分辨率和是否输入视频，见 JSON 的 variants |
| `doubao-seedance-2.0-fast` | 视频生成 | Large / Max | 含输入视频 110，否则 185，每 10,000 视频 token |
| `doubao-seedance-2.0-mini` | 视频生成 | Large / Max | 含输入视频 70，否则 115，每 10,000 视频 token |
| `doubao-seed-tts-2.0` | 语音合成 | 全部 | 每万字符 1350 AFP |
| `doubao-seed-asr-2.0` | 语音识别 | 全部 | 每小时音频 450 AFP |

Seedance 1.5 Pro 的表格列出 Medium 支持，但同页说明 Small／Medium 不支持视频生成。
清单保留这一冲突与即将下线状态；使用前需在控制台确认，不将其选为新集成默认项。

这些能力需要对应 adapter、请求／产物 schema、成本与质量评估，并非替换文字模型 ID 就能
加入现有七节点 DAG。现有 Python 实现仅支持文字模型调用；清单不会通过通用文字
`chat-completions` 误调图片、视频、向量或语音模型。所有模型能力与套餐限制来自
[官方概览](https://www.volcengine.com/docs/82379/2366394?lang=zh)，抵扣规则来自
[官方 AFP 文档](https://www.volcengine.com/docs/82379/2516283?lang=zh)。

## 使用方式与验证边界

```bash
uv run python -m refractrouter.model_catalog
uv run python -m refractrouter.model_catalog --capability text-generation --plan-tier large --json
uv run python -m refractrouter.model_catalog --capability video-generation --plan-tier large --json
```

清单命令不联网、不解析凭据、不改变实验候选池。`live_verified` 只标记仓库中已有真实调用
证据的四个型号，不代表其他模型不可用，也不证明新的账户套餐权限。

官方说明文字与向量化权益通过受支持的 AI 工具使用；本项目保留 DSH 外层验证边界和
`https://ark.cn-beijing.volces.com/api/plan/v3` 专属地址。清单没有添加后付费回退路径。
`auto` 属于供应商动态路由模式，不作为一个固定模型混入节点模型池；搜索、记忆等 Harness
能力也不伪装成模型条目。账号用量、凭据和账单没有写入清单。
