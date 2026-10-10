# RefractRouter DSH 插件

DSH 插件是独立 Python Router 的宿主适配层，提供模型入口、配置与动态图形。
模型选择、审核、预算与结算由 Python 负责；工具执行、权限、上下文压缩、会话和委派由 DSH 负责。
标准 Base URL 接入不依赖这个插件。

当前开发预览：插件 **0.33.21**、Python 核心 **0.16.33**；已验证 DSH **0.1.5-rc.3**、
Node.js **≥22.19.0 且 <23**、pnpm **10.15.0**。核对日期：2026-10-10。

## 用户下载安装

从[线上下载与安装指南](https://aealab.github.io/RefractRouter/installation.html)取得匹配的
wheel、tgz、源码及 SHA-256 文件，也可阅读[仓库指南](../../../docs/refractagent-local-quickstart.md)。
插件尚未公开到 npm，不要通过同名 registry 包安装。

```bash
uv tool install ./refractrouter-0.16.33-py3-none-any.whl
uv tool update-shell
export PATH="$(uv tool dir --bin):$PATH"
refractagent --help
dsh plugin --profile web add ./dsh-refractrouter-validation-0.33.21.tgz \
  --offline --ignore-scripts
```

`web` 替换为自己的既有 profile。安装前保存旧包与配置备份；按原参数重启 DSH，
沿用原 `DSH_HOME`、工作目录、provider 与凭证，不以新的隔离 profile 替换日常环境。
首次安装时的空模型池初始化见[DSH 接入](https://aealab.github.io/RefractRouter/integrations/dsh.html)。

## 两个模型入口

| 入口 | 执行方式 | 设置 |
| --- | --- | --- |
| RefractAgent 规划路由 | 六种策略选模或审核，保持 DSH 原生 Agent 循环 | 独立规划路由卡片；模型菜单的“路由模式” |
| RefractAgent 自动路由 | 独立 Direct / DAG 研究入口，先判断是否值得拆分 | 独立自动路由卡片；真实执行必须显式启用 |

规划策略为 Static、Stage、Task、Composite、Advisor Gate 和 Escalation。
Static 当前固定高效角色，Random 在高效／强执行两个角色之间抽取；Task 使用有序多模型池。
Stage 从新增可信证据换模；Composite 先 Task 选常用模型，再 Stage 临时接管。
Advisor 最终审核最多两次、返工一次；Escalation 必要时丢弃候选并锁定接管模型。
详细规则与验证范围见[线上策略说明](https://aealab.github.io/RefractRouter/strategies/index.html)。

未配置完成时，零调用诊断列出缺项，不用模拟回答冒充真实执行。策略值 `rr:stage` 等由适配器
转成内部策略，不能传给底层模型的 `reasoning_effort`。物理模型的推理等级由自己的配置决定。

## 生产模块与可选验收工具

分发包只需启用生产路由模块。`validation-tools` 默认关闭，不需要在生产环境同时启用。
历史包名和模块 ID 保留用于配置兼容，名称里的 `validation` 不代表必须启用实验工具。

| 导出 | 用途 |
| --- | --- |
| 包主入口 `dist/entry.js` | DSH 前端发现及生产路由；以 `entryMode: routing` 配置 |
| `/routing`、`/agent` | 底层路由适配接口；只启用子路径可能不能发现前端 |
| `/validation-tools` | 可选 `refractrouter_validate`、`refractrouter_task` 研究工具 |
| `/client` | 构建后的 DSH 前端，非独立服务 |

`conversation.view` 同时保留任务 DAG 与路由轨迹页签；`settings.plugin.item` 提供两个设置卡片。
记录可收合，展示开始时间、耗时、实际模型与动态状态。历史来源缺字段时提示缺项，不套用当前配置。

历史验证与文本任务工具依赖匹配源码环境；生产 RefractAgent 模型入口可用已安装核心脱离源码运行。
配置中的 `pythonExecutable` 默认是 `refractagent`，须能在 DSH 的启动 PATH 中找到。

## 模型、Judge 与费用

- 模型与凭证复用 DSH 目录；系统按实际 provider、接口与版本核对能力及价格。
- 新版规划配置 v7、自动模型池 v5 采用现金与参考金额，不增加 AFP 预算。Ark 订阅继续使用
  `/api/plan/v3`；订阅单次增量现金与公开价格参考估值分开，不相加、不把订阅月费当成零。
- 历史 AFP 配置与证据按原合同读取，升级需明确操作，不自动折算或修改旧费用。
- Jev 默认新配置使用 OpenRouter；直接 Typesafe.ai、本地 Laya 和 DSH LLM 为不同后端。
  云端凭证通过引用解析，不放入插件配置、源码或浏览器。Laya 的质量未达标用途保留实验标识。
- 规划预算、期限和最大调用数支持 `0＝不限制 Router 对应上限`，提供方容量与宿主权限仍有效。
- 取消释放未派发保护额度；已派发未知用量继续保留待核对预留并停止，不自动 HTTP 重试。
- 账本仅覆盖受管模型调用，不宣称覆盖所有宿主工具、独立子 Agent 或订阅月费。

本地／外部云／可信云／模拟本地是部署与数据域声明，不是能力等级。
云端需要独立授权；把 Judge 设为本地不会授权其他云端执行模型。

## 从源码构建

以下命令在仓库根目录执行：

```bash
uv sync --frozen --extra dev --extra deepagents
npm ci --prefix validation/dsh/plugin
npm run --prefix validation/dsh/plugin typecheck
npm run --prefix validation/dsh/plugin test:contracts
npm run --prefix validation/dsh/plugin build
npm pack ./validation/dsh/plugin --pack-destination ./dist
uv run pytest
```

`npm pack` 的 `prepack` 会自动构建。不要手动编辑 `dist/`、`.test-dist/` 或提交生成目录。
历史变更按[变更日志](CHANGELOG.md)读取，不将旧版本限制写成当前默认值。

## 验收与故障处理

源码、构建包、安装包和运行界面分别核对。没有模型调用的生命周期验证只证明安装路径：

```bash
python3 scripts/validate_dsh_plugin_lifecycle.py --packed
```

这个开发脚本使用临时目录，不能替换用户 profile。启用研究工具后，即使工具本身只预检，
DSH 外层助手也可能收费；不要把 DSH 对话描述成必然零费用。

每次升级先检查原安装来源，再确认两张卡片、两个页签、节点和连线、策略选择、原模型与凭证。
出现价格缺项、未知用量、replay 不兼容或基础设施错误时查对应记录，不删历史、不填假价格，
也不扩大额度掩盖故障。

自适应审核的低风险跳过已完成原 profile 真实检查；本轮 GLM low 最终审核遇到 429，
尚未完成真实审核／纠正质量验收。媒体完整流程与 P6 共享预算也仍需独立验收。
当前新增维护范围为 DSH 与 Codex CLI，Hermes 历史证据保留。

## 深入阅读

- [项目定位与宿主边界](../../../docs/independent-model-router.md)
- [规划路由日常使用](../../../docs/planning-routing-daily-use.md)
- [金额计价迁移](../../../docs/currency-only-migration.md)
- [自动路由最终审核](../../../docs/automatic-review-settings.md)
- [历史研究与实验索引](../../../docs/research-index.md)
- [线上版本与验证范围](https://aealab.github.io/RefractRouter/status.html)
