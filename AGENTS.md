# 项目规范

## 文档与 GitHub 内容语言

- 所有新建或更新时撰写的项目文档一律使用中文，包括 README、架构说明、设计方案、
  使用指南、测试报告、实验分析、变更日志及项目规范。
- 所有在 GitHub 上撰写的内容一律使用中文，包括 Issue、Pull Request、Discussion、
  评论、评审意见、Release 说明和 Wiki 页面的标题与正文。
- Git 提交标题和说明也使用中文，保证同步到 GitHub 的记录符合上述要求。
- 代码、命令、路径、API 名称、配置键、专有名词和必要的原文引用保留其准确形式；
  配套说明使用中文。
- 历史实验原始证据继续保持原样；新增的解释、分析和总结使用中文。

## 项目结构与模块组织

Python 核心实现位于 `src/refractrouter/`，实验入口位于 `experiments/`。
DSH 插件的 TypeScript 源码和契约测试分别位于 `validation/dsh/plugin/src/` 和
`validation/dsh/plugin/tests/`。
冻结任务、来源材料、模型清单与评分规则位于 `data/`，Python 测试位于 `tests/`，
DSH 集成位于 `validation/dsh/`。历史证据位于 `reports/`，必须保留已完成实验的原始产物。

## 核心与 DSH 插件定位

- 保持单仓库，通过目录和职责区分 Router 核心、实验验证与 DSH 插件，不另建插件仓库。
- RefractRouter 的核心是任务分解感知的模型路由能力。DAG 规划与校验、节点选模、
  组合执行、预算记账和最终评估属于 Python 核心及其应用运行时。
- DSH 插件是宿主适配层，用于验证核心功能的可行性；“DSH + 插件连接核心 Router”
  也是未来产品化的实现形态之一。不得将插件描述为项目核心或唯一产品入口。
- DSH 的配置、工具注册、会话、凭证和进程接口留在集成层；核心业务接口不得绑定
  DSH 类型或要求 DSH 会话。插件负责传递请求和展示结果，不重复实现节点选模。
- 当前插件通过本地 Python runner 调用核心，执行时仍依赖匹配的源码环境。
  文档必须区分当前实现与未来部署目标，不得将其描述为已提供独立 Router 服务。
- 插件安装、启动或模拟执行通过，只证明对应集成路径可用；核心路由收益仍须通过
  独立的质量、成本、时延评估验证。

## 实现语言与职责边界

- Python 负责 Router 业务逻辑：任务 DAG、节点执行与模型分配、策略、评分与评测、
  数据集、适配器、成本与时延统计，以及实验 runner。
- TypeScript 负责 DSH 插件入口、配置与工具类型、宿主集成、进程与凭据边界、
  结构化结果，以及插件契约测试。
- 不得在 TypeScript 中重复实现路由、评分、预算记账或 Go/No-go 判定。
  插件可以在调用作为判定依据的 Python runner 前检查部署级限制。
- Markdown、JSON 和 YAML 属于文档或数据格式。允许使用 TypeScript 编译生成的
  JavaScript 作为运行产物，不得新增手写 JavaScript 实现。
- 新增实现语言或跨层复制业务逻辑，须先在架构 Issue 或 ADR 中记录提案，
  并在合并前取得维护者批准。提案须说明职责归属、替代方案、成本、行为偏差防范、
  验证和回滚方式。详见 `docs/architecture.md`。

## 构建、测试与开发命令

使用 `uv sync --frozen --extra dev --extra deepagents` 安装 Python 依赖。
先执行 `npm ci --prefix validation/dsh/plugin` 安装锁定的 TypeScript 构建工具，
再执行 `npm run --prefix validation/dsh/plugin typecheck` 进行严格类型检查，
使用 `npm run --prefix validation/dsh/plugin build` 构建插件。

`uv run pytest` 运行完整测试套件，包括 TypeScript DSH 契约测试。
插件入口为编译生成的 `dist/index.js`，执行 `dsh plugin add` 前必须先构建。
不得手动编辑或提交 `dist/`、`.test-dist/`；`npm pack` 通过 `prepack` 自动构建分发产物。

`experiments/run_real_v0_1.py` 默认执行零模型调用预检。
付费运行必须取得明确范围与预算的授权，并使用新的输出路径。
用户已明确说明使用 Ark Agent Plan 订阅，并授权继续当前 Issue #32 验证期间，
不再逐项请求 AFP 预算确认；按冻结预检自动设置运行上限，继续保留用量与 AFP 比较指标。
这项授权不表示无限调用额度，也不取消零重试、单轮首错停止、版本冻结与证据保留要求。
本项目的 Ark 调用必须使用 Agent Plan `/api/plan/v3` 端点。

## 编码风格与命名

目前未配置语言专用的格式化工具或静态检查工具。
Markdown 各节之间保留一个空行，在适合换行的位置尽量将行长控制在 100 个字符附近。
标题使用简洁的中文。文件名优先采用含义明确的小写英文与连字符，
例如 `architecture-overview.md`。引入新框架或语言时，遵循其格式约定。

## 测试规范

Python 行为测试放在 `tests/`，TypeScript DSH 契约测试放在
`validation/dsh/plugin/tests/`。
使用确定性模拟适配器和模拟评审响应进行无网络测试；测试中不得发起付费模型调用。
每次创建 Pull Request 前必须运行 `uv run pytest`。

## 提交与 Pull Request 规范

提交标题使用简短的中文祈使句，例如“添加路由基准测试”。
变更原因不明显时，在提交说明中补充原因。
Pull Request 的标题和正文使用中文，清楚说明变更目的、范围、验证结果，
并链接相关 Issue 或规范。

## 安全与配置

不得提交密钥、凭据或环境专用配置。
出现生成文件或依赖目录时，应在 `.gitignore` 中补充相应规则。
