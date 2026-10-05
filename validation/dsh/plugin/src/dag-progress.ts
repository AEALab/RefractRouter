/** 仅校验和展示 Python 核心进度，不推导路由或执行状态。 */
export const PROGRESS_PROTOCOL = 'refractagent-progress/v1'
interface NodeView {
  node_type?: string | null; difficulty?: string | null; risk?: string | null
  id: string; objective: string; parents: string[]; state: string; attempt: number
  model: { id: string; provider: string; model: string; reasoning_effort?: string | null } | null
  recovery: string | null
}
export interface DagView {
  phase: string; status: string; simulated: boolean; reason: string; nodes: NodeView[]
}
export interface ProgressEvent extends DagView { protocol: string; run_id: string; sequence: number; elapsed_ms: number }
function object(v: unknown): v is Record<string, unknown> { return v !== null && typeof v === 'object' && !Array.isArray(v) }
function short(v: unknown, max = 400): v is string { return typeof v === 'string' && v.length <= max }
export function decodeDag(value: unknown): DagView {
  if (!object(value) || !short(value.phase, 40) || !short(value.status, 80) || !short(value.reason, 400)
    || typeof value.simulated !== 'boolean' || !Array.isArray(value.nodes) || value.nodes.length > 12) throw new Error('invalid DAG progress')
  const ids = new Set<string>()
  for (const row of value.nodes) {
    if (!object(row) || !short(row.id, 100) || !row.id || ids.has(row.id) || !short(row.objective, 240)
      || !short(row.state, 80) || !Number.isSafeInteger(row.attempt) || Number(row.attempt) < 0
      || !Array.isArray(row.parents) || row.parents.length > 12 || !row.parents.every(p => short(p, 100))
      || !(row.recovery === null || short(row.recovery, 100))) throw new Error('invalid DAG node progress')
    for (const key of ['node_type', 'difficulty', 'risk']) {
      if (row[key] != null && !short(row[key], 40)) throw new Error('invalid DAG classification')
    }
    ids.add(row.id)
    if (row.model !== null && (!object(row.model) || !short(row.model.id, 100)
      || !short(row.model.provider, 100) || !short(row.model.model, 200)
      || !(row.model.reasoning_effort == null || short(row.model.reasoning_effort, 40)))) throw new Error('invalid DAG model progress')
  }
  if (value.nodes.some(row => (row as NodeView).parents.some(parent => !ids.has(parent)))) throw new Error('unknown DAG progress dependency')
  return value as unknown as DagView
}
export function decodeProgress(value: unknown): ProgressEvent {
  decodeDag(value)
  if (!object(value) || value.protocol !== PROGRESS_PROTOCOL || !short(value.run_id, 100)
    || !Number.isSafeInteger(value.sequence) || Number(value.sequence) <= 0
    || typeof value.elapsed_ms !== 'number' || !Number.isFinite(value.elapsed_ms) || value.elapsed_ms < 0) throw new Error('invalid DAG progress envelope')
  return value as unknown as ProgressEvent
}
const states: Record<string,string> = { pending: '等待依赖／选模', scheduled: '排队', running: '运行中', ok: '已完成',
  skipped: '按策略跳过', 'tool-concluded': '工具已结束本轮', failed: '失败', 'invalid-output': '输出校验失败', 'cancelled-before-dispatch': '已取消', blocked: '未执行（任务停止）', 'not-run': '未执行（预览）' }
const phases: Record<string,string> = { classifying: '数据分级与部署准入', planning: '规划任务', routing: '计划就绪／模型分配', executing: '执行节点', evaluating: '独立评审', finished: '执行结束' }
function escape(value: string): string {
  // DSH 0.1 的 reasoning 区域使用纯文本；保留易读文字并去掉控制字符。
  return value.replace(/[\x00-\x1f\x7f\u202a-\u202e\u2066-\u2069]/g, ' ').replace(/</g, '‹').replace(/>/g, '›')
}
function model(row: NodeView): string {
  if (row.node_type === 'role-classifier' || row.node_type === 'role-placement') return '规则／分类器与部署策略检查'
  return row.model ? escape(`${row.model.provider}/${row.model.model}${row.model.reasoning_effort ? ' (' + row.model.reasoning_effort + ')' : ''}`) : '待分配'
}
function state(row: NodeView): string {
  const label = row.node_type === 'role-classifier' || row.node_type === 'role-placement'
    ? row.state === 'blocked' ? '准入阻断' : states[row.state] ?? row.state
    : states[row.state] ?? row.state
  return escape(label) + (row.attempt > 1 ? `（第 ${row.attempt} 次）` : '')
    + (row.recovery ? ` · ${escape(row.recovery)}` : '')
}
export function dagListing(view: DagView): string {
  if (!view.nodes.length) return ''
  return '\n【节点清单】\n' + view.nodes.map(row => `${escape(row.id)} · ${escape(row.objective)}\n  类型：${escape(row.node_type ?? '未提供')}；难度：${escape(row.difficulty ?? '未提供')}；风险：${escape(row.risk ?? '未提供')}\n  依赖：${row.parents.map(escape).join('、') || '无'}\n  模型：${model(row)}\n  状态：${state(row)}`).join('\n\n') + '\n'
}
export function progressText(event: ProgressEvent, previous?: ProgressEvent): string {
  const topology = (v: DagView) => JSON.stringify(v.nodes.map(n => [n.id,n.parents,n.objective]))
  let text = previous?.phase === event.phase ? '' : `\n【${phases[event.phase] ?? escape(event.phase)}】${event.simulated ? '（模拟）' : ''}\n`
  if (!previous || topology(event) !== topology(previous) || event.phase === 'finished') {
    if (event.reason && event.reason !== previous?.reason) text += `拆分理由：${escape(event.reason)}\n`
    return text + dagListing(event)
  }
  for (const row of event.nodes) {
    const prior = previous.nodes.find(n => n.id === row.id)
    if (JSON.stringify(row) !== JSON.stringify(prior)) text += `\n- ${escape(row.id)}：${state(row)}；模型 ${model(row)}；依赖 ${row.parents.map(escape).join('、') || '无'}\n`
  }
  return text
}

export function runSummary(result: Record<string, unknown>): string {
  const quality = object(result.quality) ? result.quality : {}
  const costs = object(result.costs) ? result.costs : {}
  const breakdown = object(result.cost_breakdown) ? result.cost_breakdown : {}
  const number = (value: unknown) => typeof value === 'number' && Number.isFinite(value) ? value.toFixed(4) : '未提供'
  const mixed=result.billing_unit==='MIXED'
  const vector=(value:unknown)=>{const row=object(value)?value:{}
    return `AFP ${number(row.AFP)}、CNY ${number(row.CNY)}`}
  const byUnit=object(costs.by_unit)?costs.by_unit:{}
  const allIn=object(costs.all_in_known_by_unit)?costs.all_in_known_by_unit:null
  const externalJudge=object(costs.out_of_band_judge)?costs.out_of_band_judge:null
  const mixedCosts=['AFP','CNY'].map(unit=>{const row=object(byUnit[unit])?byUnit[unit]:{}
    return `${unit}：生产 ${number(row.production)}、评审 ${number(row.evaluation)}、待核对 ${number(row.unconfirmed)}`}).join('；')
  const gate=object(result.complexity_gate)?result.complexity_gate:{}
  const local=object(gate.local_decision)?gate.local_decision:{}
  const combinations:Record<string,string>={'coupled-sequential-work':'顺序依赖工作保持单路线执行；工具与审核要求仍保留','trivial-workload-no-planner':'微型任务直接执行，跳过判别与规划','local-separable':'独立实质工作进入规划，之后仍须比较准入与费用','rules-only':'仅依据结构规则','local-unknown-rules-preserved':'判别无法确定，保留规则结论'}
  const route=Object.keys(gate).length?`选路：规则 ${String(gate.rule_decision??gate.decision)} → 最终 ${String(gate.decision)}；合并方式 ${combinations[String(gate.combination)]??String(gate.combination??'旧规则')}；理由 ${Array.isArray(gate.reasons)?gate.reasons.join('、'):'未提供'}\n`:''
  const signals=object(local.signals)?local.signals:{}
  const reasonNames:Record<string,string>={'context-dependent':'任务依赖未传入的历史内容',
    'trivial-workload':'微型任务无需额外判别或规划','input-too-long':'任务超出本地输入上限','token-capacity':'本地 tokenizer 容量不足'}
  const localLine=Object.keys(local).length?`${local.model==null?'结构规则（未调用 Judge）':local.backend==='jev'?'云端 Jev 结构判别':'本地结构判别'}：${String(local.verdict)}（原始 ${String(local.rawVerdict)}，判别分数 ${number(local.confidence)}）；`
    +`依赖前一步 ${number(signals.requires_previous_output)}，可独立开始 ${number(signals.can_start_independently)}；`
    +`模型 ${String(local.model??'未调用')}；推论 ${number(local.latencyMs)} ms，排队 ${number(local.queueMs)} ms；`
    +`${local.backend==='jev'?`渠道 ${String(local.provider)}；本次判别 ${number(local.costCny)} CNY（独立于执行费用）；`:''}`
    +`${local.reason?`回退原因 ${reasonNames[String(local.reason)]??String(local.reason)}；`:''}实验能力\n`:''
  const comparison=object(result.route_comparison)?result.route_comparison:{}
  const generatedLabel=comparison.generated_node_count===1?'规划器单节点候选':'DAG'
  const selectedLabel=comparison.selected_candidate==='generated-plan' && comparison.generated_node_count===1
    ?'direct（规划器单节点）':String(comparison.route)
  const selectedShape=Number.isSafeInteger(comparison.selected_node_count)
    ?`选中计划 ${String(comparison.selected_node_count)} 个节点；${comparison.multi_node_selected===true?'多节点拆分':'未形成多节点拆分'}；`
    :''
  const factors=object(comparison.decision_factors)?comparison.decision_factors:{}
  const qualityLine=Object.keys(factors).length
    ?`质量依据：模型画像先验，尚无本任务拆分质量增益的验证；两路线合格执行模型共 ${String(factors.qualified_execution_model_count??'未提供')} 款；`
      +`${typeof factors.dag_extra_worker_cost==='number'?`DAG 预计执行费用相差 ${number(factors.dag_extra_worker_cost)} ${String(result.billing_unit)}；`:''}\n`
    :''
  const comparisonLine=Object.keys(comparison).length
    ? `执行前比较：${String(comparison.status)}；选中 ${selectedLabel}；依据 ${String(comparison.reason)}；`
      + selectedShape
      + (mixed?`direct 预计 ${object(comparison.direct)?vector(comparison.direct.total_estimated_by_unit):'不可行'}，`
        +`${generatedLabel} 预计 ${object(comparison.dag)?vector(comparison.dag.total_estimated_by_unit):'不可行'}；质量依据：模型画像先验，未经本任务等质验证\n`
        :`direct 预计 ${object(comparison.direct)?number(comparison.direct.total_estimated_cost):'不可行'}，`
        +`${generatedLabel} 预计 ${object(comparison.dag)?number(comparison.dag.total_estimated_cost):'不可行'} ${String(result.billing_unit)}\n`)
      + qualityLine
    : ''
  const diagnostics=object(comparison.candidate_diagnostics)?comparison.candidate_diagnostics:{}
  const diagnosticLines=Object.entries(diagnostics).filter(([,v])=>object(v)).map(([name,value])=>{
    const d=value as Record<string,unknown>
    const rejected=object(d.rejected_combinations)?d.rejected_combinations:{}
    const labels:Record<string,string>={quality:'质量',cost:'费用',latency:'预计时延','assignment-mode':'分配模式'}
    const reasons=Object.entries(rejected).filter(([,v])=>typeof v==='number'&&v>0)
      .map(([k,v])=>`${labels[k]??k}不满足 ${String(v)} 种分配`).join('、')
    return `${name} 准入：${reasons||'没有记录约束拒绝'}；预计最短 ${number(d.minimum_scheduled_latency_ms)} ms，剩余期限 ${number(d.remaining_latency_ms)} ms；最低预计费用 ${number(d.minimum_cost)}，剩余额度 ${number(d.remaining_cost)}；无候选节点 ${Array.isArray(d.empty_candidate_nodes)?d.empty_candidate_nodes.map(escape).join('、')||'无':'未提供'}\n`
  }).join('')
  const latencyEvidence=object(comparison.latency_evidence)?comparison.latency_evidence:{}
  const latencyLines=Object.entries(latencyEvidence).flatMap(([route,nodes])=>object(nodes)?Object.entries(nodes).flatMap(([node,models])=>object(models)?Object.entries(models).map(([id,raw])=>{
    const e=object(raw)?raw:{}
    return `${route}/${escape(node)} ${escape(id)}：时延依据 ${String(e.source)}，匹配样本 ${String(e.samples??0)}，输入分组上界 ${String(e.input_bucket_max??'未提供')}，输出分组上界 ${String(e.output_bucket_max??'未提供')}（非 SLA 保证）\n`
  }):[]):[]).join('')
  const trace=object(result.cost_trace)?result.cost_trace:{}
  const selected=Array.isArray(trace.selected_nodes)?trace.selected_nodes:[]
  const callRows=Array.isArray(trace.calls)?trace.calls:[]
  const expectedLines=selected.filter(object).map(row=>
    `${escape(String(row.node_id))} → ${escape(String(row.model_id))}：预计 ${number(row.expected_cost)} ${escape(String(row.unit))}；`
    +`输入预计 ${String(row.expected_input_tokens)} tokens（保守上界 ${String(row.conservative_input_bound??'未提供')}），`
    +`输出预计 ${String(row.expected_output_tokens)} tokens；依据 ${escape(String(row.input_source??'未提供'))} / ${escape(String(row.output_source??'未提供'))}\n`).join('')
  const actualLines=callRows.filter(object).map(row=>
    `${escape(String(row.label))} · ${escape(String(row.model_id))}：预留上界 ${number(row.reserved)} ${escape(String(row.unit))}，`
    +`${row.status==='billed'?'实际结算':row.status==='unknown-usage'?'待核对预留':row.status==='cancelled-before-dispatch'?'已释放':'当前占用'} ${number(row.charged)} ${escape(String(row.unit))}，状态 ${escape(String(row.status))}\n`).join('')
  const protection=object(trace.review_protection)?trace.review_protection:null
  const protectionLine=protection?`最终评审保护额度：${number(protection.amount)} ${escape(String(protection.unit))}，`
    +`${String(protection.output_tokens)} 输出 tokens，状态 ${escape(String(protection.status))}；此额度不是已结算费用\n`:''
  const costTraceLine=Object.keys(trace).length?`费用依据：预计值用于选路；预留上界用于准入；实际结算以调用账本为准。\n`
    +expectedLines+protectionLine+actualLines:''
  return `\n【任务摘要】\n策略：${String(result.strategy_name)}；整体状态：${String(result.status)}\n`
    + route + localLine + comparisonLine + diagnosticLines + latencyLines + costTraceLine
    + `生成：${String(result.generation_status ?? '未提供')}；语义评审：${quality.passed === true ? '通过' : quality.passed === false ? '未通过' : '未提供'}，得分 ${String(quality.score ?? '未提供')}\n`
    + (mixed?`费用分账：${mixedCosts}\n`
      +(allIn?`已知合计（含外部拆分 Judge）：AFP ${number(allIn.AFP)}、CNY ${number(allIn.CNY)}；${externalJudge?`外部判别调用 ${String(externalJudge.call_id??'未提供')}，CNY ${number(externalJudge.cost)}`:''}\n`:'')
      +`规划 ${vector(breakdown.planning)}，动态规划 ${vector(breakdown.dynamic_planning)}，节点执行 ${vector(breakdown.execution)}，评审 ${vector(breakdown.evaluation)}\n`
      :`费用（${String(result.billing_unit)}）：规划 ${number(breakdown.planning)}，动态规划 ${number(breakdown.dynamic_planning)}，节点执行 ${number(breakdown.execution)}，评审 ${number(costs.evaluation)}，未确认预留 ${number(costs.unconfirmed)}\n`)
    + `耗时：${typeof result.wall_time_ms === 'number' ? (result.wall_time_ms / 1000).toFixed(2) + ' 秒' : '未提供'}\n`
    + `记录：${String(result.result_path)}\n`
}
