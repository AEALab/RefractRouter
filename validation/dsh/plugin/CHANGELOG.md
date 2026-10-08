## 0.32.2

- 修复 DSH 只提供正文结束块时内容丢失，完整块覆盖增量且不重复正文。
- 自动路由模型池增加按宿主实际支持值选择推理等级，Python 验证并传递到调用。
- 不再把默认推理档位的时延观测套用到显式不同档位；旧配置继续继承提供方默认。
- 失败终止回执保留可核对用量用于结算；错误正文和工具调用仍拒绝交付。
- 对应核心版本 0.16.8，规划标识规范化保留依赖与审计原文，非法类型和冲突仍拒绝。

## 0.32.1

- 自动路由先执行 Python 零调用预检；明确禁止／强制 DAG 或简单任务不派发拆分 Judge。
- 本地与云端拆分 Judge 共用相同执行准入；不合格配置先停止，不先花判别费用。
- 核心增加标准模型接口的显式工具回执验收；Codex 增强接入启用可信状态检查。
- 对应核心版本 0.16.7，保留用户原 profile、预算、provider、凭证和默认策略。

## 0.31.1

- 修复“不调用工具”被当作工具必需条件的误判，封闭算术不因宿主提供工具而额外调用判别或评审。
- 工具额度不限时比较已知 direct／DAG 调用，明确后续工具费用未估计，保持逐次预算准入。
- 候选诊断包含实际 provider/model 和数据域排除原因，轨迹区分订阅参考估值与新增现金。
- 对应 Python 核心版本为 0.16.4，不更改用户原有模型、预算、信任与权限配置。

## 0.31.0

- 自动路由在拆分判别无法确定时执行完整任务并保留最终审核，避免只凭弱关键词付出规划调用。
- direct 与 DAG 选路同时检查参考额度和新增现金，覆盖允许的工具续接与最终评审。
- 路由轨迹逐模型说明质量画像和容量准入原因；通过基础检查后仍须通过数据域与预算检查。
- 对应 Python 核心版本为 0.16.3，旧自动路由与规划路由配置保持兼容。

## 0.30.2

- 修复金额版新增 Ark 模型与 Seedream 路线仍引入 AFP 的问题。
- 增加模型价格与容量刷新入口，更新草稿后显式保存，保留运行中冻结价格。
- 补齐 Task／Composite 质量合格后优先现金成本的轨迹说明。

## 0.30.1

- 金额迁移后清除旧目录价格，缺少参考价的型号逐项显示不可用原因，不残留 AFP。
- 设置中的换算价格按显示精度呈现，账本原始精度保持不变。

## 0.30.0

- 新增显式金额计价迁移：规划配置 v7、自动模型目录 v5，Python 核心 0.16.0。
- 保留 Ark 订阅模型与专属端点，以公开价格估算参考成本；按量现金费用另列，不相加。
- 订阅模型通过质量门槛后保留现金支出优先；旧 AFP 记录与原配置继续兼容读取。
- 设置提供现金及参考成本独立额度，迁移草稿补齐宿主价格后由保存操作生效。
- Seedream 订阅图片使用公开图片参考价，不占用现金额度，保留原有验收状态。

## 0.29.16

- 自动路由的 Jev／本地结构判别增加“单项实质工作”问题。三项 Noul 同时支持单项、
  顺序依赖、可独立拆分和无法确定；信号冲突时保持无法确定。
- 明确单项任务直接执行，保留宿主工具权限、工具结果核对与最终审核，省去 DAG planner。
  轨迹展示三项原始分数，并注明组合强度并非 Jev 原生 confidence。
- 判别合同升至 v2，核心同步升至 0.15.19；旧版运行证据继续按 v1 读取。

## 0.29.15

- 自动路由最终验收读取本任务宿主工具回执。明确要求工具但没有对应回执时停止交付，
  不再用答案正确或模型自述证明已执行，也不自动补跑工具。
- DSH 工具桥传递实际调用关联的结构化退出状态；摘要显示工具验收与停止原因。
- Python 核心同步升至 0.15.18；评审费用保护纳入完整工具证据输入，超容量不截断。

## 0.29.14

- 自动路由的任务摘要区分节点选路预计费用、模型调用预留上界和实际结算，
  单列最终评审的保护额度；不把保护额度误写成已消费费用。
- Python 核心同步升至 0.15.17。现有会话与模型配置不作迁移。

## 0.29.13

- 自动路由轨迹显示两条路线的合格执行模型数量，并说明模型画像先验
  不能证明拆分会改善当前任务质量。Python 核心同步升至 0.15.16。
- 更正有限验收报告中把高峰价保护额度当作实际结算费用的记录；
  原始调用账本、待核对预留及历史运行结果保持原样。

## 0.29.12

- 修正自动路由把「不要读取文件／不要调用工具」误判为强制工具任务的情况，
  避免由否定要求触发额外规划。Python 核心同步升至 0.15.15。

## 0.29.11

- 自动路由真实执行支持 `synthetic`、`desensitized` 和 `live` 数据模式；真实数据任务
  的规划、执行和评审只准入本地或已授权可信云模型，不改变原模型目录。
- 修正同一任务内的「它／它们」回指被误判为依赖旧会话而跳过 Jev 的问题。
- 完成 DSH 三条有限流程及一次截断后的独立复验；费用、失败与边界见
  `reports/automatic-live-20261005/`。Python 核心同步升至 0.15.14。

## 0.29.10

- 自动拆分规则 v3 不再用宿主上下文长度证明任务可拆；微型定义和封闭算术跳过规划与额外 Judge。
- Jev 两项 Noul 区分分支间依赖与最终汇总，排除不值得拆开的微型工作；矛盾答案保留为无法确定。
- 模型池 v3 的时延按真实执行规模分组，至少五个匹配样本使用 P90；缺样本保留先验，不放宽实际期限。
- 路由摘要显示具体拒绝约束、预测值、剩余额度与期限，以及时延样本依据。

## 0.29.9

- 加入 Kimi 官方 `moonshot/kimi-k3` 路线，共用人民币价格与独立质量先验。
- 按官方默认 5m 缓存合同结算，缓存写入与普通输入互斥，不重复收费。
- 自动及规划路由省略 K3 不可调整的温度参数，保留所选推理档位。

## 0.29.8

- 自动路由增加实际路线模型池 v3，共用规划路由的价格与容量资料。
- Ark（含 Kimi）使用 AFP，DeepSeek 官方使用 CNY；切换计费组需重新选择预算。
- 缺少质量证据的型号明确列为待补齐；DeepSeek 按高峰价预留、调用时段价结算。

# 0.29.7

- 自动路由拆分 Judge 新增 Jev，共用已有 OpenRouter／Typesafe 渠道与信任设置；保留本地后端。
- 独立设置单任务判别 CNY 上限；先做执行模型零调用预检，再签发一次两题 Noul 判别。
- Python 核心 0.15.10 记录判别原始答案、用量、现金结算、取消及未知用量预留。
- 任务摘要显示实际判别后端、渠道、时延、现金费用和最终路线；不把建议拆分等同于实际多节点执行。

# 0.29.6

- 自动路由将规划器返回的单节点执行归为 direct，并在路线比较中保留候选来源、
  实际节点数及是否形成多节点拆分；规划调用继续照实计费。
- DSH 任务摘要区分规划器单节点候选与真正多节点 DAG。Python 核心版本为 0.15.9。

# 0.29.5

- 规划路由设置现在可以独立选择正在编辑的策略，不会为了修改其他策略而改变默认路由。
- 零调用诊断明确表示“配置可执行”，与 Judge 判别质量分开；预算单位展示包含 Advisor
  独立执行模型与 LLM 审核模型。
- Python 核心 0.15.8 修正 Advisor LLM Judge 被宿主移除时仍显示可执行的诊断缺口。
- 补齐六策略产品状态、当前 DSH profile 的 Judge 组合及日常使用说明。

# 0.29.4

- Jev 设置明确显示 Advisor／Escalation 当前判定规则及分动作实验选项，说明
  probability、confidence、各动作固定门槛和受影响策略；默认规则保持原样。
- 路由轨迹从冻结记录显示实际规则、原始分类、有效门槛和最终动作；旧记录缺字段时
  标明未记录，避免把 Escalation 的获选项概率误称为泛化判别信号。

# 0.29.3

- Jev 设置新增 Typesafe 直连／OpenRouter 渠道与对应凭证引用；保留原有策略题目。
- OpenRouter 使用 Decisions API，校验实际版本、提供方和请求 ID；按回执 USD 实付费用折算 CNY，
  缺少费用或用量时保留预留并停止，关闭自动回退和 HTTP 重试。
- 核心 0.15.7 新增渠道能力握手；路由轨迹标注实际接入渠道。

# 0.29.2

- 完成 DSH 与官方 Jev 的五种规划策略有限真实接线验收；调用、AFP/CNY 费用与
  受控接管证据见 `reports/jev-dsh-live-acceptance-20261002/`。
- 修正 Jev 输入字节限制误判，压缩审核输入中的宿主 replay 包络；非 token
  调用在任务结算后继续计入单位账本。
- 路由轨迹容忍可选 Judge 数值为空，避免整个轨迹视图无法显示。
- Python 核心同步升至 0.15.6，插件升至 0.29.2，避免旧安装包缓存混用。

# 0.29.1

- 在规划路由零调用检查中核对核心 Jev、Stage 和 Composite 能力；插件与已安装核心
  不匹配时，先提示升级，再进行模型资料与策略校验。
- 官方 Jev 可在 Advisor、Escalation、Task、Stage 和 Composite 的设置中选择；
  原有 DSH web profile 的五条配置路径已完成零调用验收，真实 DSH 调用仍待独立验收。
- Python 核心同步升至 0.15.5，避免同版本旧 wheel 被安装缓存复用。

# 0.29.0

- Composite 升级为独立 v6 设置：Task 从有序模型池一次选出常用模型，Stage 再根据后续
  可信执行证据临时切换到用户指定的接管模型。
- 首次执行跳过重复的 Stage 判别；Task 已选择接管模型时跳过无意义切换，并在路由轨迹中
  记录初始选模、证据、保持、恢复与实际费用。
- 规则模式支持重复失败切换、两次执行保持和无新困难时恢复；互斥候选只预留实际选中模型。
- 新增实验性规则＋本地 Laya 模式，复用常驻本地 Judge job、容量检查与取消语义；当前权重
  质量仍未达到日常使用门槛，设置页明确保留实验标识。
- 标准 `refract/composite` 已通过 DSH、Codex、Hermes 的 Base URL 工具续接；动态切换使用
  版本化可信工具证据合同验收，Router 不执行宿主工具或建立 DAG。

# 0.26.0

- 规划路由协议升级为 `refractagent-planning/4`，增加能力握手和可取消的本地 Judge job。
- Escalation 使用独立 `escalation-decision-v1`：明确缺陷、最终停滞和无法判断立即接管，
  工具过程连续停滞达到门槛后接管；接管后锁定强模型且不再追加审核。
- 高效候选正文和工具调用在审核前全部缓冲；被丢弃的工具不会执行，强模型只看到原始请求、
  已接受历史和已完成工具结果。
- 配置升级为 v4 的独立 Escalation 模型、Judge、期限和输入／输出包络；设置页可分别配置
  推理等级、数据域和信任策略，并展示本地 Judge 的真实验收状态。
- 未升级时原子保护起始执行、一次 Judge 和可能的接管路径；AFP／CNY 分账，未知用量停止。
- 冻结 24 条中英混合 Judge 案例；`deepseek-v4-flash` 达到有限门槛，当前 Laya revision 与
  `glm-5.3-flash` 的 1024 token 路线保留为实验状态。

# 0.25.0

- Task 升级为有序多模型池；按实际工具与媒体能力筛选候选，并在单一候选时跳过 Judge。
- 新增版本化 `task-decision-v1` 合同，支持一次轻量 LLM Judge 与本地 Laya-MLX Judge。
- 本地权重必须显式下载并核对固定 revision；预热、容量拒绝、指定备援及本地推论指标可诊断。
- 规划路由 replay 升级到 v2，保留底层模型真实来源及原生图片内容块。
- 新增受管 Seedream 图片工具、DSH 附件持久化、非 token 预算与 unknown 不重发语义。
- 能力状态区分 `declared`、`connected` 与 `verified`；未通过真实付费验收的媒体路线不会派发。
- 明确记录 DSH 0.1.5-rc.1 缺少原生影片合同，影片输入、播放和持久化仍被宿主能力阻塞。
- Task Judge 合同升级为 `task-decision-v2`：逐候选评价，Python 先通过初始适合度门槛，再按同计费单位的首次执行调用上界选模；路由轨迹显示排除与排序依据。
- 一次 Ark 真实验收完成轻量 LLM Judge、两轮原生工具执行与 AFP 结算；此次调用实际 1.0728 AFP，不代表长期任务质量收益。

# 0.24.0

- 修正 Stage 默认保持 2 轮实际执行 3 次强模型的问题；已消费失败证据不会再次触发升级。
- 使用 DSH 结构化 turn、step、callId、错误来源与退出码归一证据，不从工具正文猜测成败。
- 从 DSH `tools/result` 规范值捕获 Bash／PowerShell 退出码、超时、中止和沙箱事实，弥补
  持久消息只保留渲染文本的问题。
- Stage 先选目标模型，再按真实输入与该模型输出上限原子预留；未选择模型不占用预算。
- 设置页增加 Stage 简洁说明、角色与推理等级摘要、同模型提示和单独高级参数。
- 路由轨迹展示规则版本、证据摘要、评分、保持前后状态、推理等级、首字等待和累计费用。
- 冻结 12 个任务、72 次三路线对照及独立研究盲评合同；默认运行器只做零调用预检。

# 0.23.0

- 新增独立规划路由入口与六类 Python 策略，保持 DSH 原生工具循环。
- 增加独立设置、零调用诊断、离线模拟和路由轨迹。会话模式在原生模型菜单中选择，
  详细参数沿用自动路由设置卡片样式。
- 引入版本化代理 replay、任务冻结、有界审核及完整生产调用记账。
- 保留自动路由、DAG 页签、历史入口及原实验协议。
- 宿主能力基线更新为 DSH 0.1.5-rc.1；需要 Python 核心 0.10.0。
- 子 Agent 共享预算属于后续 P6，本版不宣称全委派费用覆盖。

# 未发布

- 增加 `auto-live` 实验性模型入口：先由本机核心零调用预检，再显示复杂度路径、评审策略、
  外传路线、费用估算、双硬上限和最大调用数，只有 DSH `allowed-once` 才开始真实执行。
- 设置页增加真实执行开关、三档复杂度策略、两档评审策略及无默认值的生产／评审 USD 硬上限；
  非 `synthetic`、非 USD、缺少模型池或预算时逐项说明并阻止保存。
- 默认 `auto` 始终保持模拟；`auto-live` 不使用 Router URL、不传递宿主工具、不启用回退、动态
  拆分或并发。拒绝、取消及审批服务缺失均在解析凭证和模型派发前结束。
- 冻结 Artificial Analysis Intelligence Index v4.3.2 的公开综合质量分、排名和 0–100
  百分位先验；受支持路线不再因空质量档案被误判为不可运行。
- 修正 `deepseek-flash` 与 `deepseek-v4-flash` 的版本映射，并用 Ark 官方发布记录证明可复用
  质量先验的同名路线；无法确认等价的实验视觉路线继续 fail closed。
- 本地与团队 Router 持久保存正常调用产生的路线时延观测；按 provider、有效模型和推理档位
  隔离，使用最近 50 个成功样本的 p90，失败与取消不污染预测。
- 设置页通过零调用目录读取当前样本数、预测值和最后观测时间；没有样本时明确显示保守冷启动。
- 团队 HTTP v2 增加按成员项目权限读取路线观测的只读端点，项目间数据不混用。
- DSH 模型池升级到 v2，只允许用户覆盖价格与说明；旧 v1 的手工质量和时延值不会成为运行
  证据，须通过设置页显式迁移。
- 质量改为带来源、许可和归一化信息的独立第三方冻结先验；时延改为核心保守冷启动与后续
  路线观测，不再要求用户填写。
- 设置卡片折叠时也显示“无法保存”“不可运行”或“时延冷启动”，展开后醒目解释缺失路线、
  数据来源和保存不可运行草稿的行为。
- 配置存在安全或职责引用阻断问题时，保存按钮直接禁用并改为“无法保存”，操作区逐条展示
  具体原因，同时保留“放弃修改”以恢复已保存配置。
- DSH 模型目录直接展示随核心冻结的公开价格、条件档位与来源；Ark 路线明确区分原厂参考价和
  AFP 实际结算，手工覆盖可逐路线恢复。
- 设置页持续解释规划、执行、评审和分类职责，并把自动分配规则、数据模式、部署属性及信任
  策略说明收在渐进式高级区域。
- 保存前以可定位错误阻止无部署属性、无效信任策略、未确认真实外传和失效职责引用；质量或
  时延不完整仍可保存草稿，但明确标记为不可运行。
- 区分宿主明确拒绝与写入后未确认回读，失败时保留用户草稿，不再统一显示模糊拒绝信息。

# 0.22.0

- 接入 `refractagent-http-v2` 持久任务：提交后保存任务 ID 和幂等键，事件流断开时从最后
  序号继续读取，不会重复提交或重复展示节点与答案。
- DSH 取消信号会请求服务端取消；终态立即结束思考块，并保留失败、取消和重启待核对语义。
- 设置页通过宿主侧凭证代理读取成员可用项目，只能从 `/v2/projects` 返回值选择项目 ID；
  页面不接触 token，也不能自由填写项目。
- 提交前确认服务仅支持 v1 时继续使用同步兼容路径；v2 任务一旦提交，故障时不会改走本地
  Python 或新建第二个任务。

# 0.21.0

- 新增本地核心／远程 Router URL 连接选择；远程模式不再启动本机 Python 子进程。
- Router 凭证只保存 DSH 引用，非回环地址强制 HTTPS，拒绝 URL 内嵌凭证与查询参数。
- 接入 `refractagent-http-v1` NDJSON 进度和结果协议；连接、认证与协议失败继续使用原生终止事件。
- 当前 HTTP v1 只允许预检和模拟，不开放 v4 付费执行或 DSH 宿主工具回调。

# 0.20.0

- 普通设置改为从 DSH 当前模型目录勾选 `provider/model` 路线，不再要求手填 Provider、URL、
  模型 ID 或密钥，并排除 `refractagent` 自身以防递归。
- 每条路线保存明确部署属性；可信云关联信任策略。执行前重新解析目录，已删除、失效或容量
  不完整的路线会在启动 Python 前终止。
- Python 核心根据冻结公开档案和用户覆盖自动分配规划、执行、评审与分类职责；高级设置可覆盖
  四类职责及价格、质量、时延和说明，并可恢复公开档案。
- 新增逐路线 `model_profile_provenance` 证据。没有公开档案的路线只有在完整手工声明后才能使用，
  并标记为“用户声明、未经项目校准”。
- 旧 `providerConfig` 保留用于 CLI、历史配置和迁移回退；本阶段仍只开放 v4 模拟与预检。

# 0.19.2

- 自动预览按真实序列化会话、工具描述和父节点预留量重新编译节点输入容量，长会话不再受
  通用模板容量限制。
- 自动流程失败后立即结束思考块并发送 DSH 原生错误或取消终止事件，不再留下持续运行状态，
  也不会生成伪成功答案。
- 将 `relaxBudget` 的界面文案改为“放开费用上限”，明确它不改变上下文和模型容量限制。

# 0.19.1

- v4 设置卡片默认改为简洁视图，只展示自动路由状态、最低质量和数据类型。
- Provider、角色、信任策略、模型预测、限制开关与高级 JSON 收入可逆的高级部署设置。
- 不改变 v4 配置合同、核心安全判定、路由策略、预算或旧版配置界面。

# 0.19.0

- 为 v4 自动路由配置增加 DSH 原生风格的结构化设置界面，替代仅适用于 v1–v3 的三模式区域。
- 支持编辑路由目标、安全模式、分类器、信任策略、Provider、模型角色、价格与质量／时延预测。
- 增加只展示角色与部署清单事实的结构可行性预览；最终安全和路线合法性仍由 Python 核心校验。
- 升级到 v4 后若 DSH 新会话仍保留旧三模式模型 ID，适配层会将其收敛到唯一 `auto` 入口。
- 模拟模式不再探测仅供真实执行使用的 DSH Provider，示例配置无需安装占位 Provider 即可运行。
- v4 自动路由始终开启结构化进度流，使「任务 DAG」页签在模拟与后续真实运行中收到拓扑。
- 「任务 DAG」改用 DSH Chat 标准会话投影，修复核心已记录进度但独立页签为空的问题。
- 保留高级 JSON、限制开关、旧版配置界面、任务 DAG 页签及动态拓扑行为。

# 0.18.0

- 增加 v4 自动路由设置合同，支持路由目标、安全模式以及 Provider、模型、信任策略的
  结构化增删改和整组回滚。
- 高级 JSON 与结构化草稿共用同一配置对象，保留未被表单修改的合法嵌套字段。
- 浏览器侧只接受凭证环境变量引用，拒绝把 API Key、token 或 secret 写入 Provider 行。
- 配合 Python 核心的 `validate-config` 零调用入口执行最终业务校验；TypeScript 不复制
  安全准入、候选筛选和 direct/DAG 判定。

# 0.17.2

- 新增「不限总时间」设置，接通核心调度与宿主进程期限，保留取消和独立预算。
- 停止写入 DSH 无法重载的自定义工具日志；工具证据保存在核心执行记录。提供保留原始备份与独立 header 压缩帧的旧日志迁移脚本。

# 0.17.1

- 将节点内部工具记录改为插件专用会话事件，修复缺失 surfaceOp 导致工具结果无法回传的问题。
- 安装验收使用真实 DSH Session，覆盖成功、审批拒绝与执行异常，并检查外层模型历史不混入内部工具消息。

# 变更日志

## 0.17.0

- 配合核心 0.6.0，在原有 DAG 节点中接入 DSH 原生工具执行、审批与轨迹。
- 支持 Chat Completions、Responses 及 DSH 模型桥的结构化工具调用与续调。
- 技能附加上下文回传到同一节点，工具轮次逐次记账，副作用节点禁止自动重跑。
- 保留 DAG 与设置共同注册，不改变现有预算、输出容量、思考或模型默认配置。

## 0.16.0

- 恢复与「对话」「轨迹」并列的「任务 DAG」独立页签，包含节点、依赖连线及实时状态。
- 将原图形贡献与新设置卡片合并到同一个客户端入口，增加同时注册的回归测试。
- 恢复节点类型、难度、风险展示；保留历史文字进度回放。

## 0.15.0

- 增加规划器思考方式设置：继承模型设置、开启或关闭。
- 配合核心 0.5.0，自动紧凑规划使用完整模型输出容量，取消规划超时与父进程定时中止。
- 保留手动取消与预算记账，规划等待不消耗节点执行时间。

## 0.14.3

- 增加 Ark 各模型 thinking:auto 的逐项诊断状态，设置页区分接口接受、不支持与未确认。
- 核心 0.4.3 在调用前拒绝已核验不接受 auto 的 Ark 型号；通用 provider 不套用该限制。

## 0.14.2

- 修复 Ark 预设统一发送 `thinking.type: auto` 导致豆包规划模型返回 HTTP 400；除已知强制思考模型外，使用供应商默认行为。
- 配合核心 0.4.2，在模型失败时显示安全的失败类型和 HTTP 状态，保留未知用量预留。

## 0.14.1

- 将省成本、均衡、质量优先分为独立区块，增加标题分隔线、内边距和区块间距。

## 0.14.0

- 引入 2026-09-12 核对的完整 Ark 文字模型清单，替换 DSH 设置预设中的三个实验候选。
- 新增六档 AFP 成本上限，与推理强度分离；Python 实际过滤候选并校验空集。
- 显示模型官方输入／输出系数和套餐范围，保留 GLM-5.3 的思考约束。
- 需要 Python 核心 0.4.1；历史实验 manifest 和报告保持不变。


## 0.13.2

- 将模式下的内部模型 ID 文本输入改为真实模型名称勾选列表。
- 解释三种模式的选择偏好，以及勾选限制范围、不勾选使用全部候选模型的含义。
- 排除评审模型，区分同名模型并提示已移除的配置引用。


## 0.13.1

- 对齐官方插件卡片的标题、说明、折叠箭头、主题色与保存按钮。
- 将 Ark 预设展开为可编辑配置，保留凭证引用；未编辑时仍使用原预设。
- 修复未完成 JSON 被宿主刷新覆盖、无法放弃及多行模型输入换行丢失。
- 为推理强度、候选模型和完整 JSON 提供示例与明确标签。


## 0.13.0

- 新增 DSH 浏览器半边，在「设置 → 插件 → 插件配置」显示「RefractAgent 路由」卡片。
- 通过 `refractagent` settings namespace 编辑 provider/model 配置、全局与三模式
  reasoning effort、三模式候选模型池，以及预算和上下文限制开关。
- 设置使用 DSH 用户层持久化并热加载；保存失败保留草稿，重置清除用户覆盖并恢复部署值。
- 浏览器 bundle 按 DSH lazy-CJS factory 格式构建，发布包继续保持零运行时 npm 依赖。

## 0.12.0

- `providerConfig` 新增 `defaultReasoningEffort` 与 `strategies`，支持按省成本／均衡／
  质量优先三种模式配置默认推理档位与候选模型池；模型显式档位优先于模式与全局默认。
- 插件配置新增 `limits` 开关：`relaxBudget` 放开预算拦截但保留逐次记账，
  `relaxContext` 将对话上下文上限放宽到 1000000 字节并同步放宽节点输入预算定尺上限。
- 运行记录与结果保存 `limits` 实际状态；配合 Python 核心 0.4.0。
- 增加显式可选的 `outputConstraints` 透传，无默认字数限制。
- Python 核心检查最终正文长度；DSH 分别展示生成、语义评审和长度检查状态并保存回放。
- 原始答案、评审与用量保留；超限不自动截断、修复或换模型。

## 0.11.0

- 增加 OpenAI Responses 协议、推理参数和独立用量明细，正确结算无正文截断响应。

- 支持用户配置 providers 与 models，Ark Agent Plan 改为显式可选预设。
- 复用 DSH 原生 provider 和凭证，或按 provider 解析直接 HTTP 凭证。
- Python 统一编译配置、校验计费单位与选模；结果保留 provider 和实际模型。
- 真实模式迁移需添加 `providerConfig` 或 `preset: "ark-agent-plan"`，配合核心 0.3.0。

## 0.10.0

- 新增 `refractagent` 原生模型提供方，提供省成本、均衡与质量优先三个文本任务接口。
- 模型接口通过已安装的 Python 核心运行，默认演示，保留 DSH 凭证、沙箱与进程边界。
- 原验证和文本任务工具保留；路由、评分及记账继续由 Python 管理。

## 0.7.0

- 新增 `refractrouter_task` 与 `taskProfilePath`，由 Python 完成文本 DAG 规划、A/B 选模、执行和独立评审。
- 合并既有基准候选策略时按 runner 职责区分参数，避免将基准选模选项传入文本任务。

- 文本任务新增有界并发、provider 并发上限及启动间隔参数；默认串行。
- 结果增加执行模式、最大并发、观测峰值和预测时延，Python 负责调度与原子预算。
- A/B 使用完整 DAG 调度时延；B 不再奖励对总耗时没有贡献的分支加速。
- 支持分层 profile 与固定校准/测试协议，提供零调用预检及完整模拟对照。
- 取消或失败后停止新派发并结算在途调用；真实组合收益仍待完整对照验证。

## 0.6.0

- 新增 `acceptanceCriteria`，原样转交 Python 核心并冻结规划验收条件。
- 模型规划采用 `text-task-plan-v2`，明确依赖字段与理由、节点契约、能力需求和验收覆盖。
  旧版显式计划仍可使用并标注缺少交接契约，模型生成计划不得降级。
- 零调用预览改为单节点，避免把固定模板当成任务拆分；提供并行机会、依赖深度及汇总
  诊断产物。运行时仍串行，质量 profile 仍是迁移预测。
- 核心校验结构化交接输出，失败时保存原文与费用并阻止后续执行；插件只负责接入。

## 0.9.0

- 新增 `stage: "resume"`，复用已验证的 K3 基线，只执行参考路线与节点探针，最多 28 次。
- Python 验证阶段、任务、模型、硬契约、费用和代码兼容记录；不改写历史产物。
- 本阶段新增费用与已有 K3 费用分开留证；未知用量不计为零。
- 增加真实历史基线的原生零调用恢复验证，默认仍关闭付费执行。

## 0.8.0

- 新增 `stage: "baseline"`，只执行一次 K3 整任务调用，成功或失败均不进入参考路线及探针。
- Python 将该单次阶段的等待上限设为 300 秒，保留 8192 token 输出上限和零自动重试。
- 增加原生子进程单次预检与成功／失败停止回归；其他阶段仍使用原有 120 秒时限。

## 0.7.0

- 新增 `k3-baseline` 类型化阶段及独立评审交接路径，支持准备、组合两个原生调用阶段。
- 保持默认零调用、单轮零重试、Agent Plan 专用端点与部署额度限制。
- 本阶段允许内部评审额度为零；外部评审费用另计，未知费用不按零处理。
- 新增原生工具到 Python 的零调用验证；成本选模、评审校准、材料冻结和核算由 Python 负责。

## 0.6.0

- Add the typed `execution-modes` phase for Python's explicit v0.4 A/B/C report comparison.
- Default that phase to v2 selection, require zero retries and at most three repeats, and retain
  disabled paid runs, exact Agent Plan endpoint and both deployment ceilings.
- Validate a real zero-call subprocess preflight through the registered tool. Evidence ownership,
  experimental comparisons, accounting and judging remain in Python.

## 0.5.0

- 新增有类型的 `selectionPolicy`，经 DSH 基准 runner 原样传给 Python。
- 保留 v1 默认行为，支持显式 v2 排除已知契约拒绝；未知失败继续阻断。
- 选模语义与配对样本规则留在 Python，并补充参数契约回归。

## 0.4.1

- Migrate plugin and service contracts to strict TypeScript, with explicit host/config/tool/result
  types and validated Python evidence projection. Malformed evidence fields fail closed.
- Build the ESM entry and declarations into `dist/`; pack only the runtime distribution, with no
  runtime dependencies. Retain endpoint, credential, budget and replay safeguards.

## 0.4.0

- Add `contract-replay` for the seven frozen issue #25 writer failures. Default to preflight,
  limit repeats to three, prohibit retries, stop after the first failure, and retain all existing
  Agent Plan credential and budget controls. Replay results establish contract validity only.

## 0.3.0

- Send AFP benchmark calls directly to the Agent Plan OpenAI-compatible Chat Completions endpoint,
  avoiding the DSH stdio bridge that could stall before dispatch.
- Reject AFP manifests unless every model uses provider `ark-plan` and the exact
  `https://ark.cn-beijing.volces.com/api/plan/v3` base URL, preventing fallback to ordinary Ark
  pay-as-you-go billing.
- Resolve the Agent Plan key through DSH credentials only for a paid operation, inject it into the
  scrubbed child environment, and persist prompt-free `model-progress.ndjson` request evidence.

## 0.2.2

- Enforce per-request timeouts locally while consuming DSH streams, including providers that ignore
  the supplied abort signal.
- Persist prompt-free request start and finish records so long paid runs expose their current model
  and completed-call progress.

## 0.2.1

- Reject DSH model routes whose provider-owned retry policy is not normal mode with zero retries.
- Carry the runner's per-model timeout across the stdio bridge and abort stalled DSH streams.

## 0.2.0

- Add an AFP-billed Volcengine Agent Plan manifest and generic billing-unit budgets.
- Route Agent Plan calls through the hosting DSH `llm` service over a bounded stdio bridge, so the
  provider credential remains owned by DSH and is never copied into the Python child.
- Validate the frozen provider/model routes before a paid run and expose the billing unit in
  structured preflight and evidence results.
- Reject paid ceilings below the conservative preflight estimate, reserve an estimated call before
  each invocation, and default DSH runner retries to zero.

## 0.1.1

- Bound evidence and standard-stream capture, fail on truncation, and redact resolved credentials
  from returned diagnostics.
- Declare and test the v0.1 DSH, Node, and pnpm compatibility contract.
- Add clean-profile installation lifecycle validation and release, troubleshooting, upgrade, and
  rollback documentation.

## 0.1.0

- Add the `refractrouter_validate` Cordis tool with preflight-safe defaults and two-level paid-run
  budget enforcement.
- Use DSH subprocess, sandbox, policy, and credential services while keeping benchmark logic in the
  Python runner.
## 0.32.0

- 在「路由轨迹」页同时展示自动路由与规划路由，保留任务 DAG 及两张设置卡片。
- 展示 Judge 原始答案、最终路线、全部冻结候选、逐模型预算检查及实际调用证据。
- 区分订阅参考估值、按量费用计算、待核对预留、历史预算和独立 Jev 费用。
- 明确模型评审结论与质量门槛、工具回执与任务成功、中断与缺失证据的区别。
- 对应 Python 核心 0.16.6；不改变用户预算、模型、凭据、信任或默认策略。
