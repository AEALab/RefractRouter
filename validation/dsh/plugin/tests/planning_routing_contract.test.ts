import assert from 'node:assert/strict'
import test from 'node:test'
import { spawn } from 'node:child_process'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'
import { configure,createAdapter,type AgentContext,type ModelOptions } from '../dist/agent-provider.js'
import { PlanningController,PlanningWorker,planningMessages } from '../dist/planning-routing.js'
import type { PlanningConfig, PlanningStrategy } from '../dist/planning-config.js'
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
async function fixture(strategy:PlanningStrategy='static'){
  const path=await mkdtemp(resolve(tmpdir(),'rr-planning-'))
  const events=[{type:'step/start',data:{turn:1,step:1} as Record<string,unknown>}]
  const calls:any[]=[]
  let replies:Array<()=>Iterable<StreamChunk>>=[]
  let toolExecutions=0,disposal:(()=>void)|undefined
  const providerRoutes:Record<string,{baseURL?:string;reasoning?:string}>={}
  const ctx:AgentContext={
    settings:{get:(key:string)=>key==='llm-pi-ai'?{providers:providerRoutes}:undefined} as any,
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
  let frozen=configure({pythonExecutable:resolve(root,'.venv/bin/python'),runsDir:path,planningRouting:{...config,defaultStrategy:strategy}})
  const worker=new PlanningWorker(ctx,()=>frozen)
  const controller=new PlanningController(ctx,()=>frozen,worker)
  const options:ModelOptions={provider:'refractagent',model:'planning',reasoningEffort:'rr:'+strategy,
    sessionId:'native-session',messages:[{role:'user',content:[{type:'text',text:'测试'}]}],
    tools:[{name:'read',description:'read',parameters:{type:'object'}}]}
  return {ctx,controller,calls,events,options,path,worker,
    setProviderBaseURL(provider:string,baseURL:string){providerRoutes[provider]={baseURL}},
    setProviderReasoning(provider:string,reasoning:string){providerRoutes[provider]={reasoning}},
    setStrategy(value:PlanningStrategy){frozen=configure({...frozen,planningRouting:{...config,defaultStrategy:value}})},
    setPlanning(value:PlanningConfig){frozen=configure({...frozen,planningRouting:value})},
    setReplies(v:typeof replies){replies=v},get toolExecutions(){return toolExecutions},
    async cleanup(){disposal?.();worker.dispose();await new Promise(r=>setTimeout(r,50));await rm(path,{recursive:true,force:true})}}
}
async function collect(iterable:AsyncIterable<Record<string,unknown>>){const out:Record<string,unknown>[]=[];for await(const v of iterable)out.push(v);return out}

test('Stage 新配置保持旧规则及原生工具边界',async()=>{
  const f=await fixture('stage')
  try{
    f.setPlanning({...config,schemaVersion:'refractagent-planning-v5',defaultStrategy:'stage',stage:{mode:'rules'}})
    await collect(f.controller.stream({...f.options,reasoningEffort:'rr:stage'}))
    assert.equal(f.calls[0].model,'small')
    assert.equal(f.toolExecutions,0)
    const history=await f.controller.history('native-session')
    assert.equal(history.records[0].configuration.schemaVersion,'refractagent-planning-v5')
    assert.equal(history.records[0].configuration.stage.mode,'rules')
    assert.equal(history.records[0].decisions[0].reason,'no-signal')
  }finally{await f.cleanup()}
})

test('Static 固定与随机的轨迹记录实际选法和权重',async()=>{
  const f=await fixture('static')
  try{
    const saved:PlanningConfig={...structuredClone(config),defaultStrategy:'static',
      parameters:{staticMode:'random',seed:7,efficientWeight:1,capableWeight:0}}
    f.setPlanning(saved)
    await collect(f.controller.stream(f.options))
    const record=(await f.controller.history('native-session')).records[0]
    assert.equal(record.decisions[0].reason,'static-random-selected')
    assert.deepEqual(record.decisions[0].staticChoice,
      {mode:'random',selectedRole:'efficient',efficientWeight:1,capableWeight:0})
    assert.equal(record.decisions[0].callId,record.calls[0].call_id)
  }finally{await f.cleanup()}
})

test('Task 与 Composite 的任务判别结果关联到随后执行模型',async()=>{
  for(const strategy of ['task','composite'] as const){
    const f=await fixture(strategy)
    try{
      f.setReplies([()=>reply('{"p_solve":0.9,"capability_boundary":"supported"}'),()=>reply('完成')])
      await collect(f.controller.stream({...f.options,reasoningEffort:'rr:'+strategy}))
      const record=(await f.controller.history('native-session')).records[0]
      const judge=record.decisions.find((row:any)=>row.role==='judge')
      const execution=record.decisions.find((row:any)=>row.role!=='judge')
      assert.equal(judge.reason,'task-classifier')
      assert.equal(judge.callId,record.calls[0].call_id)
      assert.equal(judge.judgeDecision.pSolve,0.9)
      assert.equal(execution.judgeDecision.candidateId,'small')
      assert.equal(execution.callId,record.calls[1].call_id)
    }finally{await f.cleanup()}
  }
})

test('Composite v6 复用 Task 模型池且首次执行跳过 Stage 判别',async()=>{
  const f=await fixture('composite')
  try{
    const configured:PlanningConfig={...structuredClone(config),schemaVersion:'refractagent-planning-v6',
      defaultStrategy:'composite',billingUnit:'CNY',maxProductionCostByUnit:{CNY:100},
      models:config.models?.map(model=>({...model,billingUnit:'CNY',capabilityCard:model.id==='small'?'常规任务':'困难任务',
        capabilities:{mainExecutor:model.id!=='judge',toolCalling:'verified',modalities:{}}})),
      composite:{pool:['small','large'],takeover:'large',judge:{type:'llm',modelId:'judge'},
        threshold:.8,maxInputChars:12000,maxExecutionOutputTokens:2048,
        stage:{mode:'rules',window:3,threshold:.5,holdTurns:2}}}
    f.setPlanning(configured)
    f.setReplies([()=>reply('{"answers":{"candidates":{"small":{"score":0.95,"missingInformation":0},"large":{"score":0.2,"missingInformation":0}}}}'),()=>reply('完成')])
    await collect(f.controller.stream({...f.options,reasoningEffort:'rr:composite'}))
    assert.deepEqual(f.calls.map(call=>call.model),['judge','small'])
    const record=(await f.controller.history('native-session')).records[0]
    assert.equal(record.configuration.schemaVersion,'refractagent-planning-v6')
    assert.equal(record.decisions.at(-1).reason,'composite-task-selected')
    assert.equal(record.decisions.at(-1).ruleVersion,'composite-rules-v1')
    assert.equal(record.decisions.at(-1).baseModel,'small')
    assert.equal(record.decisions.at(-1).takeoverModel,'large')
  }finally{await f.cleanup()}
})

test('Advisor 由 DSH 凭证边界派发 Jev Choice，并将用量交回 Router 结算',async()=>{
  const f=await fixture('advisor')
  const originalFetch=globalThis.fetch
  const sent:any[]=[]
  try{
    const configured:PlanningConfig={...structuredClone(config),schemaVersion:'refractagent-planning-v6',
      defaultStrategy:'advisor',billingUnit:'CNY',maxProductionCostByUnit:{CNY:100},
      models:config.models?.map(model=>({...model,billingUnit:'CNY',
        capabilities:{mainExecutor:model.id!=='judge',toolCalling:'verified',modalities:{}}})),
      advisor:{executor:'small',judge:{type:'jev'},threshold:.8,maxJudgeInputBytes:8000,
        judgeTimeoutMs:30000,maxExecutionOutputTokens:2048,maxJudgeOutputTokens:256},
      jev:{credentialRef:'typesafe-test',deployment:'external-cloud'}}
    f.setPlanning(configured)
    f.ctx.credentials.resolve=async reference=>{
      assert.equal(reference,'typesafe-test');return {value:'fixture-secret'}
    }
    globalThis.fetch=async (input,init)=>{
      assert.equal(String(input),'https://api.typesafe.ai/v1/systemone')
      assert.equal((init?.headers as Record<string,string>).Authorization,'Bearer fixture-secret')
      const payload=JSON.parse(String(init?.body));sent.push(payload)
      assert.equal(payload.model,'jev-1.13.0')
      return new Response(JSON.stringify({model:'jev-1.13.0',answers:{review:{type:'choice',
        choice:'APPROVE',probabilities:{APPROVE:.95,REDO_REQUIREMENT:.02,
          REDO_EVIDENCE:.02,UNRESOLVED:.01},confidence:.9}},
        usage:{input_tokens:300,output_tokens:20}}),{status:200})
    }
    f.setReplies([()=>reply('完成')])
    const output=await collect(f.controller.stream({...f.options,reasoningEffort:'rr:advisor'}))
    assert.equal(sent.length,1)
    assert.ok(output.some(chunk=>chunk.type==='text-delta'&&chunk.text==='完成'))
    assert.deepEqual(f.calls.map(call=>call.model),['small'])
    const record=(await f.controller.history('native-session')).records[0]
    const jev=record.calls.find((call:any)=>call.provider==='typesafe')
    assert.equal(jev.status,'billed')
    assert.equal(jev.billing_unit,'CNY')
    assert.equal(record.decisions.find((row:any)=>row.backend==='jev').selectedProbability,.95)
    assert.ok(!JSON.stringify(record).includes('fixture-secret'))
  }finally{globalThis.fetch=originalFetch;await f.cleanup()}
})

test('零调用检查在旧核心上明确阻断 Jev 配置',async()=>{
  const f=await fixture('stage')
  try{
    f.setPlanning({...structuredClone(config),schemaVersion:'refractagent-planning-v6',
      advisor:{executor:'small',judge:{type:'jev'},threshold:.8,maxJudgeInputBytes:8000,
        judgeTimeoutMs:30000,maxExecutionOutputTokens:2048,maxJudgeOutputTokens:256}})
    const operations:string[]=[]
    f.worker.request=async value=>{
      operations.push(String(value.op))
      if(value.op==='handshake')return {protocol:'refractagent-planning/4',
        capabilities:['escalation-decision-v1','local-judge-jobs']}
      throw new Error('不应在能力检查失败后进入预检')
    }
    await assert.rejects(f.controller.preview(),/当前核心不支持官方 Jev Judge/)
    assert.deepEqual(operations,['handshake'])
  }finally{await f.cleanup()}
})

test('未选中的 Jev 配置不会阻断 Static 执行',async()=>{
  const f=await fixture('static')
  try{
    f.setPlanning({...structuredClone(config),schemaVersion:'refractagent-planning-v6',
      defaultStrategy:'static',
      jev:{credentialRef:'not-configured',deployment:'external-cloud'},
      advisor:{executor:'small',judge:{type:'jev'}}})
    f.ctx.credentials.describe=async()=>({configured:false})
    f.setReplies([()=>reply('正常执行')])
    const output=await collect(f.controller.stream(f.options))
    assert.ok(output.some(chunk=>chunk.type==='text-delta'&&chunk.text==='正常执行'))
    assert.deepEqual(f.calls.map(call=>call.model),['small'])
  }finally{await f.cleanup()}
})

test('Composite 消费 DSH 原生失败事件，接管后保持并返回常用模型',async()=>{
  const f=await fixture('composite')
  try{
    const configured:PlanningConfig={...structuredClone(config),schemaVersion:'refractagent-planning-v6',
      defaultStrategy:'composite',billingUnit:'CNY',maxProductionCostByUnit:{CNY:100},
      models:config.models?.map(model=>({...model,billingUnit:'CNY',capabilityCard:'工具任务',
        capabilities:{mainExecutor:model.id!=='judge',toolCalling:'verified',modalities:{}}})),
      composite:{pool:['small','large'],takeover:'large',judge:{type:'llm',modelId:'judge'},
        maxExecutionOutputTokens:2048,maxJudgeOutputTokens:256,
        stage:{mode:'rules',window:3,threshold:.5,holdTurns:2}}}
    f.setPlanning(configured)
    f.setReplies([()=>reply('{"answers":{"candidates":{"C1":{"score":0.95,"missingInformation":0},"C2":{"score":0.2,"missingInformation":0}}}}')])
    await collect(f.controller.stream({...f.options,reasoningEffort:'rr:composite'}))
    const messages:any[]=[...f.options.messages]
    for(let index=0;index<2;index++){
      const callId=`failed-${index}`
      const call={type:'tool-call',id:callId,name:'bash',arguments:'{"cmd":"pytest"}'}
      const result={type:'tool-result',toolCallId:callId,isError:true,
        content:[{type:'text',text:'test failed'}]}
      messages.push({role:'assistant',content:[call]},{role:'user',content:[result]})
      f.events.push({type:'tool/call',data:{turn:1,step:index+1,callId,name:'bash',arguments:'{"cmd":"pytest"}'}})
      f.events.push({type:'tool/result',data:{turn:1,step:index+1,message:{content:[result]},
        error:{name:'CommandError',code:'EXIT_NONZERO'},meta:{exitCode:1}}})
    }
    for(let step=2;step<=4;step++){
      f.events.push({type:'step/start',data:{turn:1,step}})
      await collect(f.controller.stream({...f.options,reasoningEffort:'rr:composite',messages}))
    }
    assert.deepEqual(f.calls.map(call=>call.model),['judge','small','large','large','small'])
    const record=(await f.controller.history('native-session')).records[0]
    assert.deepEqual(record.decisions.filter((row:any)=>row.role!=='judge').map((row:any)=>row.reason),
      ['composite-task-selected','composite-repeated-failure','composite-takeover-hold','composite-return-base'])
  }finally{await f.cleanup()}
})

test('Stage 协作能力未握手通过时不能开始任务或付费调用',async()=>{
  const f=await fixture('stage')
  try{
    const request=f.worker.request.bind(f.worker)
    f.worker.request=async value=>value.op==='handshake'?{protocol:'refractagent-planning/4',
      capabilities:['escalation-decision-v1','local-judge-jobs']}:request(value)
    f.setPlanning({...config,schemaVersion:'refractagent-planning-v5',defaultStrategy:'stage',stage:{mode:'hybrid'}})
    await assert.rejects(()=>collect(f.controller.stream({...f.options,reasoningEffort:'rr:stage'})),/不支持 Stage 本地 Judge/)
    assert.equal(f.calls.length,0)
    assert.equal((await f.controller.history('native-session')).records.length,0)
  }finally{await f.cleanup()}
})

test('真实 Python worker 经 DSH 模拟循环完成两轮工具续接，插件不执行工具',async()=>{
  const f=await fixture()
  try{
    f.setReplies([()=>reply('',[tool]),()=>reply('完成')])
    const first=await collect(f.controller.stream(f.options))
    const finish=first.find(c=>c.type==='finish') as any
    assert.equal(finish.replayState.response.refractPlanning.version,2)
    assert.equal(finish.replayState.response.refractPlanning.contentContract,'dsh-content-blocks-v1')
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
    assert.deepEqual(history.records[0].decisions.map((row:any)=>row.reason),
      ['static-fixed','static-fixed'])
    assert.ok(Math.abs(history.records[0].costs.production-.00028*6.7459)<2e-8)
  }finally{await f.cleanup()}
})

test('没有 provider 默认档位时未声明推理能力的模型不传推理等级',async()=>{
  const f=await fixture()
  try{
    const saved=structuredClone(config)
    delete saved.models![0].reasoningEffort
    f.setPlanning(saved)
    f.ctx.llm.resolveModelInfo=async(provider,model)=>({provider,id:model,name:model,
      context:{contextWindow:32000},defaultMaxTokens:1024})
    await collect(f.controller.stream(f.options))
    assert.equal(f.calls[0].reasoningEffort,undefined)
  }finally{await f.cleanup()}
})

test('provider 默认推理档位与模型能力不符时零调用阻断',async()=>{
  const f=await fixture()
  try{
    const saved=structuredClone(config)
    delete saved.models![0].reasoningEffort
    f.setPlanning(saved)
    f.setProviderReasoning('fake','high')
    f.ctx.llm.resolveModelInfo=async(provider,model)=>({provider,id:model,name:model,
      context:{contextWindow:32000},defaultMaxTokens:1024})
    await assert.rejects(()=>collect(f.controller.stream(f.options)),/模型未声明推理等级.*provider 默认 high/)
    assert.equal(f.calls.length,0)
  }finally{await f.cleanup()}
})

test('使用宿主已声明且支持的模型默认推理等级',async()=>{
  const f=await fixture()
  try{
    const saved=structuredClone(config)
    delete saved.models![0].reasoningEffort
    f.setPlanning(saved)
    f.setProviderReasoning('fake','high')
    f.ctx.llm.resolveModelInfo=async(provider,model)=>({provider,id:model,name:model,
      context:{contextWindow:32000},defaultMaxTokens:1024,
      reasoning:{efforts:[{id:'low',name:'Low'},{id:'high',name:'High'}],defaultEffort:'high'}})
    await collect(f.controller.stream(f.options))
    assert.equal(f.calls[0].reasoningEffort,'high')
  }finally{await f.cleanup()}
})

test('Stage 重复失败升级、保持两次后恢复高效模型，并保留结构化决策',async()=>{
  const f=await fixture('stage')
  try{
    await collect(f.controller.stream({...f.options,reasoningEffort:'rr:stage'}))
    const messages:any[]=[...f.options.messages]
    for(let index=0;index<2;index++){
      const callId=`failed-${index}`
      const call={type:'tool-call',id:callId,name:'bash',arguments:'{"cmd":"pytest"}'}
      const result={type:'tool-result',toolCallId:callId,isError:true,
        content:[{type:'text',text:'test failed'}]}
      messages.push({role:'assistant',content:[call]},{role:'user',content:[result]})
      f.events.push({type:'tool/call',data:{turn:1,step:index+1,callId,name:'bash',arguments:'{"cmd":"pytest"}'}})
      f.events.push({type:'tool/result',data:{turn:1,step:index+1,message:{content:[result]},
        error:{name:'CommandError',code:'EXIT_NONZERO'},meta:{exitCode:1}}})
    }
    for(let step=2;step<=4;step++){
      f.events.push({type:'step/start',data:{turn:1,step}})
      await collect(f.controller.stream({...f.options,reasoningEffort:'rr:stage',messages}))
    }
    assert.deepEqual(f.calls.map(call=>call.model),['small','large','large','small'])
    const record=(await f.controller.history('native-session')).records[0]
    assert.deepEqual(record.decisions.map((decision:any)=>decision.reason),
      ['no-signal','repeated-failure','capable-hold','no-signal'])
    assert.deepEqual(record.decisions[1].evidenceIds,['1:1:failed-0','1:2:failed-1'])
    assert.equal(record.decisions[1].holdBefore,0)
    assert.equal(record.decisions[1].holdAfter,1)
    assert.equal(record.decisions[1].ruleVersion,'stage-v4')
    assert.equal(record.calls[1].reasoning_effort,'low')
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
    const rows=history.records[0].decisions
    assert.ok(rows.some((row:any)=>row.reason==='advisor-redo-required'
      &&row.candidateCallId===history.records[0].calls[0].call_id))
    assert.ok(rows.some((row:any)=>row.reason==='advisor-redo'))
  }finally{await f.cleanup()}
})

test('Advisor v6 返工后的最终回复必须复审通过才交付',async()=>{
  const f=await fixture('advisor')
  try{
    const advisorV6:PlanningConfig={...structuredClone(config),schemaVersion:'refractagent-planning-v6',
      defaultStrategy:'advisor',billingUnit:'CNY',maxProductionCostByUnit:{CNY:100},maxCalls:12,
      models:config.models!.map(model=>({...model,billingUnit:'CNY'})),
      advisor:{executor:'small',judge:{type:'llm',modelId:'judge'},threshold:.8,
        judgeTimeoutMs:30000,maxJudgeInputBytes:8000,maxExecutionOutputTokens:2048,
        maxJudgeOutputTokens:256}}
    f.setPlanning(advisorV6)
    f.setReplies([()=>reply('遗漏要求'),()=>reply('{"verdict":"REDO","feedback":"补证据"}'),
      ()=>reply('已补证据'),()=>reply('{"verdict":"APPROVE"}')])
    const chunks=await collect(f.controller.stream(f.options))
    assert.deepEqual(chunks.filter(c=>c.type==='text-delta').map(c=>c.text),['已补证据'])
    assert.deepEqual(f.calls.map(call=>call.model),['small','judge','small','judge'])
    const record=(await f.controller.history('native-session')).records[0]
    assert.deepEqual(record.calls.map((row:any)=>row.disposition),
      ['discarded','consult','accepted','consult'])
    assert.equal(record.calls[2].review_status,'reapproved')
    assert.ok(record.decisions.some((row:any)=>row.reason==='advisor-reapproved'
      &&row.reviewCount===2&&row.reviewPhase==='approved'))
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
    const record=(await f.controller.history('native-session')).records[0]
    assert.ok(record.decisions.some((row:any)=>row.reason==='escalation-takeover'
      &&row.candidateCallId===record.calls[2].call_id))
  }finally{await f.cleanup()}
})

test('Escalation v4 明确缺陷立即丢弃候选并由强模型流式接管',async()=>{
  const f=await fixture('escalation')
  try{
    const upgraded:PlanningConfig={...structuredClone(config),schemaVersion:'refractagent-planning-v4',
      defaultStrategy:'escalation',escalation:{initial:'small',takeover:'large',judge:{type:'llm',modelId:'judge'},
        stallConfirmations:2,threshold:.8,judgeTimeoutMs:30000,maxJudgeInputBytes:8000,
        maxExecutionOutputTokens:1024,maxJudgeOutputTokens:256}}
    f.setPlanning(upgraded)
    f.setReplies([()=>reply('不应显示'),()=>reply(JSON.stringify({verdict:'DEFECT',confidence:.98,
      evidenceIds:[],reason:'与任务要求冲突'})),()=>reply('强模型完成')])
    const chunks=await collect(f.controller.stream({...f.options,reasoningEffort:'rr:escalation'}))
    assert.deepEqual(chunks.filter(c=>c.type==='text-delta').map(c=>c.text),['强模型完成'])
    assert.deepEqual(f.calls.map(call=>call.model),['small','judge','large'])
    const record=(await f.controller.history('native-session')).records[0]
    assert.deepEqual(record.calls.map((call:any)=>call.disposition),['discarded','consult','accepted'])
    assert.equal(record.calls[2].review_status,'takeover-unreviewed')
    assert.ok(record.decisions.some((row:any)=>row.reason==='escalation-defect'
      &&row.candidateCallId===record.calls[0].call_id&&row.candidateDisposition==='discarded'))
  }finally{await f.cleanup()}
})

test('Escalation v4 合格候选经一次 Judge 后原样释放',async()=>{
  const f=await fixture('escalation')
  try{
    const upgraded:PlanningConfig={...structuredClone(config),schemaVersion:'refractagent-planning-v4',
      defaultStrategy:'escalation',escalation:{initial:'small',takeover:'large',judge:{type:'llm',modelId:'judge'},
        stallConfirmations:2,threshold:.8,judgeTimeoutMs:30000,maxJudgeInputBytes:8000,
        maxExecutionOutputTokens:1024,maxJudgeOutputTokens:256}}
    f.setPlanning(upgraded)
    f.setReplies([()=>reply('候选完成'),()=>reply(JSON.stringify({verdict:'PROCEED',confidence:.95,
      evidenceIds:[],reason:'符合任务要求'}))])
    const chunks=await collect(f.controller.stream({...f.options,reasoningEffort:'rr:escalation'}))
    assert.deepEqual(chunks.filter(c=>c.type==='text-delta').map(c=>c.text),['候选完成'])
    assert.deepEqual(f.calls.map(call=>call.model),['small','judge'])
  }finally{await f.cleanup()}
})

test('切换策略当前轮保持冻结，新轮重新分类；取消不释放候选',async()=>{
  const f=await fixture('static')
  try{
    await collect(f.controller.stream(f.options))
    f.setStrategy('task')
    await collect(f.controller.stream({...f.options,reasoningEffort:'rr:task'}))
    assert.equal(f.calls.length,2)
    f.events.push({type:'step/start',data:{turn:2,step:1}})
    f.setReplies([()=>reply('{"p_solve":1,"capability_boundary":"supported"}'),()=>reply('完成')])
    await collect(f.controller.stream({...f.options,reasoningEffort:'rr:task'}))
    assert.equal(f.calls.length,4)
    f.events.push({type:'step/start',data:{turn:3,step:1}})
    f.setStrategy('advisor')
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
    assert.deepEqual((await adapter.resolveModel('refractagent','planning')).reasoning?.efforts.map(e=>e.id),
      ['rr:stage','rr:task','rr:composite','rr:advisor','rr:escalation','rr:static'])
    const original=[{role:'assistant',source:{kind:'model',provider:'other',model:'old'},
      content:[{type:'text',text:'历史'}]}]
    assert.deepEqual(planningMessages(original),original)
    const legacy=[{role:'assistant',source:{kind:'model',provider:'refractagent',model:'planning',
      replayState:{response:{refractPlanning:{version:1,provider:'refract-fixture',model:'small'}}}},
      content:[{type:'text',text:'离线验收历史'}]}]
    assert.deepEqual(planningMessages(legacy)[0].source,
      {kind:'model',provider:'refract-fixture',model:'small'})
    assert.throws(()=>planningMessages([{...original[0],source:{kind:'model',provider:'refractagent',model:'auto'}}]),/真实来源/)
  }finally{await f.cleanup()}
})

test('媒体路线优先复用 apiKeyEnv，并支持 DSH provider 登录记录',async()=>{
  const f=await fixture()
  try{
    const references:string[]=[]
    f.ctx.credentials.resolve=async reference=>{references.push(reference);return {value:'secret'}}
    f.setProviderBaseURL('ark','https://ark.cn-beijing.volces.com/api/plan/v3')
    const settings=f.ctx.settings?.get?.('llm-pi-ai') as any
    settings.providers.ark.apiKeyEnv='ARK_PLAN_KEY'
    assert.equal(await f.controller.mediaCredential('ark'),'secret')
    delete settings.providers.ark.apiKeyEnv
    assert.equal(await f.controller.mediaCredential('ark'),'secret')
    assert.deepEqual(references,['ARK_PLAN_KEY','llm-pi-ai/ark'])
  }finally{await f.cleanup()}
})

test('宿主容量经 Python 模型资料查询核对，参考价格不冒充实际计费',async()=>{
  const f=await fixture()
  try{
    f.ctx.llm.resolveModelInfo=async()=>({provider:'deepseek-official',id:'deepseek-flash',name:'DeepSeek Flash',
      context:{contextWindow:64000},defaultMaxTokens:4096})
    const verified=await f.controller.metadata('deepseek-official','deepseek-flash','USD')
    assert.deepEqual(verified.capacity,{contextWindow:64000,maxOutputTokens:4096})
    assert.ok(verified.pricing.inputPer1k>0)
    const direct=await f.controller.metadata('deepseek-official','deepseek-flash','AUTO')
    assert.equal(direct.billingUnit,'CNY')
    assert.ok(direct.pricing.inputPer1k>0)
    assert.equal(direct.sources.pricing,'https://api-docs.deepseek.com/zh-cn/quick_start/pricing')
    const unknown=await f.controller.metadata('ark','minimax-m3','CNY')
    assert.equal(unknown.pricing,null)
  }finally{await f.cleanup()}
})

test('Task 单一图片候选把原生图片引用送达底层模型且不增加 Judge 调用',async()=>{
  const f=await fixture('task')
  try{
    const taskConfig:PlanningConfig={schemaVersion:'refractagent-planning-v3',enabled:true,
      defaultStrategy:'task',billingUnit:'CNY',maxProductionCostByUnit:{CNY:10},
      models:[{id:'vision',provider:'fake',model:'vision',contextWindow:32000,maxOutputTokens:1024,
        inputPer1k:.001,outputPer1k:.002,billingUnit:'CNY',deployment:'local',
        capabilities:{mainExecutor:true,toolCalling:'verified',modalities:{imageInput:'connected'},
          formats:{imageInput:['image/png']}}}],roles:{},task:{pool:['vision'],fallback:'vision',
          judge:{type:'llm',modelId:'vision'},threshold:.8,maxInputChars:12000}}
    f.setPlanning(taskConfig)
    f.setReplies([()=>reply('看到了图片')])
    const image={type:'image',attachment:{attachmentId:'sha256:image',mediaType:'image/png',bytes:3,width:1,height:1}}
    await collect(f.controller.stream({...f.options,reasoningEffort:'rr:task',messages:[
      {role:'user',content:[{type:'text',text:'描述图片'},image] as any}]}))
    assert.equal(f.calls.length,1)
    assert.deepEqual((f.calls[0].messages[0].content as any[])[1],image)
    const record=(await f.controller.history('native-session')).records[0]
    assert.equal(record.decisions[0].judgeDecision.reason,'single-eligible-candidate')
    assert.equal(record.decisions[0].callId,record.calls[0].call_id)
  }finally{await f.cleanup()}
})

test('同一任务的 AFP 判别与 CNY 现金执行分账展示，不生成跨单位总价',async()=>{
  const f=await fixture('task')
  try{
    const saved:PlanningConfig=structuredClone(config)
    saved.schemaVersion='refractagent-planning-v2'
    saved.billingUnit='USD'
    saved.maxProductionCostByUnit={AFP:10,CNY:10}
    saved.models![2].billingUnit='AFP'
    f.setPlanning(saved)
    f.setReplies([()=>reply('{"p_solve":0.8,"capability_boundary":"supported"}'),()=>reply('完成')])
    await collect(f.controller.stream(f.options))
    const record=(await f.controller.history('native-session')).records[0]
    assert.equal(record.billingUnit,null)
    assert.equal(record.costs.production,null)
    assert.ok(record.costsByUnit.AFP.production>0)
    assert.ok(record.costsByUnit.CNY.production>0)
    assert.deepEqual(record.calls.map((call:any)=>call.billing_unit),['AFP','CNY'])
  }finally{await f.cleanup()}
})

test('新 Ark Agent Plan 路线可自动识别 AFP 单位',async()=>{
  const f=await fixture()
  try{
    f.setProviderBaseURL('ark','https://ark.cn-beijing.volces.com/api/plan/v3')
    f.ctx.llm.resolveModelInfo=async(provider,model)=>({provider,id:model,name:model,
      context:{contextWindow:64000},defaultMaxTokens:4096})
    const metadata=await f.controller.metadata('ark','deepseek-v4-pro','AUTO')
    assert.equal(metadata.billingUnit,'AFP')
    assert.equal(metadata.pricing.inputPer1k,.55)
  }finally{await f.cleanup()}
})

test('Ark Agent Plan 将旧 CNY 价格迁移到 AFP 账本并要求 AFP 预算',async()=>{
  const f=await fixture()
  try{
    f.setProviderBaseURL('ark','https://ark.cn-beijing.volces.com/api/plan/v3')
    const saved:PlanningConfig=structuredClone(config)
    saved.billingUnit='CNY'
    saved.models![0]={...saved.models![0],provider:'ark',model:'deepseek-v4-pro',
      inputPer1k:.55,outputPer1k:.55}
    f.setPlanning(saved)
    f.ctx.llm.resolveModelInfo=async(provider,model)=>({provider,id:model,name:model,
      context:{contextWindow:64000},defaultMaxTokens:4096,
      reasoning:{efforts:[{id:'low',name:'Low'}],defaultEffort:'low'}})
    const report=await f.controller.preview()
    const staticRoute=report.strategies.find((row:any)=>row.id==='static')
    assert.equal(staticRoute.available,false)
    assert.match(staticRoute.issues.join(' '),/缺少 AFP 生产预算/)
    await assert.rejects(collect(f.controller.stream(f.options)),/缺少 AFP 生产预算/)
    assert.equal(f.calls.length,0)
  }finally{await f.cleanup()}
})

test('宿主 finish 错误保留未知用量预留，并显示原始失败原因',async()=>{
  const f=await fixture()
  try{
    f.setReplies([()=>({*[Symbol.iterator](){
      yield {type:'finish',reason:{kind:'error',failure:{code:'PROVIDER_FAILURE',message:'模型请求被拒绝'}}} as StreamChunk
    }})])
    await assert.rejects(()=>collect(f.controller.stream(f.options)),/PROVIDER_FAILURE.*模型请求被拒绝/)
    const history=await f.controller.history('native-session')
    assert.equal(history.records[0].calls[0].status,'unknown-usage')
    assert.equal(history.records[0].costs.production>0,true)
  }finally{await f.cleanup()}
})

test('已保存配置缺少价格时，预检和真实派发使用系统核对的模型资料',async()=>{
  const f=await fixture()
  try{
    const saved:PlanningConfig=structuredClone(config)
    saved.billingUnit='CNY'
    saved.models![0]={id:'small',provider:'deepseek-official',model:'deepseek-flash',deployment:'local'}
    f.setPlanning(saved)
    f.ctx.llm.resolveModelInfo=async(provider,model)=>({provider,id:model,name:model,
      context:{contextWindow:64000},defaultMaxTokens:4096})
    const report=await f.controller.preview()
    assert.equal(report.strategies.find((row:any)=>row.id==='static').available,true)
    assert.equal(saved.models![0].inputPer1k,undefined)
    await collect(f.controller.stream(f.options))
    assert.equal(f.calls[0].provider,'deepseek-official')
    assert.equal(f.calls[0].model,'deepseek-flash')
    const history=await f.controller.history('native-session')
    assert.ok(history.records[0].costs.production>0)
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
