/** DSH rc.3 的失败 attempt 重放可能撤回已显示的 Chat 节点。
 * 仅为本插件的自动入口保留隐藏节点，不改变审核结果、历史或 Agent 状态。
 */
export interface AssistantViewNode {
  key: string
  kind: string
  id: string
  target: string
  data: unknown
  visibility?: string
}

export interface AssistantViewContext {
  current: ReadonlyMap<string, AssistantViewNode | null>
  matches?: readonly {event?: {type?: string;data?: {chunk?: {type?: string;text?: string}}};
    location?: {turn?: {steps?: readonly {data: {get(key: string): unknown}}[]}}}[]
}

export interface AssistantDefinition {
  kind: string
  target?: string
  buildViewNode?: (context: AssistantViewContext) => AssistantViewNode | null
}

export interface AssistantEventRegistry {
  entries(): readonly AssistantDefinition[]
  subscribe(listener: () => void): () => void
  register?(definition: ReturnType<typeof automaticAttemptDefinition>): () => void
}

export const AUTOMATIC_ATTEMPT_KEY = 'refractagent-automatic-attempt'
interface AttemptEvent {type: string;data: {turn: number;step: number;stream?: unknown[]}}
interface AttemptMatch {event: AttemptEvent}
interface AttemptState {turn: number;step: number;refs: {id: string;turn: number;state:'interrupted';error?:string}[]}
const RUN_ID = /^\d{8}T\d{6}Z-[0-9a-f]{12}$/

/** 失败 attempt 不进入普通助手历史；只发布受控运行引用供轨迹页读取。 */
export function automaticAttemptDefinition() {
  function read(event: AttemptEvent): AttemptState {
    const {turn,step}=event.data, records=event.data.stream??[]
    const text=records.filter((v): v is {type:'reasoning-chunks';texts:string[]} =>
      v!==null && typeof v==='object' && (v as {type?:string}).type==='reasoning-chunks'
      && Array.isArray((v as {texts?:unknown}).texts)
      && (v as {texts:unknown[]}).texts.every(t=>typeof t==='string'))
      .map(v=>v.texts.join('')).join('\n')
    if (!/^(正在预检并执行真实自动路由。|正在预览自动拆分流程。)/.test(text))
      return {turn,step,refs:[]}
    const ids=[...text.matchAll(/【自动路由记录】(\d{8}T\d{6}Z-[0-9a-f]{12})/g)]
      .map(v=>v[1])
    const finish=records.flatMap(v=>{
      if (!v || typeof v!=='object') return []
      const record=v as {type?:string;chunk?:{type?:string;reason?:{failure?:{message?:unknown}};
        replayState?:{response?:{refractagent?:{runId?:unknown}}}}}
      return record.type==='chunk' && record.chunk?.type==='finish' ? [record.chunk] : []
    }).at(-1)
    const id=finish?.replayState?.response?.refractagent?.runId
    if(typeof id==='string' && RUN_ID.test(id)) ids.push(id)
    const error=finish?.reason?.failure?.message
    return {turn,step,refs:[...new Set(ids)].slice(-20).map(id=>({id,turn,state:'interrupted',
      ...(typeof error==='string'?{error:error.slice(0,1000)}:{})}))}
  }
  return {
    kind: AUTOMATIC_ATTEMPT_KEY,
    match(event: AttemptEvent) {return event.type==='step/start' || event.type==='assistant/attempt'
      ? {id:`${event.data.turn}:${event.data.step}`,role:event.type==='step/start'?'start' as const:'update' as const}:null},
    start(_context: unknown, match: AttemptMatch): AttemptState {return read(match.event)},
    update(context: {state?:AttemptState}, match: AttemptMatch): AttemptState {
      const next=read(match.event)
      const refs=new Map((context.state?.refs??[]).map(ref=>[ref.id,ref]))
      for(const ref of next.refs)refs.set(ref.id,ref)
      return {...next,refs:[...refs.values()].slice(-20)}
    },
    buildLocationData(context: {state?:AttemptState}, scope: string) {
      const state=context.state
      return scope==='step' && state?.refs.length
        ? {kind:'step' as const,turn:state.turn,step:state.step,key:AUTOMATIC_ATTEMPT_KEY,value:state}:null
    },
  }
}

function ownAutomaticNode(node: AssistantViewNode): boolean {
  if (node.kind !== 'assistant-step' || node.target !== 'chat'
    || node.data === null || typeof node.data !== 'object') return false
  const blocks = (node.data as {blocks?: unknown}).blocks
  return Array.isArray(blocks) && blocks.some(block => block?.kind === 'reasoning'
    && typeof block.text === 'string' && (block.text.startsWith('正在预检并执行真实自动路由。\n')
      || block.text.startsWith('正在预览自动拆分流程。\n')))
}

function ownAutomaticTurn(context: AssistantViewContext): boolean {
  return (context.matches ?? []).some(match => {
    const chunk=match.event?.data?.chunk
    if(match.event?.type==='assistant/live-chunk' && chunk?.type==='reasoning-delta'
      && typeof chunk.text==='string' && /^(正在预检并执行真实自动路由。|正在预览自动拆分流程。)/.test(chunk.text))
      return true
    return match.location?.turn?.steps?.some(step => {
      const value=step.data.get(AUTOMATIC_ATTEMPT_KEY) as {refs?: unknown[]}|undefined
      return Array.isArray(value?.refs) && value.refs.length>0
    }) ?? false
  })
}

/** 临时宿主兼容：未来宿主正常返回节点时完全沿用它的结果。 */
export function retainAutomaticAttemptNode(registry: AssistantEventRegistry): () => void {
  const patched = new Map<AssistantDefinition, {
    original: NonNullable<AssistantDefinition['buildViewNode']>
    wrapper: NonNullable<AssistantDefinition['buildViewNode']>
  }>()
  function refresh(): void {
    for (const definition of registry.entries()) {
      if (!['assistant-step','turn-process'].includes(definition.kind) || definition.target !== 'chat'
        || !definition.buildViewNode || patched.has(definition)) continue
      const original = definition.buildViewNode
      const wrapper: typeof original = function(context) {
        const result = original.call(definition, context)
        if (result !== null) return result
        const previous = context.current.get('chat')
        if (!previous || !(ownAutomaticNode(previous)
          || (previous.kind==='turn-process' && ownAutomaticTurn(context)))) return result
        // 同一 key 的隐藏投影满足宿主增量更新合同；失败提示仍由宿主显示。
        return previous.visibility === 'hidden' ? previous : {...previous, visibility: 'hidden'}
      }
      definition.buildViewNode = wrapper
      patched.set(definition, {original, wrapper})
    }
  }
  refresh()
  const unsubscribe = registry.subscribe(refresh)
  return () => {
    unsubscribe()
    for (const [definition, {original, wrapper}] of patched) {
      if (definition.buildViewNode === wrapper) definition.buildViewNode = original
    }
    patched.clear()
  }
}
