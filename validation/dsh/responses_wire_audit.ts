// 实验进程专用：原样转发 SSE，只记录事件计数、正文长度及终止用量。
import {appendFileSync} from 'node:fs'

export class ResponsesWireAudit {
  private buffer = ''
  private written = false
  readonly counts: Record<string, number> = {}
  readonly lengths = {delta: 0, completedItems: 0, terminalOutput: 0, reasoningDelta: 0}
  private readonly emit: (row: Record<string, unknown>) => void
  private readonly request: Record<string, unknown>
  constructor(emit: (row: Record<string, unknown>) => void, request: Record<string, unknown> = {}) {
    this.emit = emit
    this.request = request
  }
  feed(text: string) {
    this.buffer += text
    // SSE 行的 CRLF 可能跨网络分块；只在完整事件边界归一化。
    const boundary = /\r?\n\r?\n/
    let match: RegExpExecArray | null
    while ((match = boundary.exec(this.buffer))) {
      const event = this.buffer.slice(0, match.index)
      this.buffer = this.buffer.slice(match.index + match[0].length)
      const payload = event.split(/\r?\n/).filter(line => line.startsWith('data:'))
        .map(line => line.slice(5).trimStart()).join('\n')
      if (!payload || payload === '[DONE]') continue
      const row = JSON.parse(payload)
      const type = typeof row.type === 'string' ? row.type : 'unknown'
      this.counts[type] = (this.counts[type] ?? 0) + 1
      if (type === 'response.output_text.delta') this.lengths.delta += String(row.delta ?? '').length
      if (type.includes('reasoning') && type.endsWith('.delta')) this.lengths.reasoningDelta += String(row.delta ?? '').length
      const textLength = (items: any[]) => items.filter(item => item?.type === 'message')
        .flatMap(item => Array.isArray(item.content) ? item.content : [])
        .filter(block => block?.type === 'output_text').reduce((sum, block) => sum + String(block.text ?? '').length, 0)
      if (type === 'response.output_item.done') this.lengths.completedItems += textLength([row.item])
      if (['response.completed', 'response.incomplete', 'response.failed'].includes(type) && !this.written) {
        this.lengths.terminalOutput = textLength(row.response?.output ?? [])
        const usage = row.response?.usage
        this.emit({schemaVersion:'responses-wire-lengths-v1', request:this.request,
          counts:{...this.counts}, lengths:{...this.lengths},
          status: row.response?.status, incompleteReason: row.response?.incomplete_details?.reason,
          usage: {inputTokens:usage?.input_tokens, outputTokens:usage?.output_tokens,
            reasoningTokens:usage?.output_tokens_details?.reasoning_tokens}})
        this.written = true
      }
    }
    if (this.buffer.length > 2 * 1024 * 1024) throw new Error('诊断 SSE 事件超出技术上限')
  }
}

export function installResponsesWireAudit(path: string): () => void {
  const original = globalThis.fetch
  globalThis.fetch = async (input, init) => {
    const response = await original(input, init)
    const url = input instanceof Request ? input.url : String(input)
    if (!new URL(url).pathname.endsWith('/responses') || !response.body
        || !response.headers.get('content-type')?.includes('text/event-stream')) return response
    const raw = typeof init?.body === 'string' ? JSON.parse(init.body) : {}
    const request = {model:raw.model, maxOutputTokens:raw.max_output_tokens, reasoningEffort:raw.reasoning?.effort}
    const audit = new ResponsesWireAudit(row => appendFileSync(path, JSON.stringify(row)+'\n', {mode:0o600}), request)
    const decoder = new TextDecoder()
    const body = response.body.pipeThrough(new TransformStream<Uint8Array, Uint8Array>({
      transform(chunk, controller) {audit.feed(decoder.decode(chunk, {stream:true})); controller.enqueue(chunk)},
      flush() {audit.feed(decoder.decode())},
    }))
    return new Response(body, {status:response.status, statusText:response.statusText, headers:response.headers})
  }
  return () => {globalThis.fetch = original}
}
