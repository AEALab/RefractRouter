import assert from 'node:assert/strict'
import test from 'node:test'
import {ResponsesWireAudit, installResponsesWireAudit} from './responses_wire_audit.ts'
import {mkdtempSync, readFileSync, rmSync} from 'node:fs'
import {tmpdir} from 'node:os'
import {join} from 'node:path'

test('分块 SSE 保留正文各层长度，但不保存正文、请求或推理内容', () => {
  const records: Record<string, any>[] = []
  const audit = new ResponsesWireAudit(row => records.push(row))
  const events = [
    {type:'response.output_text.delta', delta:'秘密正文'},
    {type:'response.reasoning_summary_text.delta',delta:'秘密推理'},
    {type:'response.output_item.done',item:{type:'message',content:[{type:'output_text',text:'完整正文'}]}},
    {type:'response.incomplete',response:{status:'incomplete',incomplete_details:{reason:'length'},
      output:[{type:'message',content:[{type:'output_text',text:'最终正文'}]}],
      usage:{input_tokens:10,output_tokens:8192,output_tokens_details:{reasoning_tokens:8192}}}},
  ].map(row => 'data: '+JSON.stringify(row)+'\r\n\r\n').join('')
  for (const character of events) audit.feed(character)
  assert.equal(records.length,1)
  assert.deepEqual(records[0].lengths,{delta:4,completedItems:4,terminalOutput:4,reasoningDelta:4})
  assert.equal(records[0].incompleteReason,'length')
  assert.equal(records[0].usage.reasoningTokens,8192)
  assert.equal(JSON.stringify(records).includes('秘密'),false)
})

test('fetch 诊断原样保留响应字节、状态和头，不记录密钥或任务', async () => {
  const folder = mkdtempSync(join(tmpdir(),'refract-wire-'))
  const path = join(folder,'wire.ndjson')
  const original = globalThis.fetch
  const payload = 'data: '+JSON.stringify({type:'response.completed',response:{status:'completed',
    output:[{type:'message',content:[{type:'output_text',text:'中文正文'}]}],usage:{input_tokens:1,output_tokens:2}}})+'\n\n'
  globalThis.fetch = async () => new Response(payload,{headers:{'content-type':'text/event-stream','x-fixture':'kept'}})
  const restore = installResponsesWireAudit(path)
  try {
    const response = await fetch('https://fixture.invalid/responses',{method:'POST',
      headers:{Authorization:'Bearer secret-key'},body:JSON.stringify({model:'fixture',input:'secret-task',max_output_tokens:8192,reasoning:{effort:'low'}})})
    assert.equal(response.headers.get('x-fixture'),'kept')
    assert.equal(await response.text(),payload)
    const raw = readFileSync(path,'utf8')
    assert.ok(!raw.includes('secret-key') && !raw.includes('secret-task') && !raw.includes('中文正文'))
    assert.equal(JSON.parse(raw).lengths.terminalOutput,4)
    assert.equal(JSON.parse(raw).request.reasoningEffort,'low')
  } finally {restore();globalThis.fetch=original;rmSync(folder,{recursive:true})}
})
