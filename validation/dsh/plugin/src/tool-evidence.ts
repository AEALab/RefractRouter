/** 捕获 DSH 工具流水线的规范结果；仅传递事实，不在 TypeScript 中做路由判定。 */
type Json = Record<string, unknown>

interface ToolExecutionFact {
  callId: string
  name: string
  agent?: { session: { header?: { id?: string } } }
}

interface ToolResultFact {
  isError: boolean
  value?: unknown
}

function object(value: unknown): value is Json {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function shellFact(value: unknown): Json | undefined {
  if (!object(value) || value.kind !== 'foreground') return undefined
  const exitCode = value.exitCode
  const signal = value.signal
  if (!(exitCode === null || typeof exitCode === 'number' && Number.isSafeInteger(exitCode))
      || !(signal === null || typeof signal === 'string')
      || typeof value.timedOut !== 'boolean' || typeof value.aborted !== 'boolean') return undefined
  const fact: Json = { exitCode, signal, timedOut: value.timedOut, aborted: value.aborted }
  if (object(value.sandbox)) {
    const sandbox: Json = {}
    if (typeof value.sandbox.mode === 'string') sandbox.mode = value.sandbox.mode
    if (typeof value.sandbox.denied === 'boolean') sandbox.denied = value.sandbox.denied
    if (typeof value.sandbox.runnerFailed === 'boolean') sandbox.runnerFailed = value.sandbox.runnerFailed
    if (Object.keys(sandbox).length) fact.sandbox = sandbox
  }
  return fact
}

export class ToolEvidenceCapture {
  private sessions = new Map<string, Map<string, Json>>()

  observe(exec: ToolExecutionFact, result: ToolResultFact): void {
    if (result.isError || !['bash', 'pwsh'].includes(exec.name)) return
    const session = exec.agent?.session.header?.id
    const fact = shellFact(result.value)
    if (!session || !fact) return
    let calls = this.sessions.get(session)
    if (!calls) {
      calls = new Map()
      this.sessions.set(session, calls)
    }
    calls.set(exec.callId, fact)
    while (calls.size > 256) calls.delete(calls.keys().next().value!)
  }

  enrich(session: string, events: readonly {type: string; data: Json}[]): Array<{type: string; data: Json}> {
    const calls = this.sessions.get(session)
    return events.map(event => {
      if (event.type !== 'tool/result' || !calls) return {type:event.type,data:event.data}
      const message = object(event.data.message) ? event.data.message : undefined
      const source = message && object(message.source) ? message.source : undefined
      const callId = typeof source?.callId === 'string' ? source.callId : undefined
      const hostResult = callId ? calls.get(callId) : undefined
      return {type:event.type,data:hostResult ? {...event.data,hostResult} : event.data}
    })
  }
}
