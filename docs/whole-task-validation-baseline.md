# 整任务选模开发的测试与评测基线

对应 [#202](https://github.com/AEALab/RefractRouter/issues/202)，属于
[#201](https://github.com/AEALab/RefractRouter/issues/201) 的首个前置工作。
六策略主体及宿主循环保持原样，本次新增测试防护、证据入口和整任务冻结合同。

## 可复现运行

先按项目规范安装锁定依赖：

```sh
uv sync --frozen --extra dev --extra deepagents
npm ci --prefix validation/dsh/plugin
npm run --prefix validation/dsh/plugin typecheck
npm run --prefix validation/dsh/plugin build
uv run python experiments/run_whole_task_baseline.py --output-dir /tmp/新的基线证据目录
```

入口内部执行完整 `uv run pytest`，没有付费、筛选测试或跳过文件的参数。
普通 `uv run pytest` 也会通过 `tests/conftest.py` 默认加载网络防护，
旧研究显式使用 `-p tests.offline_network_guard` 的方式仍可读取。
输出目录必须全新；不会覆盖既有证据。CI 上传同样的完整产物：

- `environment.json`：Python/Node/npm/uv、Git提交、工作区状态及Git列出文件的字节摘要，
  不保存凭证值；未提交文件也有身份，符号链接只绑定链接文本、不读取外部目标。
- `command.json`、`pytest.log`：实际执行命令、完整合并日志。
- `junit.xml`：完整测试结果，失败、错误和跳过均保留。
- `network.json`：防护范围、回环访问及被阻断外部尝试，以及收集/选中/取消选择/实际调用计数。
- `source-after.json`：运行后重算原源码清单；任何原文件字节未恢复也会阻断基线。
- `result.json`：真实退出码、耗时和基线判定；缺失证据、空测试、失败或跳过均不通过。

网络防护阻断本 pytest Python 进程中的外部 DNS、TCP/UDP 地址访问，允许回环模拟服务器。
回环正反向名称查询使用确定性本地映射，`getaddrinfo/getnameinfo` 只传数值地址，
不会将未在本地登记的127.0.0.2等地址交给系统PTR解析器。
直接socket连接/发包接口同样把localhost改为对应地址族的数值地址，再交给C层；
bind只接受数值地址或本地确定性映射，避免绕过Python名称解析包装。
负控测试会故意触发阻断，所以 `blocked_external` 不必为零。
它不是 OS 级网络沙箱，也不保证独立 Python/Node 子进程无法联网。
宿主契约仍使用模拟提供方；runner 不向子进程传递继承的认证变量，
不以此代替宿主文件隔离或宣称核对了真实供应商扣费。

runner 会清理继承的 `PYTEST_*`、`PYTHONPATH/PYTHONHOME`，显式选择完整 `tests` 目录，
并禁用隐式 `addopts`。收集数、选中数与实际调用数必须一致且大于0，取消选择必须为0；
JUnit 子测试可增加记录数，但不会被当作新增独立测试。没有计数证据也不能通过。
这是PR #212合并后独立审查发现的补充修正，原合并、CI和审查记录保留，#202重新打开跟踪。

## 基线与历史问题分开

2026-10-29 从远端 `main` 的 `0e58fd31b604142eba42e6c3953bbf0b1a4fa09c`
建立隔离工作区，安装锁定依赖后，原主线完整测试为 **2096 passed、5 subtests passed**。
该结果是加入本次变更前的基线，不包括随后新增的网络与评测合同测试。

旧研究工作区曾有全套运行中止记录，其中涉及端口权限、未加载防护 fixture 和
研究冻结指纹拒绝。那些原始记录保持原样；新工作区主线通过不能改写为旧工作区也通过。
研究原型不因本次 PR 自动合并；不能通过更新旧指纹或移走失败测试伪造全套通过。
环境禁止回环端口时属于该环境的集成测试阻塞，需要在允许本地端口的受支持环境运行，
不能把它当作路由算法质量问题，也不能跳过后宣称完整验收通过。

PR #212 首次 Linux CI 的已安装包验收发现另一个可见性错误：uv 工具环境放在临时
workspace 的兄弟目录，而 DSH 的 bwrap 使用空 `/tmp` 后只重新绑定 workspace。
因此宿主已安装的 Python 在沙箱内报告不存在。安装验收将 uv 工具与入口放入隔离
workspace 的 `.installation`，保持宿主沙箱策略不变，并以真实安装模拟验收复核。
这不修改用户安装位置或默认配置；首次失败和取消任务仍保留于 CI 记录。

## 整任务评测合同

`data/whole-task-routing/evaluation-contract-v1.json` 固定以下共同口径：

- 以独立任务为单位；失败、未交付及未知质量保留分母，未知不当通过。
- 质量优先，无新增关键缺陷；计划中的质量差界限 3 个百分点、单侧确定水平 95%。
- 目标完整模型费用省 20%，两个预冻结半批均省钱；小样本不足时不自动扩量。
- 费用包含全部执行尝试、分类和在线审核；丢弃/失败是调用标签，不重复计费。
- 共用研究评分另列并报告项目总支出；现金、参考估值、历史 AFP 分开。
- 保持模型原生输出上限、HTTP自动重试0；未知用量保留预留并停止新派发。
- 隐藏评估与模型、工具、缓存及可读日志隔离；旧题不重新取得留出身份。

`whole_task_protocol.freeze_study` 校验任务/来源分组、材料及验收摘要，冻结模型路线、工具、
宿主和交付合同摘要。工具收益配对必须使用相同路线，选模收益配对必须使用相同工具；
两种配对都须使用相同宿主与交付要求。输出保存完整快照及哈希，修改输入不会改变旧快照。

调用 `experiments/freeze_whole_task_study.py` 时必须显式提供实验声明、已暴露材料摘要列表及
新输出文件，例如：

```sh
uv run python experiments/freeze_whole_task_study.py --study /path/to/study.json \
  --exposed-materials /path/to/exposed.json --output /path/to/new-freeze.json
```

声明仅包含 `contract`、`tasks`、`arms`、`comparisons`；实际字段见对应合同测试。
来源清单为空不自动获得独立性认证。冻结器不提供 `--execute`，也不读取任务答案。

这是后续 #210 的合同基础，不能证明材料来源真实或不近重复，也没有冻结新的真实任务、
精确模型/价格包络、统计方法与观察点。因此输出始终 `liveExecutionReady=false`，
不得据此开始付费调用、宣称质量达标、启用新产品默认策略或关闭 #210。
后续需核对真实材料和模型快照，将费用与统计验收完整冻结后才可运行。
