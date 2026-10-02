# 官方 Jev 与原有 DSH profile 接线核对

日期：2026-10-02。范围为用户原有 `web` profile 的设置、零调用诊断和构建安装；
没有创建新的 profile，也没有执行 DSH 中的付费模型任务。

## 发现与修复

原有 profile 的 TypeScript 插件已包含 Jev 选项，但 `refractagent` 指向的 Python
工具仍是同版本号的旧 wheel。Advisor 切换为 Jev 后，设置可保存，零调用检查却报
`advisor.judge.type 必须是 llm 或 local-decision`。单独使用 `uv tool install --force`
复用了旧 wheel；使用 `--force --reinstall` 后，已安装核心包含 Jev 合同与校验。

发布版本升为 Python 0.15.5、插件 0.29.1。插件的零调用检查先核对核心能力，
缺少 `jev-judge-v1` 时给出明确升级提示。安装包从当前源码构建；原有 profile
的依赖清单指向 0.29.1 包，运行时插件仍由该 profile 已有的工作树链接加载。

## 实际核对

- DSH `0.1.5-rc.3`、Python 核心 `0.15.5`、插件 `0.29.1`；本地 `laya-mlx`
  依赖保留。
- 原有会话、RefractAgent 规划路由模型入口、规划路由与自动路由两张设置卡仍可见。
- 在只对当前 DSH 进程提供临时 Jev 凭证的条件下，分别保存 Advisor、Escalation、
  Task、Stage 协作模式及 Composite 的 Jev 设置；零调用诊断均显示可用。
- 已把临时策略选择恢复到原有设置；再次检查六种策略均显示可用。临时凭证未写入
  仓库或原有 DSH 凭证文件。
- `uv run pytest -q`：1477 个测试及 5 个子测试通过；TypeScript 类型检查通过。
  Python wheel 和插件 tarball 构建成功，包内含 Jev 接线文件。

本次 DSH 界面核对没有生产模型调用，因此本次费用为 0 AFP、0 CNY。过去的官方
Jev 固定题真实结果见 [Judge 后端对比](../judge-backend-comparison-20261001/README.md)
和 [Choice 分动作留出题](../jev-choice-action-gate-20261001/README.md)；这些结果
不能替代 DSH 的端到端接线验收。Jev 当前按外部云数据域处理，DSH 系统指令中含本机
绝对路径；取得对 Jev 这条路线的明确授权后，再做有限的真实接线任务并记录用量。
