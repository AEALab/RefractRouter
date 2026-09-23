import assert from 'node:assert/strict'
import test from 'node:test'
import { spawn } from 'node:child_process'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'
import { configure,createAdapter,type AgentContext,type ModelOptions } from '../dist/agent-provider.js'
import { PlanningController,PlanningWorker,planningMessages } from '../dist/planning-routing.js'
import type { PlanningConfig } from '../dist/planning-config.js'
import type { StreamChunk } from '../dist/contracts.js'

const root=resolve('../../..')
const config:PlanningConfig={schemaVersion:'refractagent-planning-v1',enabled:true,maxProductionCost:10,
  models:['small','large','judge'].map(id=>({id,provider:'fake',model:id,contextWindow:32000,maxOutputTokens:1024,
    inputPer1k:.001,outputPer1k:.002,deployment:'local',reasoningEffort:'low'})),
  roles:{efficient:'small',capable:'large',classifier:'judge',advisor:'judge'}}
const tool={type:'tool-call',id:'read1',name:'read',arguments:'{}'}
function* reply(text:string,blocks:Record<string,unknown>[]=[]):Generator<StreamChunk>{
  let index=0
  if(text){
    yield {type:'block-start',index,block:{type:'text'}}
    yield {type:'text-delta',index,text}
    yield {type:'block-end',index:index++,block:{type:'text',text} as any}
  }
  for(const block of blocks){
    yield {type:'block-start',index,block:{type:'tool-call'}}
    yield {type:'block-end',index:index++,block:block as any}
  }
  yield {type:'usage',usage:{inputTokens:100,outputTokens:20}}
  yield {type:'finish',reason:{kind:blocks.length?'tool-calls':'stop'},replayState:{response:{native:'source'}}}
}
async function fixture(strategy='static'){
  const path=await mkdtemp(resolve(tmpdir(),'rr-planning-'))
  const events=[{type:'step/start',data:{turn:1,step:1} as Record<string,unknown>}]
  const calls:any[]=[]
  let replies:Array<()=>Iterable<StreamChunk>>=[]
  let toolExecutions=0,disposal:(()=>void)|undefined
  const ctx:AgentContext={
    llm:{registerAdapter(){},async *stream(options){calls.push(options);yield* (replies.shift()?.()??reply('完成'))}},
    agents:{requireInitiator:()=>({id:'native-session',session:{header:{id:'native-session'},events,append(){}}})},
    tools:{async execute(){toolExecutions++;throw new Error('插件不应执行宿主工具')}},
    credentials:{async describe(){return {configured:true}},async resolve(){throw new Error('凭证仅由宿主使用')}},
    effect(setup){disposal=setup() as ()=>void},
    sandboxPolicy:{resolve:()=>({mode:'workspace-write',workspaceRoot:root})},
    sandbox:{confine:argv=>({argv,enforcement:'full'})},
    subprocess:{
      async resolveExecutable(){return resolve(root,'.venv/bin/python')},
      spawn(spec){
        const child=spawn(spec.argv[0],spec.argv.slice(1),{cwd:spec.cwd,env:spec.env,stdio:'pipe',signal:spec.signal})
        child.on('error',()=>{})
        const done=new Promise<{exitCode:number|null;signal:string|null}>(res=>child.once('exit',(exitCode,signal)=>res({exitCode,signal})))
        return {stdin:child.stdin,stdout:child.stdout,done,waitForExit:()=>done,terminate:()=>{child.kill()},collected:{}}
      }
    }
  }
  const frozen=configure({pythonExecutable:resolve(root,'.venv/bin/python'),runsDir:path,planningRouting:config})
  const worker=new PlanningWorker(ctx,()=>frozen)
  const controller=new PlanningController(ctx,()=>frozen,worker)
  const options:ModelOptions={provider:'refractagent',model:'planning',reasoningEffort:'rr:'+strategy,
    sessionId:'native-session',messages:[{role:'user',content:[{type:'text',text:'测试'}]}],
    tools:[{name:'read',description:'read',parameters:{type:'object'}}]}
  return {ctx,controller,calls,events,options,path,
    setReplies(v:typeof replies){replies=v},get toolExecutions(){return toolExecutions},
    async cleanup(){disposal?.();worker.dispose();await new Promise(r=>setTimeout(r,50));await rm(path,{recursive:true,force:true})}}
}
async function collect(iterable:AsyncIterable<Record<string,unknown>>){const out:Record<string,unknown>[]=[];for await(const v of iterable)out.push(v);return out}

test('真实 Python worker 经 DSH 模拟循环完成两轮工具续接，插件不执行工具',async()=>{
  const f=await fixture()
  try{
    f.setReplies([()=>reply('',[tool]),()=>reply('完成')])
    const first=await collect(f.controller.stream(f.options))
    const finish=first.find(c=>c.type==='finish') as any
    assert.equal(f.toolExecutions,0)
    assert.equal(f.calls[0].reasoningEffort,'low')
    assert.ok(!JSON.stringify(f.calls[0]).includes('rr:'))
    f.events.push({type:'step/start',data:{turn:1,step:2}})
    const second=await collect(f.controller.stream({...f.options,messages:[...f.options.messages,
      {role:'assistant',content:[tool],source:{kind:'model',provider:'refractagent',model:'planning',replayState:finish.replayState}},
      {role:'user',content:[{type:'tool-result',toolCallId:'read1',content:[{type:'text',text:'文件内容'}]}]}]}))
    assert.equal(f.calls[1].messages[1].source.provider,'fake')
    assert.equal(f.calls[1].messages[1].source.model,'small')
    assert.deepEqual(f.calls[1].messages[1].source.replayState,{response:{native:'source'}})
    assert.ok(second.some(c=>c.type==='text-delta'&&c.text==='完成'))
    const history=await f.controller.history('native-session')
    assert.equal(history.records[0].calls.length,2)
    assert.ok(Math.abs(history.records[0].costs.production-.00028)<1e-10)
  }finally{await f.cleanup()}
})

test('审核丢弃的回复与工具不泄漏，全部实际调用记账',async()=>{
  const f=await fixture('advisor')
  try{
    f.setReplies([()=>reply('候选'),()=>reply('{"verdict":"REDO","feedback":"补证据"}'),()=>reply('接受')])
    const chunks=await collect(f.controller.stream(f.options))
    assert.deepEqual(chunks.filter(c=>c.type==='text-delta').map(c=>c.text),['接受'])
    assert.equal(f.calls.length,3)
    assert.equal(f.toolExecutions,0)
    const history=await f.controller.history('native-session')
    assert.deepEqual(history.records[0].calls.map((c:any)=>c.disposition),['discarded','consult','accepted'])
    assert.equal(history.records[0].calls[0].response_output,undefined)
  }finally{await f.cleanup()}
})

test('升级判别丢弃工具调用后只释放强模型回复',async()=>{
  const f=await fixture('escalation')
  try{
    f.setReplies([()=>reply('探索'),()=>reply('{"escalate":true}'),
      ()=>reply('',[tool]),()=>reply('{"escalate":true}'),()=>reply('强模型完成')])
    await collect(f.controller.stream(f.options))
    const chunks=await collect(f.controller.stream(f.options))
    assert.ok(!chunks.some(c=>(c.block as any)?.type==='tool-call'))
    assert.equal(f.calls.at(-1).model,'large')
    assert.equal(f.toolExecutions,0)
  }finally{await f.cleanup()}
})

test('切换策略当前轮保持冻结，新轮重新分类；取消不释放候选',async()=>{
  const f=await fixture('static')
  try{
    await collect(f.controller.stream(f.options))
    await collect(f.controller.stream({...f.options,reasoningEffort:'rr:task'}))
    assert.equal(f.calls.length,2)
    f.events.push({type:'step/start',data:{turn:2,step:1}})
    f.setReplies([()=>reply('{"p_solve":1,"capability_boundary":"supported"}'),()=>reply('完成')])
    await collect(f.controller.stream({...f.options,reasoningEffort:'rr:task'}))
    assert.equal(f.calls.length,4)
    f.events.push({type:'step/start',data:{turn:3,step:1}})
    const cancel=new AbortController()
    f.setReplies([()=>({*[Symbol.iterator](){yield* reply('候选');cancel.abort()}})])
    await assert.rejects(()=>collect(f.controller.stream({...f.options,reasoningEffort:'rr:advisor',signal:cancel.signal})))
    const history=await f.controller.history('native-session')
    assert.equal(history.records[0].status,'cancelled')
  }finally{await f.cleanup()}
})

test('规划入口可发现但未配置零调用拒绝；原生历史来源保持',async()=>{
  const f=await fixture()
  try{
    const adapter=createAdapter(f.ctx,()=>configure({}))
    assert.ok((await adapter.listModels('refractagent')).some(m=>m.id==='planning'))
    assert.equal((await adapter.resolveModel('refractagent','planning')).reasoning?.defaultEffort,'rr:stage')
    const original=[{role:'assistant',source:{kind:'model',provider:'other',model:'old'},
      content:[{type:'text',text:'历史'}]}]
    assert.deepEqual(planningMessages(original),original)
    assert.throws(()=>planningMessages([{...original[0],source:{kind:'model',provider:'refractagent',model:'auto'}}]),/真实来源/)
  }finally{await f.cleanup()}
})


test('宿主读取 finish 后结束消费不会取消任务；缺失 replay 仍保留真实来源',async()=>{
  const f=await fixture()
  try{
    f.setReplies([()=>({*[Symbol.iterator](){for(const chunk of reply('完成')){
      if(chunk.type==='finish')yield {...chunk,replayState:undefined}
      else yield chunk
    }}})])
    for await(const chunk of f.controller.stream(f.options))if(chunk.type==='finish'){
      assert.doesNotThrow(()=>JSON.parse(JSON.stringify(chunk)))
      const message={role:'assistant',content:[{type:'text',text:'完成'}],
        source:{kind:'model',provider:'refractagent',model:'planning',replayState:chunk.replayState}}
      assert.equal(planningMessages([message])[0].source.model,'small')
      break
    }
    const history=await f.controller.history('native-session')
    assert.equal(history.records[0].status,'running')
    await collect(f.controller.stream(f.options))
  }finally{await f.cleanup()}
})
test('审核修正反馈在后续回放中只追加一次，并保留来源',async()=>{
  const messages=planningMessages([{role:'assistant',content:[{type:'text',text:'修订'}],
    source:{kind:'model',provider:'refractagent',model:'planning',replayState:{response:{refractPlanning:{
      version:1,provider:'fake',model:'small',feedback:'补证据'}}}}}])
  assert.equal(messages.length,2)
  assert.match(messages[0].content[0].text,/补证据/)
  assert.equal(messages[1].source.model,'small')
})


test('未完成的规划模型容量不会破坏旧入口的目录元数据',async()=>{
  const f=await fixture()
  try{
    const draft=structuredClone(config) as any
    delete draft.models[0].contextWindow
    delete draft.models[0].maxOutputTokens
    const adapter=createAdapter(f.ctx,()=>configure({planningRouting:draft}))
    const models=await adapter.listModels('refractagent')
    assert.ok(models.some(m=>m.id==='balanced'))
    assert.ok(Number.isFinite(models.find(m=>m.id==='planning')?.context?.contextWindow))
  }finally{await f.cleanup()}
})
