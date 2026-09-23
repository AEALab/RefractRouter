/** 已安装 DSH 的真实 LlmRuntime、Session、ToolRuntime 与已构建插件的零网络验收。 */
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
if(!process.argv[2])throw new Error('请指定 DSH node_modules 目录')
const base=resolve(process.argv[2],'@deepseek-ai')
const load=(name:string)=>import(pathToFileURL(resolve(base,name,'lib/index.js')).href)
const {Context}=await load('cordis')
const {Session}=await load('dsh-session')
const {ToolRuntime}=await load('dsh-tools')
const {SystemPrompt}=await load('dsh-system-prompt')
const {LlmRuntime}=await load('dsh-llm')
const {apply:fixture}=await import('./planning-fixture.ts')
const {createAdapter,configure}=await import('../dist/agent-provider.js')
const ctx=new Context()
new SystemPrompt(ctx,{})
new ToolRuntime(ctx)
new LlmRuntime(ctx)
fixture(ctx)
const session=Session.create('refract-planning-sdk-fixture')
const agent={id:session.header.id,session,ctx}
const root=resolve(import.meta.dirname,'../../../..')
const runs=await mkdtemp(resolve(tmpdir(),'refract-planning-sdk-'))
const executable=process.argv[3]??resolve(root,'.venv/bin/python')
const disposals:(()=>void)[]=[]
const context:any={
  llm:ctx.llm,tools:ctx.tools,agents:{requireInitiator:()=>agent},
  effect(setup:()=>()=>void){disposals.push(setup())},
  credentials:{async describe(){return {configured:false}},async resolve(){throw new Error('不能读取凭证')}},
  sandboxPolicy:{resolve:()=>({mode:'workspace-write',workspaceRoot:tmpdir()})},
  sandbox:{confine:(argv:string[])=>({argv,enforcement:'full'})},
  subprocess:{
    async resolveExecutable(){return executable},
    spawn(spec:any){
      const p=spawn(spec.argv[0],spec.argv.slice(1),{cwd:spec.cwd,env:spec.env,stdio:'pipe',signal:spec.signal})
      p.on('error',()=>{})
      const done=new Promise(res=>p.once('exit',(exitCode,signal)=>res({exitCode,signal})))
      return {stdin:p.stdin,stdout:p.stdout,done,waitForExit:()=>done,terminate:()=>p.kill(),collected:{}}
    }
  }}
const config=configure({pythonExecutable:executable,runsDir:runs,planningRouting:{
  schemaVersion:'refractagent-planning-v1',enabled:true,maxProductionCost:10,defaultStrategy:'stage',
  models:['small','large'].map(id=>({id,provider:'refract-fixture',model:id,
    contextWindow:1000000,maxOutputTokens:1024,inputPer1k:.001,outputPer1k:.002,deployment:'local'})),
  roles:{efficient:'small',capable:'large'}}})
const adapter=createAdapter(context,()=>config)
const messages:any[]=[{id:'user',role:'user',source:{kind:'user'},content:[{type:'text',text:'完成两轮离线工具验收'}]}]
let tools=0,steps=0
try{
  for(let i=1;i<=3;i++){
    session.append('step/start',{turn:1,step:i})
    const chunks:any[]=[]
    for await(const c of adapter.stream({provider:'refractagent',model:'planning',reasoningEffort:'rr:stage',
      sessionId:session.header.id,messages,tools:ctx.tools.schemas(),signal:new AbortController().signal}))chunks.push(c)
    const blocks=chunks.filter(c=>c.type==='block-end').map(c=>c.block)
    const finish=chunks.find(c=>c.type==='finish')
    assert.ok(finish)
    const assistant={id:'assistant-'+i,role:'assistant',source:{kind:'model',provider:'refractagent',
      model:'planning',replayState:finish.replayState},content:blocks}
    messages.push(assistant)
    session.append('assistant/message',{turn:1,step:i,message:assistant,stream:[]},{surfaceOp:'append'})
    for(const call of blocks.filter((b:any)=>b.type==='tool-call')){
      session.append('tool/call',{turn:1,step:i,callId:call.id,name:call.name,arguments:call.arguments})
      const result=await ctx.tools.execute({callId:call.id,name:call.name,arguments:JSON.parse(call.arguments),
        agent,signal:new AbortController().signal})
      assert.equal(result.isError,false)
      assert.deepEqual(result.content,[{type:'text',text:'离线工具已完成'}])
      const message={id:'tool-'+i,role:'user',source:{kind:'tool',callId:call.id},
        content:[{type:'tool-result',toolCallId:call.id,content:result.content,isError:result.isError}]}
      messages.push(message)
      session.append('tool/result',{turn:1,step:i,message},{surfaceOp:'append'})
      tools++
    }
    steps++
  }
  assert.equal(tools,2)
  assert.equal(steps,3)
  assert.match(messages.at(-1).content[0].text,/两轮原生工具/)
  assert.equal(session.snapshotEvents().filter((e:any)=>e.type==='tool/result').length,2)
  console.log(JSON.stringify({status:'pass',host:'DSH LlmRuntime + Session + ToolRuntime',
    modelRequests:3,nativeToolExecutions:2,networkModelCalls:0,dagCreated:false}))
}finally{
  for(const dispose of disposals)dispose()
  await new Promise(r=>setTimeout(r,50))
  await rm(runs,{recursive:true,force:true})
}
