/** 仅校验和展示 Python 核心进度，不推导路由或执行状态。 */
export const PROGRESS_PROTOCOL = 'refractagent-progress/v1'
interface NodeView {
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
    || typeof value.simulated !== 'boolean' || !Array.isArray(value.nodes) || value.nodes.length > 8) throw new Error('invalid DAG progress')
  const ids = new Set<string>()
  for (const row of value.nodes) {
    if (!object(row) || !short(row.id, 100) || !row.id || ids.has(row.id) || !short(row.objective, 240)
      || !short(row.state, 80) || !Number.isSafeInteger(row.attempt) || Number(row.attempt) < 0
      || !Array.isArray(row.parents) || row.parents.length > 8 || !row.parents.every(p => short(p, 100))
      || !(row.recovery === null || short(row.recovery, 100))) throw new Error('invalid DAG node progress')
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
  failed: '失败', 'invalid-output': '输出校验失败', 'cancelled-before-dispatch': '已取消', blocked: '未执行（任务停止）', 'not-run': '未执行（预览）' }
const phases: Record<string,string> = { planning: '规划任务', routing: '计划就绪／模型分配', executing: '执行节点', evaluating: '独立评审', finished: '执行结束' }
function escape(value: string): string {
  // DSH 0.1 的 reasoning 区域使用纯文本；保留易读文字并去掉控制字符。
  return value.replace(/[\x00-\x1f\x7f\u202a-\u202e\u2066-\u2069]/g, ' ').replace(/</g, '‹').replace(/>/g, '›')
}
function model(row: NodeView): string {
  return row.model ? escape(`${row.model.provider}/${row.model.model}${row.model.reasoning_effort ? ' (' + row.model.reasoning_effort + ')' : ''}`) : '待分配'
}
function state(row: NodeView): string {
  return escape(states[row.state] ?? row.state) + (row.attempt > 1 ? `（第 ${row.attempt} 次）` : '')
    + (row.recovery ? ` · ${escape(row.recovery)}` : '')
}
export function dagListing(view: DagView): string {
  if (!view.nodes.length) return ''
  return '\n' + view.nodes.map(row => `${escape(row.id)} · ${escape(row.objective)}\n  依赖：${row.parents.map(escape).join('、') || '无'}\n  模型：${model(row)}\n  状态：${state(row)}`).join('\n\n') + '\n'
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
  return `\n【任务摘要】\n策略：${String(result.strategy_name)}；整体状态：${String(result.status)}\n`
    + `生成：${String(result.generation_status ?? '未提供')}；语义评审：${quality.passed === true ? '通过' : quality.passed === false ? '未通过' : '未提供'}，得分 ${String(quality.score ?? '未提供')}\n`
    + `费用（${String(result.billing_unit)}）：规划 ${number(breakdown.planning)}，动态规划 ${number(breakdown.dynamic_planning)}，节点执行 ${number(breakdown.execution)}，评审 ${number(costs.evaluation)}，未确认预留 ${number(costs.unconfirmed)}\n`
    + `耗时：${typeof result.wall_time_ms === 'number' ? (result.wall_time_ms / 1000).toFixed(2) + ' 秒' : '未提供'}\n`
    + `记录：${String(result.result_path)}\n`
}
