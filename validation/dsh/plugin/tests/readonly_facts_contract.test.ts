import assert from 'node:assert/strict'
import test from 'node:test'
import { spawn } from 'node:child_process'
import { createHash } from 'node:crypto'
import { mkdtemp,writeFile,rm,access } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'
import { configure,type AgentContext,type ModelOptions } from '../dist/agent-provider.js'
import { PlanningController,planningMessages } from '../dist/planning-routing.js'
import { registerReadonlyFactTools } from '../dist/readonly-facts.js'
import type { SpawnSpec,StreamChunk } from '../dist/contracts.js'

type Json=Record<string,any>
const root=resolve('../../..')
const hash=(value:string)=>createHash('sha256').update(value).digest('hex')
const args={path:'visible.py',symbol:'f',definitionLine:null}
async function fixture(){
  const workspace=await mkdtemp(resolve(tmpdir(),'rr-facts-'))
  const text='def f():\r\n    return ("文😀", 2)\r\n'
  await writeFile(resolve(workspace,'visible.py'),text)
  await writeFile(resolve(workspace,'json.py'),`from pathlib import Path\nPath(${JSON.stringify(resolve(workspace,'must-not-execute'))}).write_text('executed')\nraise RuntimeError('不应导入仓库模块')\n`)
  const manifest=JSON.stringify({schemaVersion:'readonly-facts-host-v1',root:'.',files:{'visible.py':hash(text)}})
  await writeFile(resolve(workspace,'manifest.json'),manifest)
  const tools=new Map<string,Json>(),specs:SpawnSpec[]=[],calls:Json[]=[],policies:Json[]=[],disposers:Array<()=>void>=[]
  const events:Array<{type:string;data:Record<string,unknown>}>=[{type:'step/start',data:{turn:1,step:1}}]
  const agent={id:'host-agent',session:{header:{id:'host-session',cwd:workspace},events,append(){}}}
  let answer='完成',nextTool=true,overrideChunks:StreamChunk[]|undefined
  const tool={type:'tool-call',id:'fact-call',name:'refract_python_structure',arguments:JSON.stringify(args)}
  const ctx:AgentContext={
    agents:{requireInitiator:()=>agent},credentials:{async describe(){return {configured:false}},async resolve(){throw new Error('事实工具不能读取凭证')}},
    tools:{register(value:unknown){const item=value as Json;tools.set(item.name,item)},async execute(){throw new Error('Router不能执行宿主工具')}},
    effect(setup){const done=setup();if(typeof done==='function')disposers.push(done as ()=>void)},
    sandboxPolicy:{resolve:()=>({mode:'workspace-write',workspaceRoot:workspace})},
    sandbox:{confine(argv,policy){policies.push(policy);return {argv,enforcement:'full'}}},
    subprocess:{async resolveExecutable(){return resolve(root,'.venv/bin/python')},spawn(spec){
      specs.push(spec)
      const child=spawn(spec.argv[0],spec.argv.slice(1),{cwd:spec.cwd,env:spec.env,stdio:'pipe',signal:spec.signal})
      let out='',err='';child.stdout.setEncoding('utf8');child.stderr.setEncoding('utf8')
      child.stdout.on('data',(text:string)=>{out+=text});child.stderr.on('data',(text:string)=>{err+=text})
      child.on('error',()=>{})
      const done=new Promise<{exitCode:number|null;signal:string|null}>(resolve=>child.once('close',(exitCode,signal)=>resolve({exitCode,signal})))
      return {stdin:child.stdin,stdout:child.stdout,done,waitForExit:()=>done,terminate:()=>{child.kill()},collected:{
        stdout:{readFrom:()=>({text:out,lossy:typeof spec.stdio.stdout==='object'&&Buffer.byteLength(out)>spec.stdio.stdout.maxBytes})},
        stderr:{readFrom:()=>({text:err,lossy:Buffer.byteLength(err)>spec.stdio.stderr.maxBytes})}}}
    }},
    llm:{registerAdapter(){},async *stream(options){
      calls.push(options)
      if(nextTool){nextTool=false;yield {type:'block-end',index:0,block:tool}}
      else if(overrideChunks)yield* overrideChunks
      else {yield {type:'text-delta',index:0,text:answer};yield {type:'block-end',index:0,block:{type:'text',text:answer}}}
      yield {type:'usage',usage:{inputTokens:100,outputTokens:20}}
      yield {type:'finish',reason:{kind:calls.length===1?'tool-calls':'stop'}}
    }}
  }
  let config=configure({pythonExecutable:resolve(root,'.venv/bin/python'),runsDir:resolve(workspace,'runs'),
    factTools:{enabled:true,manifestPath:'manifest.json',manifestSha256:hash(manifest)},
    planningRouting:{schemaVersion:'refractagent-planning-v1',enabled:true,defaultStrategy:'static',maxProductionCost:10,
      models:[{id:'small',provider:'fake',model:'small',contextWindow:32000,maxOutputTokens:1024,inputPer1k:.001,outputPer1k:.002,deployment:'local'}],
      roles:{efficient:'small'}}})
  const host=registerReadonlyFactTools(ctx,()=>config)!
  const controller=new PlanningController(ctx,()=>config,undefined,undefined,host)
  const options:ModelOptions={provider:'refractagent',model:'planning',sessionId:'host-session',reasoningEffort:'rr:static',
    messages:[{role:'user',content:[{type:'text',text:'用只读工具核对返回结构'}]}],
    tools:[...tools.values()].map(({name,description,parameters})=>({name,description,parameters}))}
  return {workspace,tools,host,controller,options,agent,events,tool,calls,specs,policies,
    setAnswer(value:string){answer=value},disable(){config=configure({...config,factTools:{...config.factTools!,enabled:false}})},
    setChunks(value:StreamChunk[]){overrideChunks=value},
    async cleanup(){for(const dispose of disposers)dispose();controller.rpc.dispose();await new Promise(r=>setTimeout(r,50));await rm(workspace,{recursive:true,force:true})}}
}
async function collect(stream:AsyncIterable<Json>){const chunks=[];for await(const chunk of stream)chunks.push(chunk);return chunks}

test('默认不登记事实工具；缺少宿主工具能力明确拒绝',()=>{
  const config=configure()
  assert.equal(registerReadonlyFactTools({} as AgentContext,()=>config),undefined)
  const enabled=configure({factTools:{enabled:true,manifestPath:'manifest.json',manifestSha256:'a'.repeat(64)}})
  assert.throws(()=>registerReadonlyFactTools({} as AgentContext,()=>enabled),/未接通/)
})

test('DSH模拟循环执行真实只读Python工具，校验绑定实际最终候选且不追加模型',async()=>{
  const f=await fixture()
  try{
    const first=await collect(f.controller.stream(f.options))
    const finish=first.find(c=>c.type==='finish') as Json
    const value=await f.tools.get('refract_python_structure')!.execute(args,{agent:f.agent,signal:new AbortController().signal})
    const body=JSON.parse(value.modelText)
    const fact=body.facts.find((v:Json)=>v.kind==='return-expression')
    assert.equal(fact.span.quote,'return ("文😀", 2)')
    assert.equal(value.visibleUtf8Bytes,Buffer.byteLength(value.modelText))
    const answer=JSON.stringify({answer:{arity:2},structuralAssertions:[{
      factId:fact.factId,field:'fixedTupleArity',answerPointer:'/answer/arity'}]})
    f.setAnswer(answer);f.events.push({type:'step/start',data:{turn:1,step:2}})
    const second=await collect(f.controller.stream({...f.options,messages:[...f.options.messages,
      {role:'assistant',content:[f.tool],source:{kind:'model',provider:'refractagent',model:'planning',replayState:finish.replayState}},
      {role:'user',content:[{type:'tool-result',toolCallId:'fact-call',content:[{type:'text',text:value.modelText}]}]}]}))
    const final=second.find(c=>c.type==='finish') as Json
    const envelope=final.replayState.response.refractPlanning
    assert.equal(envelope.factVerification.allBoundFieldsSupported,true)
    assert.equal(envelope.factVerification.wholeTaskQualityProven,false)
    const history=await f.controller.history('host-session')
    assert.equal(history.records[0].calls.length,2)
    assert.equal(envelope.factVerification.candidateId,history.records[0].calls.at(-1).call_id)
    assert.equal(f.calls.length,2)
    const sourceCalls=f.specs.filter(s=>s.argv.includes('fact-tool'))
    assert.equal(sourceCalls.length,2)
    assert.ok(sourceCalls.every(s=>s.env.PYTHONDONTWRITEBYTECODE==='1'&&!Object.keys(s.env).some(k=>/API_KEY|TOKEN|SECRET/.test(k))))
    assert.equal(f.policies.filter(p=>p.mode==='read-only').length,2)
    assert.ok(sourceCalls.every(s=>s.argv.includes('-I')&&s.argv.includes('-B')))
    await assert.rejects(()=>access(resolve(f.workspace,'must-not-execute')))
    const replayed=planningMessages([{role:'assistant',content:[{type:'text',text:answer}],source:{
      kind:'model',provider:'refractagent',model:'planning',replayState:final.replayState}}])
    assert.ok(!JSON.stringify(replayed).includes('allBoundFieldsSupported'))
    assert.equal(await f.host.verifyCandidate({session:'host-session',agent:'host-agent',turn:2},'new-call',
      {content:answer,toolCalls:[],finishReason:'stop'},f.agent,new AbortController().signal),undefined)
  }finally{await f.cleanup()}
})

test('模型参数不能扩大固定范围；宿主禁用或配置变更后不读取来源',async()=>{
  const f=await fixture()
  try{
    const source=f.tools.get('refract_python_structure')!
    const result=await source.execute({...args,path:'hidden-evaluation.py'},{agent:f.agent,signal:new AbortController().signal})
    assert.equal(JSON.parse(result.modelText).status,'denied')
    const before=f.specs.length;f.disable()
    await assert.rejects(()=>source.execute(args,{agent:f.agent,signal:new AbortController().signal}),/未启用/)
    assert.equal(f.specs.length,before)
    assert.equal(f.calls.length,0)
  }finally{await f.cleanup()}
})

for(const scenario of ['增量与结束块不同','部分块仅有结束块'])test('实际候选绑定：'+scenario,async()=>{
  const f=await fixture()
  try{
    const first=await collect(f.controller.stream(f.options))
    const finish=first.find(c=>c.type==='finish') as Json
    const value=await f.tools.get('refract_python_structure')!.execute(args,{agent:f.agent,signal:new AbortController().signal})
    const fact=JSON.parse(value.modelText).facts.find((v:Json)=>v.kind==='return-expression')
    const body={answer:{arity:2},structuralAssertions:[{factId:fact.factId,field:'fixedTupleArity',answerPointer:'/answer/arity'}]}
    const good=JSON.stringify(body),bad=JSON.stringify({...body,answer:{arity:3}})
    let delivered=good
    if(scenario==='增量与结束块不同'){
      delivered=bad
      f.setChunks([{type:'text-delta',index:0,text:good},{type:'block-end',index:0,block:{type:'text',text:bad}}])
    }else{
      const split=Math.floor(good.length/2)
      f.setChunks([{type:'text-delta',index:0,text:good.slice(0,split)},
        {type:'block-end',index:0,block:{type:'text',text:good.slice(0,split)}},
        {type:'block-end',index:1,block:{type:'text',text:good.slice(split)}}])
    }
    f.events.push({type:'step/start',data:{turn:1,step:2}})
    const chunks=await collect(f.controller.stream({...f.options,messages:[...f.options.messages,
      {role:'assistant',content:[f.tool],source:{kind:'model',provider:'refractagent',model:'planning',replayState:finish.replayState}},
      {role:'user',content:[{type:'tool-result',toolCallId:'fact-call',content:[{type:'text',text:value.modelText}]}]}]}))
    const last=chunks.find(c=>c.type==='finish') as Json
    const report=last.replayState.response.refractPlanning.factVerification
    assert.equal(report.allBoundFieldsSupported,scenario==='部分块仅有结束块')
    const record=(await f.controller.history('host-session')).records[0]
    assert.equal(record.calls.at(-1).output_sha256,hash(delivered))
    assert.equal(f.calls.length,2)
  }finally{await f.cleanup()}
})
