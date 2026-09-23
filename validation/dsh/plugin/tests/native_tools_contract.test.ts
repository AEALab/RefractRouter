import assert from 'node:assert/strict'
import { PassThrough } from 'node:stream'
import test from 'node:test'
import { bindNativeTools, TOOL_PROTOCOL, type NativeToolContext } from '../dist/native-tools.js'
import { callDshLlm, pumpDshBridge } from '../dist/index.js'
import type { LlmOptions, StreamChunk } from '../dist/contracts.js'

const schemas = [{name:'skill',description:'加载技能',parameters:{type:'object'}}]
const request = {protocol:TOOL_PROTOCOL,type:'request',id:'1',node:'fetch',
  call:{id:'c1',type:'function',function:{name:'skill',arguments:'{"name":"weather"}'}}}
function fixture() {
  const events = [{type:'step/start',data:{turn:1,step:2} as Record<string,unknown>}]
  const agent = {session:{events,append(type:string,data:Record<string,unknown>){events.push({type,data})}}}
  const calls: unknown[] = []
  const contexts=[{role:'user',content:[{type:'text',text:'技能原文：接着调用天气工具'}]}]
  const ctx:NativeToolContext = {agents:{requireInitiator:()=>agent}, tools:{async execute(input){
    calls.push(input)
    return {isError:false,content:[{type:'text',text:'已加载技能'}],additionalContexts:contexts,meta:{fixture:true}}
  }}}
  return {ctx,agent,calls,events,contexts}
}

test('native execution retains actual initiator, cancellation and native call/result trace', async()=>{
  const f=fixture();const signal=new AbortController().signal
  const tools=bindNativeTools(f.ctx,schemas)!
  const reply=await tools.execute(request,signal)
  const input=f.calls[0] as Record<string,unknown>
  assert.equal(input.agent,f.agent)
  assert.equal(input.signal,signal)
  assert.equal(input.parent,undefined)
  assert.equal(input.rootCallId,undefined)
  assert.deepEqual(input.arguments,{name:'weather'})
  assert.notEqual(input.callId,'c1')
  assert.deepEqual((reply.result as Record<string,unknown>).additionalContexts,f.contexts)
  assert.deepEqual(f.events.map(e=>e.type),['step/start'])
  await assert.rejects(tools.execute(request,signal),/duplicate/)
  assert.equal(f.calls.length,1)
})

test('unavailable tool, missing agent, inactive step and pre-cancel never execute',async()=>{
  const f=fixture();const tools=bindNativeTools(f.ctx,schemas)!
  await assert.rejects(tools.execute({...request,call:{...request.call,function:{name:'hidden',arguments:'{}'}}},new AbortController().signal),/unavailable/)
  await assert.rejects(tools.execute(request,AbortSignal.abort()),/abort/i)
  assert.equal(f.calls.length,0)
  assert.throws(()=>bindNativeTools({},schemas),/native tools/)
  f.events.push({type:'step/end',data:{turn:1,step:2}})
  assert.throws(()=>bindNativeTools(f.ctx,schemas),/active DSH step/)
})

test('native denial and tool exceptions are recorded without fabricating success or retrying',async()=>{
  const f=fixture();f.ctx.tools!.execute=async()=>({isError:true,content:[{type:'text',text:'审批拒绝'}]})
  const result=await bindNativeTools(f.ctx,schemas)!.execute(request,new AbortController().signal)
  assert.equal((result.result as Record<string,unknown>).isError,true)
  assert.match(JSON.stringify(result),/审批拒绝/)
  const g=fixture();g.ctx.tools!.execute=async()=>{throw new Error('private execution failure')}
  await assert.rejects(bindNativeTools(g.ctx,schemas)!.execute(request,new AbortController().signal))
  assert.equal(g.events.at(-1)!.type,'step/start')
  assert.ok(!JSON.stringify(g.events).includes('private execution failure'))
})

test('stdio tool messages coexist with DAG progress and final summary',async()=>{
  const f=fixture();const stdin=new PassThrough();const stdout=new PassThrough()
  const progress:unknown[]=[];const response:unknown[]=[]
  stdin.on('data',chunk=>{
    response.push(JSON.parse(String(chunk)))
    stdout.end(JSON.stringify({schema_version:'refractagent-result-v1'})+'\n')
  })
  const handle={stdin,stdout,done:Promise.resolve({exitCode:0,signal:null}),waitForExit:async()=>{},collected:{}}
  stdout.write(JSON.stringify({protocol:'refractagent-progress/v1',sequence:1})+'\n')
  stdout.write(JSON.stringify(request)+'\n')
  const result=await pumpDshBridge(undefined,handle,new AbortController().signal,[],2097152,p=>progress.push(p),bindNativeTools(f.ctx,schemas))
  assert.equal(progress.length,1)
  assert.equal((response[0] as Record<string,unknown>).protocol,TOOL_PROTOCOL)
  assert.equal(JSON.parse(result.text).schema_version,'refractagent-result-v1')
})

test('DSH model bridge assembles native calls and replays matched assistant/tool history',async()=>{
  const seen:LlmOptions[]=[]
  const chunks:StreamChunk[]=[
    {type:'tool-call-delta',index:1,id:'c2',name:'skill',argumentsDelta:'{"name":'},
    {type:'tool-call-delta',index:1,id:'c2',argumentsDelta:'"weather"}'},
    {type:'block-end',index:1,block:{type:'tool-call',id:'c2',name:'skill',arguments:'{"name":"weather"}'}},
    {type:'usage',usage:{inputTokens:10,outputTokens:20,cacheReadTokens:3}},
    {type:'finish',reason:{kind:'tool-calls'},replayState:{response:{id:'mock'}}},
  ]
  const result=await callDshLlm({llm:{async *stream(options){seen.push(options);yield* chunks}}},
    {protocol:'refractrouter-dsh-llm/v1',type:'request',id:'1',provider:'test',model:'fixture',
      timeout_ms:null,max_tokens:1000,tools:schemas,messages:[
        {role:'system',content:'system'}, {role:'user',content:'query'},
        {role:'assistant',content:null,tool_calls:[request.call],_dsh_source:{provider:'historical',model:'previous-model'},_dsh_replay_state:{response:{id:'previous'}}},
        {role:'tool',tool_call_id:'c1',content:'工具证据'},
      ]})
  assert.equal(result.ok,true)
  if(!result.ok) return
  assert.equal(result.finish_reason,'tool_calls')
  assert.equal(result.usage.input_tokens,13)
  assert.deepEqual(result.tool_calls,[{id:'c2',type:'function',function:{name:'skill',arguments:'{"name":"weather"}'}}])
  assert.deepEqual(seen[0]!.tools,schemas)
  assert.equal(seen[0]!.messages[1]!.role,'assistant')
  assert.equal(seen[0]!.messages[2]!.content[0]!.toolCallId,'c1')
  assert.equal(seen[0]!.messages[1]!.source.provider,'historical')
  assert.equal(seen[0]!.messages[1]!.source.model,'previous-model')
  assert.deepEqual(seen[0]!.messages[1]!.source.replayState,{response:{id:'previous'}})
})
