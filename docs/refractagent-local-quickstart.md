# 下载安装

本指南对应开发预览：Python 核心 **0.16.33**、DSH 插件 **0.33.21**。
已验证 DSH **0.1.5-rc.3**；核对日期为 **2026-10-10**。
本页下载来自本项目构建，不包含模型密钥、用户配置或会话。

## 选择安装方式

| 你的情况 | 需要安装 |
| --- | --- |
| 在 DSH 中使用设置和图形 | Python 核心 wheel + DSH 插件 tgz |
| 让 Codex CLI 通过 Base URL 使用规划策略 | Python 核心 wheel + 独立网关配置；不需要 DSH 插件 |
| 开发、研究或修改项目 | 源码、开发依赖及构建工具 |

插件目前没有公开 npm 包。不要执行 `npm install dsh-refractrouter-validation`。
Python 核心也请使用本页 wheel，避免从同名或未经核对的发行包安装。

## 环境要求

| 组件 | 要求 | 核对命令 |
| --- | --- | --- |
| Python | ≥3.11；本次安装验证为 3.12 | `python3 --version` |
| uv | 支持 `tool install`、`build` | `uv --version` |
| Node.js | ≥22.19.0 且 <23 | `node --version` |
| pnpm | 已验证 10.15.0 | `pnpm --version` |
| DSH | 已验证 0.1.5-rc.3 | `dsh --version` |

本指南命令面向 macOS / Linux 的 Bash 或 Zsh。Windows 原生完整安装尚未独立验收。
本地 Laya-MLX 另要求兼容的 Apple Silicon macOS；使用云端 Judge 不需要安装 MLX。

首次安装 DSH 时执行：

```bash
npm install --global --before=2026-09-27T00:00:00Z \
  pnpm@10.15.0 @deepseek-ai/dsh@0.1.5-rc.3
```

解析日期与项目 CI 一致，用于固定 DSH 内部宽松依赖。已有 DSH 时先核对版本与现有插件，
不要为了安装 Router 重建 profile。uv 的安装方法见[官方指南](https://docs.astral.sh/uv/getting-started/installation/)。

## 下载预览包

- [推荐离线安装包：refractrouter-install-0.16.33.zip](https://aealab.github.io/RefractRouter/downloads/refractrouter-install-0.16.33.zip)
- [Python 核心：refractrouter-0.16.33-py3-none-any.whl](https://aealab.github.io/RefractRouter/downloads/refractrouter-0.16.33-py3-none-any.whl)
- [DSH 插件：dsh-refractrouter-validation-0.33.21.tgz](https://aealab.github.io/RefractRouter/downloads/dsh-refractrouter-validation-0.33.21.tgz)
- [对应源码：refractrouter-source-0.16.33.zip](https://aealab.github.io/RefractRouter/downloads/refractrouter-source-0.16.33.zip)
- [SHA-256 校验文件](https://aealab.github.io/RefractRouter/downloads/SHA256SUMS.txt)
- [构建与版本清单](https://aealab.github.io/RefractRouter/downloads/build-manifest.json)

推荐下载并解压离线安装包：其中包含 wheel、tgz、两份指南及对应的校验文件。
把解压目录长期保存，再检查下载完整性：

```bash
cd /你保存安装包的目录
# macOS
shasum -a 256 -c SHA256SUMS.txt
# Linux 可以使用 sha256sum -c SHA256SUMS.txt
```

离线安装包内部的校验文件只核对 wheel 与 tgz。网页提供的独立校验文件还包含
源码和安装 zip；若只单独下载部分文件，核对该文件对应的 SHA-256 行。
本次是开发预览，不把尚未发布的 GitHub Release 或 npm 包写成正式发行渠道。

## 安装 Python 核心

在保存安装包的目录执行：

```bash
uv tool install ./refractrouter-0.16.33-py3-none-any.whl
uv tool update-shell
```

重新打开终端，或在当前终端临时补充 PATH：

```bash
export PATH="$(uv tool dir --bin):$PATH"
refractagent --help
refractrouter-gateway --help
```

这两条帮助命令不调用模型。`uv tool` 把核心安装在独立环境中，运行不依赖源码目录。
DSH 也必须能从启动环境找到 `refractagent`；高级部署设置可以指定命令的绝对路径。

## 安装到已有 DSH profile

先停止正在运行的 DSH 服务，保存原有设置、凭证文件和 profile 补丁的本地备份。
继续使用你原来的 `DSH_HOME` 和 profile；**不要新建隔离配置来替换日常环境**。

以下示例使用 `web`，如果你的实际 profile 名不同，请替换：

```bash
dsh plugin --profile web add ./dsh-refractrouter-validation-0.33.21.tgz \
  --offline --ignore-scripts
```

`--ignore-scripts` 跳过安装期脚本，分发包已经编译。首次安装仍须具备 DSH 所需的宿主依赖；
本地包安装报离线缺项时核对 pnpm 与已有 DSH 安装，不用新的 profile 隐藏错误。

生产包启用路由入口，`validation-tools` 是可选研究工具，默认关闭。它们来自同一个包，
不需要为日常使用同时启用两个模块。

## 启动 DSH

在希望保存工作与运行记录的目录执行：

```bash
mkdir -p "$HOME/RefractWorkspace"
cd "$HOME/RefractWorkspace"
dsh --profile web --host 127.0.0.1 --port 3080
```

打开终端显示的[本机地址](http://127.0.0.1:3080/)，按 DSH 的原有认证流程进入。
端口被占用时选择空闲端口；升级已有服务时沿用原启动参数和原工作目录。

::: info 首次安装自动路由的初始化
若是全新安装、自动路由设置仍显示旧三档入口，可以下载
[首次安装设置草稿](https://aealab.github.io/RefractRouter/examples/dsh-first-install.json)，核对其中的预算与设置，
再按 [DSH 接入](https://aealab.github.io/RefractRouter/integrations/dsh.html#首次安装设置草稿) 初始化。草稿不包含可执行模型或密钥，
真实调用默认关闭。**已有 Router 设置的用户不要加载此草稿。**
:::

接下来按[第一项任务](https://aealab.github.io/RefractRouter/quickstart.html)配置模型、数据域与预算。默认模拟和零调用检查不是真实模型工作。

## 从源码构建

源码 zip 对应本页的预览包。仓库 `main` 的版本以其 `pyproject.toml` 和插件 `package.json`
为准，不假定任何时候都等于这份预览。

```bash
git clone https://github.com/AEALab/RefractRouter.git
cd RefractRouter
uv build --wheel
npm ci --prefix validation/dsh/plugin
npm pack ./validation/dsh/plugin --pack-destination ./dist
```

或解压本页源码 zip，进入 `RefractRouter` 后执行后三条命令。`dist/` 中会产生 wheel 与 tgz；
按照实际文件版本安装。普通使用者不需要安装 DeepAgents、运行 benchmark 或启用验收工具。

## 升级与回滚

升级时先核对安装版本、当前 profile 和是否使用尚未合入的开发包，再保存旧 wheel、tgz 与设置备份：

```bash
uv tool install --reinstall ./refractrouter-0.16.33-py3-none-any.whl
dsh plugin --profile web add ./dsh-refractrouter-validation-0.33.21.tgz \
  --offline --ignore-scripts
```

随后按原参数重启 DSH，检查两个设置卡片、模型、DAG 页签及路由轨迹。先跑零调用诊断，
再新建任务验证。升级不应改变预算、信任授权、推理默认值或旧会话。
回滚时重新安装保存的上一组包；需要恢复设置时使用本地备份，保留运行记录及未知费用预留。

## 仅使用标准模型接口

安装核心后，准备自己的网关配置并启动 `refractrouter-gateway`。
本机 Base URL 为 `http://127.0.0.1:8088/v1`，提供六种规划策略。
详见 [Codex CLI 接入](https://aealab.github.io/RefractRouter/integrations/codex.html)。DSH 网页地址不能作为模型 Base URL。
