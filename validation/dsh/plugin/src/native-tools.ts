/** DSH 原生执行边界；不选模型、不执行路由，也不解析正文中的伪工具标记。 */
import { randomUUID } from 'node:crypto'

export const TOOL_PROTOCOL = 'refractrouter-tools/v1'
export interface ToolSchema { name: string; description: string; parameters: Record<string, unknown> }
export interface NativeAgent {
  session: {
    events: readonly { type: string; data: Record<string, unknown> }[]
    append(type: string, data: Record<string, unknown>): unknown
  }
}
export interface NativeToolContext {
  agents?: { requireInitiator(): NativeAgent }
  tools?: { execute(input: { callId: string; name: string; arguments: unknown; agent: NativeAgent; signal: AbortSignal }): Promise<{
    isError: boolean; content: Array<Record<string, unknown>>; additionalContexts?: unknown[];
    concludesTurn?: true; meta?: unknown; error?: { info?: { name: string; code: string } }
  }> }
}
function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}
export function bindNativeTools(ctx: NativeToolContext, schemas: ToolSchema[]) {
  if (!schemas.length) return undefined
  if (!ctx.tools || !ctx.agents) throw new Error('RefractAgent requires DSH native tools and agents services')
  const agent = ctx.agents.requireInitiator()
  const stepEvent = [...agent.session.events].reverse().find(e=>e.type === 'step/start' || e.type === 'step/end' || e.type === 'turn/end')
  if (stepEvent?.type !== 'step/start' || typeof stepEvent.data.turn !== 'number' || typeof stepEvent.data.step !== 'number') {
    throw new Error('RefractAgent tool execution requires an active DSH step')
  }
  const step = { turn: stepEvent.data.turn, step: stepEvent.data.step }
  // 使用宿主本次请求组装的可见工具，不能从全局注册表扩大可用范围。
  const frozen = structuredClone(schemas)
  const allowed = new Set(frozen.map(s=>s.name))
  const seen = new Set<string>()
  let closed = false
  return {
    schemas: frozen,
    async execute(raw: unknown, signal: AbortSignal): Promise<Record<string, unknown>> {
      if (!object(raw)) throw new Error('invalid tool bridge request')
      const base = { protocol: TOOL_PROTOCOL, type: 'response', id: String(raw.id ?? '') }
      signal.throwIfAborted()
      const call = raw.call
      if (closed || seen.size >= 64 || raw.protocol !== TOOL_PROTOCOL || raw.type !== 'request'
          || typeof raw.node !== 'string' || !object(call) || call.type !== 'function'
          || typeof call.id !== 'string' || !object(call.function)
          || typeof call.function.name !== 'string' || !allowed.has(call.function.name)
          || typeof call.function.arguments !== 'string') throw new Error('invalid or unavailable native tool call')
      const key = `${raw.node}\u0000${call.id}`
      if (seen.has(key)) throw new Error('duplicate native tool call')
      const args: unknown = JSON.parse(call.function.arguments)
      if (!object(args)) throw new Error('native tool arguments must be an object')
      seen.add(key)
      const callId = `refractagent-${randomUUID()}`
      const name = call.function.name
      // 节点工具证据由 Python tool_calls 持久化。DSH 不支持外部自定义事件的重载，
      // 也不能把内部工具结果加入外层模型历史，因此不向宿主会话伪造工具事件。
      try {
        const result = await ctx.tools!.execute({ callId, name, arguments: args, agent, signal })
        if (result.concludesTurn) closed = true
        signal.throwIfAborted()
        return { ...base, ok: true, result: { isError: result.isError, content: result.content,
          additionalContexts: result.additionalContexts ?? [],
          ...(result.error?.info ? { error: result.error.info } : {}), concludesTurn: result.concludesTurn === true } }
      } catch (error) {
        closed = true
        throw error
      }
    },
  }
}
export type NativeToolsBridge = NonNullable<ReturnType<typeof bindNativeTools>>
