/** Issue #200：真实 DSH 运行时、真实 Python 选模账本，双进程禁网的专家工具验收。 */
import assert from 'node:assert/strict'
import { spawn, execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import net from 'node:net'
import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import http from 'node:http'
import https from 'node:https'
const [modules,executable,output,strategy,flag,scenario='clean']=process.argv.slice(2)
if(!modules||!executable||!output||!['static','stage'].includes(strategy)||flag!=='--enable-node-tools'
  ||!['clean','task-failures','semantic-error'].includes(scenario))
  throw new Error('用法：node check-node-tools.ts <DSH node_modules> <Python> <新证据目录> static|stage --enable-node-tools [clean|task-failures|semantic-error]')
await mkdir(output,{recursive:false}) // 证据不得覆盖或复用。
const base=resolve(modules,'@deepseek-ai')
const load=(name:string)=>import(pathToFileURL(resolve(base,name,'lib/index.js')).href)
const {Context}=await load('cordis')
const {Session}=await load('dsh-session')
const {ToolRuntime}=await load('dsh-tools')
const {SystemPrompt}=await load('dsh-system-prompt')
const {LlmRuntime}=await load('dsh-llm')
const {PlanningController}=await import('../dist/planning-routing.js')
const {createAdapter,configure}=await import('../dist/agent-provider.js')
const {registerExperimentalNodeTools}=await import('../dist/node-tools.js')
const {ToolEvidenceCapture}=await import('../dist/tool-evidence.js')
let networkAttempts=0,requests=0
const denyNetwork=()=>{networkAttempts++;throw new Error('离线验收禁止网络调用')}
globalThis.fetch=denyNetwork as typeof fetch
net.Socket.prototype.connect=denyNetwork as typeof net.Socket.prototype.connect
http.request=denyNetwork as typeof http.request
https.request=denyNetwork as typeof https.request
const guard=resolve(output,'network-guard')
await mkdir(guard)
await writeFile(resolve(guard,'sitecustomize.py'),`import socket
from pathlib import Path
def deny(*args, **kwargs):
    Path(${JSON.stringify(resolve(guard,'attempted'))}).write_text('网络访问被拒绝')
    raise RuntimeError('离线验收禁止网络调用')
socket.socket.connect = deny
socket.socket.connect_ex = deny\nsocket.getaddrinfo = deny\nfrom refractrouter.schemas import TaskDAG\ndef forbid_dag(*args, **kwargs):\n    Path(${JSON.stringify(resolve(guard,'dag-attempted'))}).write_text('禁止创建 DAG')\n    raise RuntimeError('本验收禁止创建 DAG')\nTaskDAG.__init__ = forbid_dag\nPath(${JSON.stringify(resolve(guard,'ready'))}).write_text('socket-dns-dag-guards-active')
`)
const root=resolve(import.meta.dirname,'../../../..')
const files=['src/refractrouter/node_tools.py','src/refractrouter/planning_runtime.py',
  'validation/dsh/plugin/src/node-tools.ts','validation/dsh/plugin/src/planning-routing.ts',
  'validation/dsh/plugin/src/agent-provider.ts','validation/dsh/plugin/scripts/check-node-tools.ts',
  'uv.lock','validation/dsh/plugin/package-lock.json']
const sourceHashes:Record<string,string>={}
for(const file of files)sourceHashes[file]=createHash('sha256').update(await readFile(resolve(root,file))).digest('hex')
const cli=JSON.parse(await readFile(resolve(modules,'../package.json'),'utf8'))
await writeFile(resolve(output,'provenance.json'),JSON.stringify({sourceHashes,hostVersion:cli.version,
  baseCommit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),
  sourceState:'工作区源码，按 SHA-256 核对',nodeVersion:process.version,networkGuards:['Node socket/http/fetch','Python socket/DNS']},null,2))
const ctx=new Context()
new SystemPrompt(ctx,{})
new ToolRuntime(ctx)
new LlmRuntime(ctx)
const capture=new ToolEvidenceCapture()
ctx.on('tools/result',(exec:any,result:any)=>capture.observe(exec,result))
let probeExecutions=0
if(scenario==='task-failures')ctx.tools.register({name:'bash',description:'离线夹具：仅执行固定的非零退出探针',
  parameters:{type:'object',properties:{command:{type:'string',enum:['fixture-exit-7']}},required:['command'],additionalProperties:false},
  output:{schema:{type:'object'},render:(_args:unknown,value:any)=>[{type:'text',text:JSON.stringify(value)}]},
  async execute(args:any){
    assert.deepEqual(args,{command:'fixture-exit-7'})
    probeExecutions++
    const child=spawn(executable,['-c','import sys; sys.exit(7)'],{cwd:resolve(output),
      env:{...process.env,PYTHONPATH:guard},stdio:'ignore'})
    const exitCode=await new Promise<number|null>((done,reject)=>{child.once('error',reject);child.once('exit',done)})
    assert.equal(exitCode,7)
    return {kind:'foreground',exitCode,signal:null,timedOut:false,aborted:false}
  }})
const expectedArtifact=scenario==='semantic-error'?'项目总价为 99 元。':'项目总价为 100 元。'
const info=(provider:string,model:string)=>({provider,id:model,name:'节点工具离线模型 '+model,
  inputModalities:['text'],context:{contextWindow:1000000},defaultMaxTokens:1024})
const fixture:any={
  providerInfo:(provider:string)=>({id:provider,name:'节点工具离线验收'}),
  providerRetryPolicy:()=>({mode:'normal',maxRetries:0,retryableCodes:[]}),
  listModels:async(provider:string)=>['small','large'].map(m=>info(provider,m)),
  resolveModel:async(provider:string,model:string)=>info(provider,model),
  prepareCall:async(provider:string,model:string)=>({model:info(provider,model),stream:fixture.stream}),
  async *stream(options:any){
    requests++
    let block:any
    const results=options.messages.flatMap((m:any)=>Array.isArray(m.content)?m.content:[])
      .filter((b:any)=>b.type==='tool-result')
    const expertCount=results.filter((b:any)=>b.toolCallId.startsWith('node-')).length
    const probeCount=results.filter((b:any)=>b.toolCallId.startsWith('probe-')).length
    if(options.tools?.length&&scenario==='task-failures'&&probeCount<2){
      block={type:'tool-call',id:'probe-'+probeCount,name:'bash',arguments:JSON.stringify({command:'fixture-exit-7'})}
    }else if(options.tools?.some((t:any)=>t.name==='refract_expert')&&expertCount<3){
      block={type:'tool-call',id:'node-'+expertCount,name:'refract_expert',arguments:JSON.stringify({
        intent:['analyze','check','synthesize'][expertCount],task:'核对项目总价',context:'项目总价为 100 元。'})}
    }else{
      block={type:'text',text:options.tools?.length?'已完成三次专家工具调用；'+expectedArtifact:JSON.stringify({
        artifact:expectedArtifact,quotes:['总价为 100 元'],limitations:['仅核对给定材料']})}
    }
    yield {type:'block-start',index:0,blockType:block.type}
    if(block.type==='tool-call')yield {type:'tool-call-delta',index:0,id:block.id,name:block.name,argumentsDelta:block.arguments}
    else yield {type:'text-delta',index:0,text:block.text}
    yield {type:'block-end',index:0,block}
    yield {type:'usage',usage:{inputTokens:100,outputTokens:30}}
    yield {type:'finish',reason:{kind:block.type==='tool-call'?'tool-calls':'stop'}}
  }}
ctx.llm.registerAdapter(['refract-node-fixture'],fixture)
const session=Session.create('refract-node-tools-'+strategy+'-'+scenario)
const agent={id:session.header.id,session,ctx}
const disposals:Array<()=>void>=[]
const context:any={llm:ctx.llm,tools:ctx.tools,agents:{requireInitiator:()=>agent},
  effect(setup:()=>()=>void){disposals.push(setup())},
  credentials:{async describe(){return {configured:false}},async resolve(){throw new Error('离线夹具禁止读取凭证')}},
  sandboxPolicy:{resolve:()=>({mode:'workspace-write',workspaceRoot:resolve(output)})},
  sandbox:{confine:(argv:string[])=>({argv,enforcement:'full'})},
  subprocess:{async resolveExecutable(){return executable},spawn(spec:any){
    const child=spawn(spec.argv[0],spec.argv.slice(1),{cwd:spec.cwd,
      env:{...spec.env,PYTHONPATH:guard},stdio:'pipe',signal:spec.signal})
    child.on('error',()=>{})
    const done=new Promise(res=>child.once('exit',(exitCode,signal)=>res({exitCode,signal})))
    return {stdin:child.stdin,stdout:child.stdout,done,waitForExit:()=>done,terminate:()=>child.kill(),collected:{}}
  }}}
const config=configure({pythonExecutable:executable,runsDir:'evidence',planningRouting:{
  schemaVersion:'refractagent-planning-v1',enabled:true,maxProductionCost:10,maxCalls:scenario==='task-failures'?9:7,defaultStrategy:strategy as any,
  models:['small','large'].map(id=>({id,provider:'refract-node-fixture',model:id,contextWindow:1000000,
    maxOutputTokens:1024,inputPer1k:.001,outputPer1k:.002,deployment:'local'})),
  roles:{efficient:'small',capable:'large'}}})
const planning=new PlanningController(context,()=>config,undefined,capture)
const adapter=createAdapter(context,()=>config,capture,planning)
const messages:any[]=[{id:'user',role:'user',source:{kind:'user'},content:[{type:'text',text:'核对总价并完成三次专家分析'}]}]
try{
  const dispose=await registerExperimentalNodeTools(context,planning,{enabled:true},()=>ctx.tools.schemas())
  disposals.push(dispose)
  let tools=0
  for(let step=1;step<=(scenario==='task-failures'?6:4);step++){
    session.append('step/start',{turn:1,step})
    const chunks:any[]=[]
    for await(const chunk of adapter.stream({provider:'refractagent',model:'planning',reasoningEffort:'rr:'+strategy,
      sessionId:session.header.id,messages,tools:ctx.tools.schemas(),signal:new AbortController().signal}))chunks.push(chunk)
    const blocks=chunks.filter(c=>c.type==='block-end').map(c=>c.block)
    const finish=chunks.find(c=>c.type==='finish')
    assert.ok(finish)
    const assistant={id:'assistant-'+step,role:'assistant',source:{kind:'model',provider:'refractagent',
      model:'planning',replayState:finish.replayState},content:blocks}
    messages.push(assistant)
    session.append('assistant/message',{turn:1,step,message:assistant,stream:[]},{surfaceOp:'append'})
    for(const call of blocks.filter((b:any)=>b.type==='tool-call')){
      session.append('tool/call',{turn:1,step,callId:call.id,name:call.name,arguments:call.arguments})
      const result=await ctx.tools.execute({callId:call.id,name:call.name,arguments:JSON.parse(call.arguments),
        agent,signal:new AbortController().signal})
      assert.equal(result.isError,false,JSON.stringify(result))
      const value=JSON.parse(result.content[0].text)
      if(call.name==='refract_expert'){
        assert.equal(value.toolCallId,call.id)
        assert.equal(value.artifact,expectedArtifact)
        tools++
      }else assert.equal(value.exitCode,7)
      const message={id:'tool-'+step,role:'user',source:{kind:'tool',callId:call.id},
        content:[{type:'tool-result',toolCallId:call.id,content:result.content,isError:result.isError}]}
      messages.push(message)
      session.append('tool/result',{turn:1,step,message},{surfaceOp:'append'})
    }
  }
  const history=await planning.rpc.request({op:'history',session:session.header.id})
  const runId=history.records[0].runId
  await planning.rpc.request({op:'end',runId})
  const record=await planning.rpc.request({op:'query',runId})
  assert.equal(tools,3)
  assert.equal(requests,scenario==='task-failures'?9:7)
  assert.equal(networkAttempts,0)
  assert.equal((await readdir(guard)).includes('attempted'),false)
  assert.equal((await readdir(guard)).includes('dag-attempted'),false)
  assert.equal(await readFile(resolve(guard,'ready'),'utf8'),'socket-dns-dag-guards-active')
  assert.equal((await readdir(resolve(output,'evidence/planning'))).length,1)
  assert.equal(record.status,'completed')
  assert.equal(record.calls.length,requests)
  assert.equal(record.calls.filter((c:any)=>c.purpose==='node-tool').length,3)
  assert.ok(record.calls.every((c:any)=>c.status==='billed'))
  assert.ok(record.nodeTools.invocations.every((i:any)=>i.status==='completed'))
  const events=session.snapshotEvents()
  assert.equal(events.filter((e:any)=>e.type==='tool/call').length,tools+probeExecutions)
  assert.equal(events.filter((e:any)=>e.type==='tool/result').length,tools+probeExecutions)
  const sum=record.calls.reduce((total:number,c:any)=>total+c.charged,0)
  assert.ok(Math.abs(record.costs.production-sum)<1e-10)
  assert.match(messages.at(-1).content[0].text,/已完成三次/)
  const models=record.calls.map((c:any)=>c.model_id)
  const switches=models.slice(1).filter((m:string,i:number)=>m!==models[i]).length
  const capableCalls=models.filter((m:string)=>m==='large').length
  assert.equal(probeExecutions,scenario==='task-failures'?2:0)
  if(strategy==='stage'&&scenario==='task-failures')assert.ok(capableCalls>=2)
  else assert.equal(capableCalls,0)
  const acceptance={status:'pass',strategy,scenario,modelsByCall:models,modelSwitchCount:switches,
    capableCalls,probeExecutions,semanticMismatchObserved:scenario==='semantic-error',protocol:'node-as-tool-v1-experimental',
    host:'DSH LlmRuntime + Session + ToolRuntime',fixtureModelRequests:requests,expertToolCalls:tools,
    networkAttempts,networkModelCalls:0,dagConstructionGuard:true,dagCreated:false,parentRunCount:1,sharedLedgerCalls:record.calls.length,
    simulatedCost:record.costs,realModelCost:0,qualityBenefitProven:false,nodeVersion:process.version,
    evidencePath:record.resultPath,scope:'离线契约验收，不证明任务质量、成本或时延收益'}
  await writeFile(resolve(output,'session-events.json'),JSON.stringify(events,null,2))
  await writeFile(resolve(output,'acceptance.json'),JSON.stringify(acceptance,null,2))
  console.log(JSON.stringify(acceptance))
}catch(error){
  await writeFile(resolve(output,'failure.json'),JSON.stringify({error:String(error),scenario,requests,networkAttempts},null,2))
  throw error
}finally{for(const dispose of disposals.reverse())dispose()}
