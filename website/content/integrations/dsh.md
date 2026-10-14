# DSH 接入

DSH 插件连接独立 Python 核心，提供两种模型入口、设置卡片、工具事件与图形展示。
默认本机接入无需单独启动 Router HTTP 服务。

## 安装后的检查

1. `refractagent --help` 在启动 DSH 的同一环境可用。
2. 生产路由模块启用，`validation-tools` 保持关闭。
3. 设置中同时看到 **RefractAgent 规划路由** 和 **RefractAgent 自动路由**。
4. 会话中看到 **任务 DAG** 与 **路由轨迹** 两个页签。
5. 原来的 provider、凭证与会话仍在。

<figure class="doc-screenshot"><a href="/screenshots/dsh-20261014/settings-cards.png" target="_blank" rel="noopener"><img src="/screenshots/dsh-20261014/settings-cards.png" alt="实际 DSH 设置窗口：两个 RefractAgent 路由卡片"/></a><figcaption>2026-10-14 实际界面：安装正确时两张卡片同时出现。只看到一张或显示旧三档入口时，先核对插件版本与 profile。</figcaption></figure>

包名为历史兼容保留 `dsh-refractrouter-validation`，不表示需要启用验收工具。
生产入口通过包主入口加载前端；只启用 `/routing` 子路径可能不能发现设置与页签。

## 首次安装设置草稿

仅供**尚未配置 RefractRouter 的首次安装**。先下载
[dsh-first-install.json](/examples/dsh-first-install.json)，放到工作目录，
阅读里面的初始预算、真实执行关闭状态和空模型池，然后启动：

```bash
dsh --profile web --patch ./dsh-first-install.json \
  --host 127.0.0.1 --port 3080
```

随后从 DSH 目录选择自己的模型，登记信任策略与 Judge，按[第一项任务](../quickstart.md)
配置和保存。首次初始化阶段使用同一个补丁与工作目录启动；不要换到新 profile。
**已有 Router 用户直接按原启动方式升级，不加载这个草稿覆盖设置。**

草稿不包含可执行 provider、密钥或虚构价格，零调用诊断在你配置完成前会列出缺项。
不要为了消除提示填入零价格或把所有能力写成支持。

## 选择入口与路由模式

规划路由：在模型菜单选择规划入口，再用“路由模式”选择六策略之一。
策略标识由适配器转成内部策略，不作为底层 `reasoning_effort` 发送。

自动路由：选择“自动路由（真实执行）”，确认实时配置已启用；模拟入口仍为安装演示，
不能拿模拟文字当成真实回答。

<figure class="doc-screenshot compact"><a href="/screenshots/dsh-20261014/routing-mode-menu.png" target="_blank" rel="noopener"><img src="/screenshots/dsh-20261014/routing-mode-menu.png" alt="实际模型菜单中的路由入口"/></a><figcaption>模型菜单中的两个入口：规划路由按策略列出；自动路由的「模拟」与「真实执行」是两条不同路线。</figcaption></figure>

## 原生工具与模型历史

规划路由把被接受的模型工具调用原样交回 DSH。工具执行、权限、审批与后台委派由 DSH 管理。
自动路由的宿主工具调用也遵守 DSH 的执行与审批边界。

每条回复保存实际 provider、模型与 replay 来源；跨模型转换按已验收组合检查。
历史组合未通过时明确阻断，不把旧回复一律标成当前模型，也不删除工具配对来让请求通过。
上下文压缩由 DSH 负责，Router 保留归一化证据与消费事件 ID。

## 停止与恢复

使用 DSH 原生取消。插件或核心中断后未确认派发保留待核对状态，不自动重发可能已收费
或产生副作用的操作。重启后读取旧记录；新增配置只影响新任务。

## 用 Base URL 接入 DSH

也可不安装插件，在 DSH 配置标准 Chat Completions provider：
Base URL `http://127.0.0.1:8088/v1`，模型 `refract/static` 等。
这条路径提供标准模型服务，不自动得到插件设置、DAG 页签或原生结构化工具证据。
其能力以网关 `/v1/models` 与已验收合同为准。
