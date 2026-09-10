import assert from 'node:assert/strict'
import { PassThrough } from 'node:stream'
import test from 'node:test'
import { apply, configure, createAdapter, type AgentAdapter, type AgentContext } from '../dist/agent-provider.js'

function fixture(result: Record<string, unknown> = {}) {
  let adapter: AgentAdapter | undefined
  let credentials = 0
  const credentialReferences: string[] = []
  const spawns: Array<{ argv: string[]; env: Record<string,string>; input: () => string }> = []
  const ctx: AgentContext = {
    llm: { registerAdapter(providers, value) { assert.deepEqual(providers,['refractagent']); adapter=value } },
    credentials: { async describe() { return {configured:true} }, async resolve(reference) {
      credentials++; credentialReferences.push(reference)
      // Native DSH CredentialRef is the identifier itself, without an env: prefix.
      return /^[A-Za-z_][A-Za-z0-9_]*$/.test(reference) ? {value:'private-test-key'} : undefined
    } },
    sandboxPolicy: { resolve: () => ({mode:'workspace-write',workspaceRoot:'/tmp/agent-contract'}) },
    sandbox: { confine: argv => ({argv:['sandbox',...argv],enforcement:'full'}) },
    subprocess: {
      async resolveExecutable() { return '/installed/core/bin/python' },
      spawn(spec) {
        const stdin=new PassThrough(); let input=''
        stdin.on('data',chunk=>{input+=String(chunk)})
        spawns.push({argv:spec.argv,env:spec.env,input:()=>input})
        const output = { schema_version:'refractagent-result-v1',strategy:'balanced',strategy_name:'均衡',
          mode:'demo',status:'simulated',answer:'[SIMULATED] answer',costs:{production:0,evaluation:0,unconfirmed:0},
          models:{answer:'physical-model'},usage:{input_tokens:20,output_tokens:30},simulated:true,
          dag:{phase:'finished',status:'simulated',simulated:true,reason:'模拟',nodes:[]},
          billing_unit:'AFP',result_path:'/tmp/agent-contract/runs/id/result.json',run_id:'id',...result }
        const stdout = new PassThrough()
        stdin.on('finish', () => stdout.end(JSON.stringify(output)+'\n'))
        return {stdin,stdout,done:Promise.resolve({exitCode:0,signal:null}),async waitForExit(){},
          collected:{stdout:{readFrom:()=>({text:JSON.stringify(output),lossy:false})}} }
      },
    },
  }
  return {ctx,spawns,credentialReferences,get adapter(){return adapter!},get credentials(){return credentials}}
}
const options = {provider:'refractagent',model:'balanced',system:'保留系统要求',
  messages:[{role:'user',content:[{type:'text',text:'比较两个方案'}]}],signal:new AbortController().signal}
async function chunks(adapter: AgentAdapter) {
  const output=[]
  for await (const chunk of adapter.stream(options)) output.push(chunk)
  return output
}

test('native registration advertises three strategy models with zero retries',async()=>{
  const f=fixture();apply(f.ctx)
  assert.deepEqual((await f.adapter.listModels('refractagent')).map(m=>m.id),['economy','balanced','quality'])
  assert.equal(f.adapter.providerRetryPolicy('refractagent').maxRetries,0)
  assert.equal(f.credentials,0);assert.equal(f.spawns.length,0)
  await assert.rejects(f.adapter.resolveModel('refractagent','unknown'))
})
test('demo uses installed core through native sandboxed subprocess and preserves conversation',async()=>{
  const f=fixture(); const result=await chunks(createAdapter(f.ctx,configure()))
  assert.equal(f.credentials,0)
  const spawn=f.spawns[0]!
  assert.deepEqual(spawn.argv.slice(0,5),['sandbox','/installed/core/bin/python','-m','refractrouter.agent_cli','run'])
  assert.ok(!spawn.argv.includes('--execute-paid-run'))
  assert.equal(spawn.env.PYTHONPATH,undefined)
  assert.ok(JSON.parse(spawn.input()).context.includes('保留系统要求'))
  assert.equal(JSON.parse(spawn.input()).outputConstraints, undefined)
  assert.deepEqual(result.at(-1)?.reason,{kind:'stop'})
  assert.equal(result.filter(c=>c.type==='finish').length,1)
  assert.equal(result.find(c=>c.type==='text-delta')?.text,'[SIMULATED] answer')
})
test('automatic decomposition is passed to Python without a fabricated plan',async()=>{
  const f=fixture()
  await chunks(createAdapter(f.ctx,configure({template:'auto'})))
  const payload=JSON.parse(f.spawns[0]!.input())
  assert.equal(payload.template,'auto')
  assert.equal(payload.plan,undefined)
})

test('explicit length constraints reach Python and failed checks preserve answer and replay verdicts', async()=>{
  const constraint = {maxLength:250, unit:'unicode-code-points', countWhitespace:false}
  const validation = {schema_version:'output-length-check-v1',status:'failed',constraints:{...constraint},
    passed:false,actual_length:263,output_sha256:'a'.repeat(64)}
  const answer = '长'.repeat(263)
  const quality = {score:95,passed:true,rationale:'模型误判长度通过'}
  const f = fixture({mode:'live',simulated:false,status:'output-constraint-failed',answer,
    generation_status:'completed',format_validation:validation,quality})
  const config = configure({executionMode:'live',allowPaidRuns:true,preset:'ark-agent-plan',outputConstraints:constraint})
  constraint.maxLength=1000
  const result = await chunks(createAdapter(f.ctx,config))
  assert.equal((JSON.parse(f.spawns[0]!.input()).outputConstraints).maxLength,250)
  assert.equal(f.spawns.length,1)
  assert.equal(result.find(c=>c.type==='text-delta')?.text,answer)
  const info = String(result.find(c=>c.type==='reasoning-delta')?.text)
  assert.match(info,/生成：completed/)
  assert.match(info,/语义评审：.*"passed":true/)
  assert.match(info,/长度检查：未通过，263\/250 Unicode 码点（不计空白）/)
  const replay = result.at(-1)?.replayState as {response:{refractagent:Record<string,unknown>}}
  assert.deepEqual(replay.response.refractagent.formatValidation,validation)
  assert.deepEqual(replay.response.refractagent.quality,quality)
  assert.equal(replay.response.refractagent.generationStatus,'completed')
})

test('explicit checks cannot silently disappear with an older installed core',async()=>{
  const f=fixture()
  await assert.rejects(chunks(createAdapter(f.ctx,configure({outputConstraints:{
    maxLength:250,unit:'unicode-code-points',countWhitespace:false}}))),/did not return/)
  for (const outputConstraints of [null,{}, {maxLength:250},
    {maxLength:250,unit:'tokens',countWhitespace:false},
    {maxLength:250,unit:'unicode-code-points',countWhitespace:'false'}]) {
    assert.throws(()=>configure({outputConstraints}),/invalid outputConstraints/)
  }
})
test('host-injected user-role context cannot replace the latest actual user task',async()=>{
  const f=fixture()
  const messages=[
    {role:'user',source:{kind:'user'},content:[{type:'text',text:'之前的任务'}]},
    {role:'user',source:{kind:'agent-instructions'},content:[{type:'text',text:'项目说明'}]},
    {role:'assistant',source:{kind:'model'},content:[{type:'text',text:'之前的答案'}]},
    {role:'user',source:{kind:'user'},content:[{type:'text',text:'只比较部署成本'}]},
    {role:'user',source:{kind:'plugin'},content:[{type:'text',text:'运行环境'}]},
    {role:'user',source:{kind:'skill-catalog'},content:[{type:'text',text:'注入的技能目录'}]},
  ]
  for await(const _ of createAdapter(f.ctx,configure()).stream({...options,messages})){}
  const payload=JSON.parse(f.spawns[0]!.input())
  assert.equal(payload.task,'只比较部署成本')
  assert.deepEqual(JSON.parse(payload.context).messages,messages)
  const empty=fixture()
  await assert.rejects(async()=>{
    for await(const _ of createAdapter(empty.ctx,configure()).stream({...options,messages:messages.slice(-2)})){}
  },/requires a text user task/)
  assert.equal(empty.spawns.length,0)
})
test('live deployment gate rejects before credential access or subprocess',async()=>{
  const f=fixture()
  await assert.rejects(chunks(createAdapter(f.ctx,configure({executionMode:'live'}))),/disabled/)
  assert.equal(f.credentials,0);assert.equal(f.spawns.length,0)
})
test('live resolves host credential only after enablement and preserves explicit limits',async()=>{
  const f=fixture({mode:'live',simulated:false,status:'completed'})
  await chunks(createAdapter(f.ctx,configure({executionMode:'live',preset:'ark-agent-plan',allowPaidRuns:true,maxProductionCost:7,maxEvaluationCost:9})))
  assert.equal(f.credentials,1)
  assert.deepEqual(f.credentialReferences,['CODEX_ARK_API_KEY'])
  const spawn=f.spawns[0]!
  assert.ok(spawn.argv.includes('--execute-paid-run'));assert.ok(spawn.argv.includes('7'));assert.ok(spawn.argv.includes('9'))
  assert.equal(spawn.env.CODEX_ARK_API_KEY,'private-test-key')
  assert.ok(!spawn.argv.join(' ').includes('private-test-key'))
  const custom=fixture({mode:'live',simulated:false,status:'completed'})
  await chunks(createAdapter(custom.ctx,configure({executionMode:'live',preset:'ark-agent-plan',allowPaidRuns:true,credentialEnv:'TEAM_ARK_KEY'})))
  assert.deepEqual(custom.credentialReferences,['TEAM_ARK_KEY'])
  assert.equal(custom.spawns[0]!.env.CODEX_ARK_API_KEY,'private-test-key')
})
test('malformed usage or mismatched strategy cannot become a successful model response',async()=>{
  for (const result of [{usage:{input_tokens:NaN,output_tokens:1}},
    {usage:{input_tokens:1,output_tokens:1,cache_read_tokens:-1}},
    {usage:{input_tokens:1,output_tokens:1,reasoning_tokens:0.5}},
    {strategy:'quality'},{mode:'live'},{costs:{production:-1,evaluation:0,unconfirmed:0}}]) {
    const f=fixture(result)
    await assert.rejects(chunks(createAdapter(f.ctx,configure())),/invalid|different/)
  }
})
test('cancelled requests never emit a completed answer',async()=>{
  const f=fixture(); const controller=new AbortController();controller.abort()
  await assert.rejects(async()=>{for await(const _ of createAdapter(f.ctx,configure({executionMode:'live',preset:'ark-agent-plan',allowPaidRuns:true})).stream({...options,signal:controller.signal})){}},/cancelled/)
  assert.equal(f.credentials,0)
  assert.equal(f.spawns.length,0)
})

function userConfiguration(native = false) {
  return { schemaVersion:'refractagent-providers-v1',billingUnit:'USD',qualityMin:0,
    providers: native ? [{id:'host',type:'dsh',dshProvider:'team-host'}] : [
      {id:'one',type:'openai-compatible',baseUrl:'https://one.example/v1',credentialEnv:'FIRST_KEY'},
      {id:'two',type:'openai-compatible',baseUrl:'https://two.example/v1',credentialEnv:'SECOND_KEY'},
    ],
    models:[
      {id:'answer',provider:native?'host':'one',model:'production',role:'candidate',contextWindow:32768,
       pricing:{unit:'USD',inputPer1k:.001,outputPer1k:.002},routing:{quality:90,latencyMs:1000}},
      {id:'review',provider:native?'host':'two',model:'review',role:'judge',contextWindow:32768,
       pricing:{unit:'USD',inputPer1k:.001,outputPer1k:.002}},
    ] }
}

test('live cannot silently select Ark without a provider configuration or preset',async()=>{
  const f=fixture()
  await assert.rejects(chunks(createAdapter(f.ctx,configure({executionMode:'live',allowPaidRuns:true}))),/configure providerConfig/)
  assert.equal(f.credentials,0);assert.equal(f.spawns.length,0)
})

test('custom providers receive separate host credential references outside the task payload',async()=>{
  const f=fixture({mode:'live',simulated:false,status:'completed',billing_unit:'USD'})
  f.ctx.credentials.resolve=async reference=>{f.credentialReferences.push(reference);return {value:reference+'-secret'}}
  await chunks(createAdapter(f.ctx,configure({executionMode:'live',allowPaidRuns:true,providerConfig:userConfiguration()})))
  const spawn=f.spawns[0]!
  assert.deepEqual(f.credentialReferences,['FIRST_KEY','SECOND_KEY'])
  assert.deepEqual(JSON.parse(spawn.env.REFRACTROUTER_PROVIDER_CREDENTIALS!),{FIRST_KEY:'FIRST_KEY-secret',SECOND_KEY:'SECOND_KEY-secret'})
  assert.equal(spawn.env.CODEX_ARK_API_KEY,undefined)
  assert.equal(spawn.env.FIRST_KEY,undefined)
  assert.deepEqual(JSON.parse(spawn.input()).providerConfig,userConfiguration())
  assert.ok(!spawn.input().includes('-secret'))
  assert.ok(!spawn.argv.includes('--preset'))
})

test('custom demo configuration never resolves provider credentials',async()=>{
  const f=fixture({billing_unit:'USD'})
  await chunks(createAdapter(f.ctx,configure({providerConfig:userConfiguration()})))
  assert.equal(f.credentials,0)
  assert.equal(f.spawns[0]!.env.REFRACTROUTER_PROVIDER_CREDENTIALS,undefined)
  assert.deepEqual(JSON.parse(f.spawns[0]!.input()).providerConfig,userConfiguration())
})

test('provider configuration rejects raw secrets and recursion in the host boundary',()=>{
  const recursive=userConfiguration(true)
  recursive.providers=[{id:'host',type:'dsh',dshProvider:'refractagent'}]
  assert.throws(()=>configure({providerConfig:recursive}),/recursive/)
  const secrets=userConfiguration()
  assert.throws(()=>configure({providerConfig:{...secrets,providers:[{...secrets.providers[0],apiKey:'secret'}]}}),/configuration fields/)
  assert.throws(()=>configure({preset:'ark-agent-plan',providerConfig:userConfiguration()}),/mutually exclusive/)
})

test('DSH providers require zero host retries before any model dispatch',async()=>{
  const f=fixture()
  f.ctx.llm.listProviders=()=>[{id:'team-host'}]
  f.ctx.llm.resolveModelInfo=async()=>({})
  f.ctx.llm.providerRetryPolicy=()=>({mode:'normal',maxRetries:2})
  f.ctx.llm.stream=async function*(){throw new Error('must not call')}
  await assert.rejects(chunks(createAdapter(f.ctx,configure({executionMode:'live',allowPaidRuns:true,providerConfig:userConfiguration(true)}))),/retry-policy-not-zero/)
  assert.equal(f.credentials,0);assert.equal(f.spawns.length,0)
})

test('native DSH routes reuse the host LLM bridge without exporting host credentials',async()=>{
  const f=fixture()
  let hostCalls=0
  let childReply: Record<string,unknown> | undefined
  let childEnvironment: Record<string,string> | undefined
  f.ctx.llm.listProviders=()=>[{id:'team-host'}]
  f.ctx.llm.resolveModelInfo=async()=>({})
  f.ctx.llm.providerRetryPolicy=()=>({mode:'normal',maxRetries:0})
  f.ctx.llm.stream=async function*(request){
    hostCalls++
    assert.equal(request.provider,'team-host');assert.equal(request.model,'production')
    yield {type:'text-delta',text:'native answer'}
    yield {type:'usage',usage:{inputTokens:10,outputTokens:3}}
    yield {type:'finish',reason:{kind:'stop'}}
  }
  f.ctx.subprocess.spawn=spec=>{
    assert.ok(spec.argv.includes('--host-stdio'))
    childEnvironment=spec.env
    const stdin=new PassThrough(),stdout=new PassThrough()
    let finish: (value:{exitCode:number;signal:null})=>void
    const done=new Promise<{exitCode:number;signal:null}>(resolve=>{finish=resolve})
    let buffer=''
    stdin.on('data',chunk=>{
      buffer+=String(chunk)
      let end: number
      while((end=buffer.indexOf('\n'))>=0){
        const message=JSON.parse(buffer.slice(0,end));buffer=buffer.slice(end+1)
        if(message.providerConfig){
          stdout.write(JSON.stringify({protocol:'refractrouter-dsh-llm/v1',type:'request',id:'1',provider:'team-host',model:'production',messages:[{role:'user',content:'native task'}],timeout_ms:1000,max_tokens:1000})+'\n')
        } else {
          childReply=message
          stdout.end(JSON.stringify({schema_version:'refractagent-result-v1',strategy:'balanced',strategy_name:'均衡',mode:'live',status:'completed',answer:'native answer',costs:{production:.01,evaluation:.01,unconfirmed:0},models:{answer:'production'},usage:{input_tokens:10,output_tokens:3},simulated:false,billing_unit:'USD',result_path:'/tmp/result.json',run_id:'native'})+'\n')
          finish!({exitCode:0,signal:null})
        }
      }
    })
    return {stdin,stdout,done,async waitForExit(){},collected:{}}
  }
  const result=await chunks(createAdapter(f.ctx,configure({executionMode:'live',allowPaidRuns:true,providerConfig:userConfiguration(true)})))
  assert.equal(hostCalls,1)
  assert.equal(childReply?.ok,true)
  assert.equal(childReply?.content,'native answer')
  assert.equal(f.credentials,0)
  assert.equal(childEnvironment?.REFRACTROUTER_PROVIDER_CREDENTIALS,undefined)
  assert.equal(childEnvironment?.CODEX_ARK_API_KEY,undefined)
  assert.equal(result.find(c=>c.type==='text-delta')?.text,'native answer')
})


test('all configured credentials are redacted from runner errors',async()=>{
  const f=fixture({schema_version:'refractagent-error-v1',error:'FIRST_KEY-secret SECOND_KEY-secret'})
  f.ctx.credentials.resolve=async reference=>({value:reference+'-secret'})
  await assert.rejects(chunks(createAdapter(f.ctx,configure({executionMode:'live',allowPaidRuns:true,providerConfig:userConfiguration()}))),
    (error: unknown)=>error instanceof Error && !error.message.includes('KEY-secret') && error.message.includes('[REDACTED]'))
})

test('configured provider snapshots cannot be changed after registration',()=>{
  const input=userConfiguration()
  const config=configure({providerConfig:input})
  input.models[0]!.provider='two'
  assert.equal(config.providerConfig!.models[0]!.provider,'one')
  assert.throws(()=>{config.providerConfig!.models[0]!.provider='two'},TypeError)
})


test('Responses provider configuration and reasoning envelope reach the Python core',async()=>{
  const f=fixture({mode:'live',status:'completed',simulated:false,billing_unit:'USD'})
  const config={...userConfiguration(),providers:[{id:'one',type:'openai-responses',credentialEnv:'OPENAI_API_KEY'}]}
  for(const model of config.models)model.provider='one'
  const models=config.models.map(model=>({...model,maxOutputTokens:32768,contextWindow:131072,
    requestOptions:{reasoning:{effort:'high'}}}))
  await chunks(createAdapter(f.ctx,configure({executionMode:'live',allowPaidRuns:true,
    maxOutputTokens:32768,providerConfig:{...config,models}})))
  const spawn=f.spawns[0]!
  assert.ok(spawn.argv.includes('32768'))
  assert.deepEqual(f.credentialReferences,['OPENAI_API_KEY'])
  assert.equal(JSON.parse(spawn.input()).providerConfig.models[0].requestOptions.reasoning.effort,'high')
  assert.equal(spawn.env.CODEX_ARK_API_KEY,undefined)
})


test('node effort profiles pass to Python and selected efforts survive display and replay',async()=>{
  const modelRoutes={cost:{id:'answer-low',provider:'one',model:'same',reasoning_effort:'low'},
    answer:{id:'answer-high',provider:'one',model:'same',reasoning_effort:'high'}}
  const evaluationModel={id:'review',provider:'one',model:'review',reasoning_effort:'medium'}
  const f=fixture({billing_unit:'USD',model_routes:modelRoutes,evaluation_model:evaluationModel})
  const config=userConfiguration()
  const base=config.models[0]!
  const variants=['low','high'].map(effort=>({...base,id:'answer-'+effort,model:'same',reasoningEffort:effort,
    routing:{quality:90,latencyMs:2000,outputTokens:1000,profiles:[
      {nodeType:'synthesis',difficulty:'low',risk:'low',quality:95,latencyMs:1000,outputTokens:1000}]}}))
  const input={...config,models:[...variants,config.models[1]!]}
  const output=await chunks(createAdapter(f.ctx,configure({providerConfig:input})))
  assert.deepEqual(JSON.parse(f.spawns[0]!.input()).providerConfig,input)
  assert.ok(String(output.find(c=>c.type==='reasoning-delta')?.text).includes(JSON.stringify(modelRoutes)))
  const replay=output.at(-1)?.replayState as {response:{refractagent:{modelRoutes:unknown;evaluationModel:unknown}}}
  assert.deepEqual(replay.response.refractagent.modelRoutes,modelRoutes)
  assert.deepEqual(replay.response.refractagent.evaluationModel,evaluationModel)
})

test('automatic mode reports progress before spawning and forwards bounded planning controls', async()=>{
  const f=fixture()
  const adapter=createAdapter(f.ctx,configure({template:'auto',plannerModelId:'small',
    plannerTimeoutMs:8000,plannerMaxOutputTokens:900,maxDynamicSplits:1,maxConcurrency:3,verifyDependencies:true}))
  const stream=adapter.stream(options)[Symbol.asyncIterator]()
  assert.equal((await stream.next()).value?.type,'block-start')
  const progress=(await stream.next()).value
  assert.equal(progress?.type,'reasoning-delta')
  assert.match(String(progress?.text),/正在/)
  assert.equal(f.spawns.length,0)
  while(!(await stream.next()).done) {}
  const spawn=f.spawns[0]!
  const payload=JSON.parse(spawn.input())
  assert.equal(payload.plannerModelId,'small')
  assert.equal(payload.maxDynamicSplits,1)
  assert.equal(payload.maxConcurrency,3)
  assert.equal(payload.verifyDependencies,true)
})

function progressHarness() {
  const f = fixture()
  let finish: (() => void) | undefined
  let aborted = false
  const node = {id:'answer',objective:'整理结论',parents:[],state:'running',attempt:1,
    model:{id:'cheap',provider:'ark-plan',model:'flash',reasoning_effort:null},recovery:null}
  const view = {phase:'executing',status:'started',simulated:false,reason:'独立处理',nodes:[node]}
  f.ctx.subprocess.spawn = spec => {
    assert.ok(spec.argv.includes('--progress-stdio'))
    const stdin = new PassThrough(), stdout = new PassThrough()
    let resolve!: (value:{exitCode:number;signal:null})=>void
    const done = new Promise<{exitCode:number;signal:null}>(r=>{resolve=r})
    const send = (sequence:number, snapshot:unknown) => stdout.write(JSON.stringify({protocol:'refractagent-progress/v1',run_id:'live',sequence,elapsed_ms:sequence,...snapshot as object})+'\n')
    stdin.on('finish', () => {
      send(1,{...view,nodes:[],phase:'planning'})
      send(2,{...view,reason:'private-test-key <img src=x> [打开](https://example.invalid)'})
    })
    finish = () => {
      const dag = {...view,phase:'finished',status:'completed',nodes:[{...node,state:'ok'}]}
      send(3,dag)
      stdout.end(JSON.stringify({schema_version:'refractagent-result-v1',strategy:'balanced',strategy_name:'均衡',
        mode:'live',status:'completed',answer:'最终答案',simulated:false,dag,plan_origin:'model',plan:{nodes:[node]},
        costs:{production:0,evaluation:0,unconfirmed:0},models:{answer:'flash'},usage:{input_tokens:1,output_tokens:1},
        billing_unit:'AFP',result_path:'/tmp/run/result.json'})+'\n')
      resolve({exitCode:0,signal:null})
    }
    spec.signal.addEventListener('abort',()=>{aborted=true;stdout.end();resolve({exitCode:1,signal:null})},{once:true})
    return {stdin,stdout,done,collected:{},async waitForExit(){}}
  }
  const stream = createAdapter(f.ctx,configure({template:'auto',executionMode:'live',allowPaidRuns:true,preset:'ark-agent-plan'})).stream(options)[Symbol.asyncIterator]()
  return {stream,finish:()=>finish!(),get aborted(){return aborted}}
}

test('节点表在模型完成前显示且运行记录保留完整进度，敏感值与 Markdown 被转义', {timeout:3000}, async()=>{
  const h = progressHarness()
  let seen = ''
  while (!seen.includes('answer ·')) {
    const chunk = await h.stream.next()
    assert.equal(chunk.done,false)
    if (chunk.value?.type==='reasoning-delta') seen += String(chunk.value.text)
  }
  assert.match(seen,/依赖：/)
  assert.match(seen,/运行中/)
  assert.match(seen,/ark-plan\/flash/)
  assert.ok(!seen.includes('private-test-key') && !seen.includes('<img'))
  assert.ok(seen.includes('REDACTED') && seen.includes('‹img'))
  h.finish()
  const chunks:Record<string,unknown>[]=[]
  while(true){const item=await h.stream.next();if(item.done)break;chunks.push(item.value!)}
  const block=chunks.find(c=>c.type==='block-end'&&c.index===0)!.block as {text:string}
  assert.match(block.text,/运行中/)
  assert.match(block.text,/已完成/)
  assert.equal(chunks.find(c=>c.type==='text-delta')?.text,'最终答案')
  const replay=chunks.at(-1)!.replayState as {response:{refractagent:{dag:{nodes:Array<{state:string}>}}}}
  assert.equal(replay.response.refractagent.dag.nodes[0]!.state,'ok')
})

test('停止消费进度时取消子进程，不产生伪完成答案', {timeout:3000}, async()=>{
  const h=progressHarness()
  let seen=''
  while(!seen.includes('answer ·')){
    const chunk=await h.stream.next()
    if(chunk.value?.type==='reasoning-delta')seen+=String(chunk.value.text)
  }
  await h.stream.return?.()
  assert.equal(h.aborted,true)
})
