import assert from 'node:assert/strict'
import { PassThrough } from 'node:stream'
import test from 'node:test'
import { apply, configure, createAdapter, type AgentAdapter, type AgentContext } from '../dist/agent-provider.js'

function fixture(result: Record<string, unknown> | Array<Record<string, unknown>> = {}) {
  let adapter: AgentAdapter | undefined
  let discovery: ((request:{provider?:string;baseURL?:string;api?:string;apiKey?:string},signal?:AbortSignal)=>Promise<readonly {id:string;name?:string}[]>)|undefined
  const discoveries:Record<string,typeof discovery>={}
  let credentials = 0
  const credentialReferences: string[] = []
  const spawns: Array<{ argv: string[]; env: Record<string,string>; input: () => string }> = []
  let runIndex=0
  const ctx: AgentContext = {
    llm: { registerAdapter(providers, value) { assert.deepEqual(providers,['refractagent']); adapter=value },
      registerModelDiscovery(settingsNs,callback){discoveries[settingsNs]=callback
        if(settingsNs==='refractagent-router-projects')discovery=callback;return()=>{}} },
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
        if(spec.argv.includes('route-profiles')){
          const text=JSON.stringify({schemaVersion:'refractrouter-route-profiles-v1',modelCalls:0,profiles:[{
            route:'team/worker',effectiveModel:'worker-v1',reasoningEffort:'default',prediction_ms:1250,
            samples:4,window:'latest-50-successful-p90',last_observed_at:'2026-09-22T00:00:00Z',
            snapshot_id:'a'.repeat(64),statusCounts:{success:4}}]})
          return {done:Promise.resolve({exitCode:0,signal:null}),async waitForExit(){},
            collected:{stdout:{readFrom:()=>({text,lossy:false})}}}
        }
        const overlay=Array.isArray(result)?result[runIndex++]??{}:result
        const output = { schema_version:'refractagent-result-v1',strategy:'balanced',strategy_name:'均衡',
          mode:'demo',status:'simulated',answer:'[SIMULATED] answer',costs:{production:0,evaluation:0,unconfirmed:0},
          models:{answer:'physical-model'},usage:{input_tokens:20,output_tokens:30},simulated:true,
          dag:{phase:'finished',status:'simulated',simulated:true,reason:'模拟',nodes:[]},
          billing_unit:'AFP',result_path:'/tmp/agent-contract/runs/id/result.json',run_id:'id',...overlay }
        const stdout = new PassThrough()
        if(spec.argv.includes('--host-stdio')) stdin.on('data', chunk=>{
          if(String(chunk).includes('\n')) stdout.end(JSON.stringify(output)+'\n')
        })
        else stdin.on('finish', () => stdout.end(JSON.stringify(output)+'\n'))
        return {stdin,stdout,done:Promise.resolve({exitCode:0,signal:null}),async waitForExit(){},
          collected:{stdout:{readFrom:()=>({text:JSON.stringify(output),lossy:false})}} }
      },
    },
  }
  return {ctx,spawns,credentialReferences,discoveries,get adapter(){return adapter!},get discovery(){return discovery!},get credentials(){return credentials}}
}
const options = {provider:'refractagent',model:'balanced',system:'保留系统要求',
  messages:[{role:'user',content:[{type:'text',text:'比较两个方案'}]}],signal:new AbortController().signal}
async function chunks(adapter: AgentAdapter) {
  const output=[]
  for await (const chunk of adapter.stream(options)) output.push(chunk)
  return output
}
const modelPool = () => ({schemaVersion:'refractagent-dsh-model-pool-v1' as const,billingUnit:'USD',
  security:{dataMode:'synthetic'},routes:[
    {provider:'team',model:'planner',deployment:'local' as const,overrides:{inputPer1k:0,outputPer1k:0,quality:90,latencyMs:100}},
    {provider:'team',model:'worker',deployment:'local' as const,overrides:{inputPer1k:0,outputPer1k:0,quality:80,latencyMs:50}},
  ]})
const liveProviderConfig=()=>({schemaVersion:'refractagent-providers-v4' as const,billingUnit:'CNY',
  objective:{qualityMin:80,primary:'cost' as const,secondary:'latency' as const,dagMode:'auto' as const},
  security:{dataMode:'synthetic'},providers:[{id:'external',type:'openai-compatible' as const,
    baseUrl:'https://models.example/v1',credentialEnv:'MODEL_KEY',deployment:'external-cloud' as const}],
  models:[
    {id:'worker',provider:'external',model:'worker',roles:['planner' as const,'worker' as const,'classifier' as const],
      contextWindow:131072,maxOutputTokens:4096,pricing:{unit:'CNY',inputPer1k:.0067459,outputPer1k:.0134918},
      routing:{quality:90,latencyMs:1000}},
    {id:'judge',provider:'external',model:'judge',roles:['judge' as const],contextWindow:131072,
      maxOutputTokens:4096,pricing:{unit:'CNY',inputPer1k:.0067459,outputPer1k:.0134918}},
  ]})
const liveExecution=()=>({schemaVersion:'refractagent-live-execution-v1' as const,enabled:true,
  maxProductionCost:.1,maxEvaluationCost:.1,complexityPolicy:'auto' as const,reviewPolicy:'adaptive' as const})
const previewResult={strategy:'auto',strategy_name:'自动路由',mode:'preflight',status:'preview',answer:'',
  simulated:false,billing_unit:'CNY',live_authorization_preview:{schema_version:'refractagent-live-authorization-v1',
    authorization_id:'auth-1',issued_at:'2026-09-22T00:00:00Z',expires_at:'2026-09-22T00:10:00Z',
    preview_sha256:'a'.repeat(64),ready:true,complexity:{decision:'direct'},review:{required:false},
    calls:{maximum:1},costs:{production_estimate:.01,evaluation_estimate:0,production_hard_limit:.1,
      evaluation_hard_limit:.1}}}

test('native registration advertises three strategy models with zero retries',async()=>{
  assert.equal(configure({}).pythonExecutable,'refractagent')
  const f=fixture();apply(f.ctx)
  assert.deepEqual((await f.adapter.listModels('refractagent')).map(m=>m.id),['economy','balanced','quality'])
  assert.equal(f.adapter.providerRetryPolicy('refractagent').maxRetries,0)
  assert.equal(f.credentials,0);assert.equal(f.spawns.length,0)
  await assert.rejects(f.adapter.resolveModel('refractagent','unknown'))
})
test('legacy demo replay omits unavailable live fields for strict DSH JSON serialization',async()=>{
  const f=fixture();apply(f.ctx)
  const output=await chunks(f.adapter)
  const finish=output.find(chunk=>chunk.type==='finish') as Record<string,unknown>
  const replay=((finish.replayState as Record<string,unknown>).response as Record<string,unknown>)
    .refractagent as Record<string,unknown>
  assert.equal(Object.hasOwn(replay,'complexityGate'),false)
  assert.equal(Object.hasOwn(replay,'review'),false)
  assert.equal(Object.hasOwn(replay,'modelCallLimit'),false)
})
test('route profile discovery reads local persisted observations without a model call',async()=>{
  const f=fixture();apply(f.ctx)
  const discover=f.discoveries['refractagent-route-profiles']!
  const rows=await discover({})
  assert.equal(rows[0]?.id,'team/worker')
  assert.equal(JSON.parse(rows[0]?.name??'{}').samples,4)
  assert.ok(f.spawns[0]?.argv.includes('route-profiles'))
  assert.equal(f.credentials,0)
})
test('v4 advertises only automatic routing and normalizes a stale DSH legacy selection',async()=>{
  const f=fixture({strategy:'auto',strategy_name:'自动路由',billing_unit:'USD'})
  const providerConfig={schemaVersion:'refractagent-providers-v4',billingUnit:'USD',
    objective:{qualityMin:80,primary:'cost',secondary:'latency',dagMode:'auto'},
    security:{dataMode:'live'},
    providers:[{id:'local',type:'openai-compatible',baseUrl:'https://local.example/v1',deployment:'local'}],
    models:[
      {id:'work',provider:'local',model:'worker',roles:['planner','worker'],contextWindow:32768,
       pricing:{unit:'USD',inputPer1k:0,outputPer1k:0},routing:{quality:90,latencyMs:1000}},
      {id:'review',provider:'local',model:'judge',roles:['judge'],contextWindow:32768,
       pricing:{unit:'USD',inputPer1k:0,outputPer1k:0}},
    ]}
  const adapter=createAdapter(f.ctx,()=>configure({providerConfig}))
  assert.deepEqual((await adapter.listModels('refractagent')).map(model=>model.id),['auto','auto-live'])
  assert.equal((await adapter.resolveModel('refractagent','balanced')).id,'balanced')
  const v4Chunks=[]
  for await(const chunk of adapter.stream({...options,model:'balanced'})) v4Chunks.push(chunk)
  assert.equal(f.credentials,0)
  assert.equal(f.spawns.length,1)
  const payload=JSON.parse(f.spawns[0]!.input())
  assert.equal(payload.strategy,'auto')
  assert.equal(payload.template,'auto')
  assert.deepEqual(payload.providerConfig,providerConfig)
  assert.ok(v4Chunks.some(chunk=>chunk.type==='reasoning-delta' && /自动路由/.test(String(chunk.text))))
  assert.ok(f.spawns[0]!.argv.includes('--progress-stdio'))

  const legacyLive=fixture({strategy:'auto',strategy_name:'自动路由',billing_unit:'USD'})
  const legacyAdapter=createAdapter(legacyLive.ctx,()=>configure({providerConfig,executionMode:'live',allowPaidRuns:true}))
  const legacyChunks=[]
  for await(const chunk of legacyAdapter.stream({...options,model:'auto'})) legacyChunks.push(chunk)
  assert.deepEqual(legacyChunks.at(-1)?.reason,{kind:'stop'})
  assert.equal(legacyLive.credentials,0)
  assert.equal(legacyLive.spawns.length,1)
  assert.ok(legacyLive.spawns[0]!.argv.includes('demo'))
  assert.ok(!legacyLive.spawns[0]!.argv.includes('--execute-paid-run'))
})
test('settings-enabled developer live starts one local preflight and one bound live process without host approval',async()=>{
  const liveResult={strategy:'auto',strategy_name:'自动路由',mode:'live',status:'completed',answer:'真实答案',
    simulated:false,billing_unit:'CNY',plan_origin:'direct-gate',plan:{nodes:[{node_id:'answer'}]},
    dag:{phase:'finished',status:'completed',simulated:false,reason:'直接回答',nodes:[]}}
  const f=fixture([previewResult,liveResult])
  const adapter=createAdapter(f.ctx,()=>configure({routerUrl:'http://127.0.0.1:8787',
    providerConfig:liveProviderConfig(),liveExecution:{...liveExecution(),maxOutputTokens:'unlimited'}}))
  const output=[]
  for await(const chunk of adapter.stream({...options,model:'auto-live',tools:[{name:'forbidden',description:'x',parameters:{}}]}))output.push(chunk)
  assert.deepEqual((await adapter.listModels('refractagent')).map(model=>model.id),['auto','auto-live'])
  assert.equal(f.spawns.length,2)
  assert.ok(f.spawns[0]!.argv.includes('preflight'))
  assert.ok(f.spawns[1]!.argv.includes('live'))
  assert.ok(f.spawns[1]!.argv.includes('--execute-paid-run'))
  const previewPayload=JSON.parse(f.spawns[0]!.input()),livePayload=JSON.parse(f.spawns[1]!.input())
  assert.equal(previewPayload.authorization,undefined)
  assert.equal(livePayload.authorization.authorization_id,'auth-1')
  assert.equal(livePayload.hostTools,undefined)
  assert.equal(livePayload.maxDynamicSplits,0);assert.equal(livePayload.maxConcurrency,1)
  assert.equal(previewPayload.unlimitedNodeOutput,true)
  assert.equal(livePayload.unlimitedNodeOutput,true)
  assert.equal(f.credentials,1)
  assert.equal(output.find(chunk=>chunk.type==='text-delta')?.text,'真实答案')
  assert.deepEqual(output.at(-1)?.reason,{kind:'stop'})
})
test('enabled DSH tools reach preflight and live with the same bounded catalog',async()=>{
  const liveResult={strategy:'auto',strategy_name:'自动路由',mode:'live',status:'completed',answer:'结果',
    simulated:false,billing_unit:'CNY',plan_origin:'direct-gate',plan:{nodes:[{node_id:'answer'}]},
    dag:{phase:'finished',status:'completed',simulated:false,reason:'直接回答',nodes:[]}}
  const f=fixture([previewResult,liveResult])
  const agent={session:{events:[{type:'step/start',data:{turn:1,step:1}}],append(){}}}
  f.ctx.agents={requireInitiator:()=>agent}
  f.ctx.tools={async execute(){return {isError:false,content:[{type:'text',text:'模拟结果'}]}}}
  const adapter=createAdapter(f.ctx,()=>configure({providerConfig:liveProviderConfig(),
    liveExecution:{...liveExecution(),maxDshToolCalls:3}}))
  const schemas=[{name:'web_search',description:'查询网页',parameters:{type:'object'}}]
  for await(const _ of adapter.stream({...options,model:'auto-live',tools:schemas})) { /* consume */ }
  assert.equal(f.spawns.length,2)
  const preview=JSON.parse(f.spawns[0]!.input()),live=JSON.parse(f.spawns[1]!.input())
  assert.deepEqual(preview.hostTools,schemas)
  assert.deepEqual(live.hostTools,schemas)
  assert.equal(preview.maxDshToolCalls,3)
  assert.equal(live.maxDshToolCalls,3)
  assert.ok(f.spawns.every(spawn=>spawn.argv.includes('--host-stdio')))
})
test('production and review unlimited choices reach both preview and live unchanged',async()=>{
  const liveResult={strategy:'auto',strategy_name:'自动路由',mode:'live',status:'completed',answer:'答案',
    simulated:false,billing_unit:'CNY',plan_origin:'direct-gate',plan:{nodes:[{node_id:'answer'}]},
    dag:{phase:'finished',status:'completed',simulated:false,reason:'直接回答',nodes:[]}}
  const f=fixture([previewResult,liveResult])
  const adapter=createAdapter(f.ctx,()=>configure({providerConfig:liveProviderConfig(),
    liveExecution:{...liveExecution(),maxProductionCost:'unlimited',maxEvaluationCost:'unlimited'}}))
  for await(const _ of adapter.stream({...options,model:'auto-live'})) { /* consume */ }
  assert.equal(f.spawns.length,2)
  for(const spawn of f.spawns){
    const production=spawn.argv.indexOf('--production-budget')
    const evaluation=spawn.argv.indexOf('--evaluation-budget')
    assert.equal(spawn.argv[production+1],'unlimited')
    assert.equal(spawn.argv[evaluation+1],'unlimited')
  }
})
test('DSH 模型池在执行前解析宿主目录、隔离枚举失败并排除自身',async()=>{
  const f=fixture({strategy:'auto',strategy_name:'自动路由',billing_unit:'USD'})
  Object.assign(f.ctx.llm,{
    listProviders:()=>[{id:'refractagent',name:'RefractAgent'},{id:'broken',name:'失效 Provider'},{id:'team',name:'团队模型'}],
    listModels:async(provider:string)=>{if(provider==='broken')throw new Error('枚举失败');return [
      {id:'planner',name:'规划模型'},{id:'worker',name:'执行模型'}]},
    resolveModelInfo:async(_provider:string,model:string)=>({id:model,context:{contextWindow:131072},defaultMaxTokens:8192,
      reasoning:{efforts:[{id:'low'},{id:'high'}]}}),
  })
  const result=await chunks(createAdapter(f.ctx,()=>configure({dshModelPool:modelPool()})))
  assert.deepEqual(result.at(-1)?.reason,{kind:'stop'})
  const payload=JSON.parse(f.spawns[0]!.input())
  assert.deepEqual(payload.dshCatalogSnapshot.routes.map((row:{provider:string;model:string})=>`${row.provider}/${row.model}`),
    ['team/planner','team/worker'])
  assert.deepEqual(payload.dshCatalogSnapshot.failures,[{provider:'broken',message:'枚举失败'}])
  assert.equal(payload.providerConfig,undefined)
})
test('已删除的 DSH 路线在启动 Python 前以稳定错误终止',async()=>{
  const f=fixture({strategy:'auto',strategy_name:'自动路由',billing_unit:'USD'})
  Object.assign(f.ctx.llm,{
    listProviders:()=>[{id:'team'}],
    listModels:async()=>[{id:'planner'}],
    resolveModelInfo:async()=>({context:{contextWindow:131072},defaultMaxTokens:8192}),
  })
  const result=await chunks(createAdapter(f.ctx,()=>configure({dshModelPool:modelPool()})))
  assert.equal(f.spawns.length,0)
  assert.deepEqual(result.at(-1)?.reason,{kind:'error',failure:{code:'REFRACTAGENT_ROUTE_UNAVAILABLE',
    message:'RefractAgent 未执行：配置的 Provider 或模型路线当前不可用，请检查 DSH 模型设置。 诊断：DSH route unavailable: team/worker'}})
  assert.equal(result.some(chunk=>chunk.type==='text-delta'),false)
})
test('demo uses installed core through native sandboxed subprocess and preserves conversation',async()=>{
  const f=fixture(); const result=await chunks(createAdapter(f.ctx, () => configure()))
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
  const replay=result.at(-1)?.replayState as {response:{refractagent:Record<string,unknown>}}
  assert.equal(Object.hasOwn(replay.response.refractagent,'routerTask'),false)
})
test('Router URL uses authenticated NDJSON transport without starting local Python',async()=>{
  const f=fixture()
  const originalFetch=globalThis.fetch
  const requests:Request[]=[]
  globalThis.fetch=async(input,init)=>{
    const request=new Request(input,init);requests.push(request)
    if(request.url.endsWith('/healthz'))return Response.json({protocol:'refractagent-http-v1',status:'ok',paid_execution:false})
    const result={schema_version:'refractagent-result-v1',strategy:'balanced',strategy_name:'均衡',
      mode:'demo',status:'simulated',answer:'[SIMULATED] remote answer',
      costs:{production:0,evaluation:0,unconfirmed:0},models:{answer:'physical-model'},
      usage:{input_tokens:0,output_tokens:0},simulated:true,billing_unit:'AFP',
      dag:{phase:'finished',status:'simulated',simulated:true,reason:'远程模拟',nodes:[]},
      result_path:'/srv/runs/id/result.json',run_id:'id'}
    const progress={protocol:'refractagent-progress/v1',run_id:'id',sequence:1,elapsed_ms:1,
      phase:'routing',status:'started',simulated:true,reason:'远程模拟',nodes:[]}
    return new Response(JSON.stringify({protocol:'refractagent-http-v1',type:'progress',value:progress})+'\n'
      +JSON.stringify({protocol:'refractagent-http-v1',type:'result',value:result})+'\n',{
      status:200,headers:{'content-type':'application/x-ndjson'}})
  }
  try{
    const output=await chunks(createAdapter(f.ctx,()=>configure({
      routerUrl:'http://127.0.0.1:8787/',routerCredential:'ROUTER_TOKEN',template:'auto'})))
    assert.equal(f.spawns.length,0)
    assert.deepEqual(f.credentialReferences,['ROUTER_TOKEN'])
    assert.deepEqual(requests.map(request=>new URL(request.url).pathname),['/healthz','/v1/run'])
    assert.equal(requests[1]!.headers.get('authorization'),'Bearer private-test-key')
    const body=JSON.parse(await requests[1]!.text())
    assert.equal(body.protocol,'refractagent-http-v1')
    assert.equal(body.execution.mode,'demo')
    assert.equal(body.request.task,'比较两个方案')
    assert.ok(output.some(chunk=>chunk.type==='reasoning-delta'&&String(chunk.text).includes('远程模拟')))
    assert.equal(output.find(chunk=>chunk.type==='text-delta')?.text,'[SIMULATED] remote answer')
    assert.deepEqual(output.at(-1)?.reason,{kind:'stop'})
  }finally{globalThis.fetch=originalFetch}
})
test('Router HTTP v2 resumes durable events without resubmitting and exposes task metadata',async()=>{
  const f=fixture();const originalFetch=globalThis.fetch;const requests:Request[]=[]
  const result={schema_version:'refractagent-result-v1',strategy:'balanced',strategy_name:'均衡',mode:'demo',
    status:'simulated',answer:'[SIMULATED] durable answer',costs:{production:0,evaluation:0,unconfirmed:0},
    models:{answer:'physical-model'},usage:{input_tokens:0,output_tokens:0},simulated:true,billing_unit:'AFP',
    dag:{phase:'finished',status:'simulated',simulated:true,reason:'持久模拟',nodes:[]},
    result_path:'/srv/runs/durable/result.json',run_id:'durable'}
  let eventReads=0
  globalThis.fetch=async(input,init)=>{
    const request=new Request(input,init);requests.push(request);const url=new URL(request.url)
    if(url.pathname==='/healthz')return Response.json({protocol:'refractagent-http-v1',status:'ok',paid_execution:false,
      protocols:['refractagent-http-v1','refractagent-http-v2']})
    if(url.pathname==='/v2/projects')return Response.json({protocol:'refractagent-http-v2',projects:[{id:'alpha',maxConcurrentTasks:2}]})
    if(url.pathname==='/v2/tasks')return Response.json({protocol:'refractagent-http-v2',taskId:'task-1',projectId:'alpha',
      memberId:'alice',status:'queued',createdAt:'now',updatedAt:'now',reused:false},{status:202})
    if(url.pathname==='/v2/tasks/task-1/events'){
      eventReads+=1
      if(eventReads===1)return new Response([
        {sequence:1,type:'status',value:{status:'queued'}},
        {sequence:2,type:'status',value:{status:'running'}},
        {sequence:3,type:'progress',value:{protocol:'refractagent-progress/v1',run_id:'durable',sequence:1,
          elapsed_ms:1,phase:'routing',status:'started',simulated:true,reason:'持久模拟',nodes:[]}},
      ].map(row=>JSON.stringify({protocol:'refractagent-http-v2',taskId:'task-1',...row})+'\n').join(''))
      assert.equal(url.searchParams.get('after'),'3')
      return new Response([
        {sequence:4,type:'result',value:result},
        {sequence:5,type:'status',value:{status:'completed'}},
      ].map(row=>JSON.stringify({protocol:'refractagent-http-v2',taskId:'task-1',...row})+'\n').join(''))
    }
    throw new Error('unexpected URL '+request.url)
  }
  try{
    const output=await chunks(createAdapter(f.ctx,()=>configure({routerUrl:'http://127.0.0.1:8787',
      routerCredential:'ROUTER_TOKEN',routerProject:'alpha',template:'auto'})))
    assert.equal(requests.filter(request=>new URL(request.url).pathname==='/v2/tasks'&&request.method==='POST').length,1)
    const submitted=requests.find(request=>new URL(request.url).pathname==='/v2/tasks'&&request.method==='POST')!
    assert.match(submitted.headers.get('idempotency-key')??'',/^[0-9a-f-]{36}$/)
    assert.equal((JSON.parse(await submitted.text())).projectId,'alpha')
    assert.equal(eventReads,2)
    assert.ok(output.some(chunk=>chunk.type==='reasoning-delta'&&String(chunk.text).includes('团队任务：task-1 · 项目 alpha')))
    assert.equal(output.find(chunk=>chunk.type==='text-delta')?.text,'[SIMULATED] durable answer')
    const replay=output.at(-1)?.replayState as {response:{refractagent:{routerTask:{resumed:boolean,idempotencyKey:string}}}}
    assert.equal(replay.response.refractagent.routerTask.resumed,true)
    assert.equal(replay.response.refractagent.routerTask.idempotencyKey,submitted.headers.get('idempotency-key'))
  }finally{globalThis.fetch=originalFetch}
})
test('Router HTTP v2 cancellation reaches the persistent task endpoint',async()=>{
  const f=fixture();const originalFetch=globalThis.fetch;const controller=new AbortController();let cancelled=false
  globalThis.fetch=async(input,init)=>{
    const request=new Request(input,init);const url=new URL(request.url)
    if(url.pathname==='/healthz')return Response.json({protocol:'refractagent-http-v1',status:'ok',
      protocols:['refractagent-http-v1','refractagent-http-v2']})
    if(url.pathname==='/v2/projects')return Response.json({protocol:'refractagent-http-v2',projects:[{id:'alpha',maxConcurrentTasks:2}]})
    if(url.pathname==='/v2/tasks'&&request.method==='POST'){
      queueMicrotask(()=>controller.abort())
      return Response.json({protocol:'refractagent-http-v2',taskId:'task-cancel',status:'queued'},{status:202})
    }
    if(url.pathname==='/v2/tasks/task-cancel/cancel'){cancelled=true;return Response.json({status:'cancelled'},{status:202})}
    if(url.pathname==='/v2/tasks/task-cancel/events')throw new DOMException('aborted','AbortError')
    throw new Error('unexpected URL '+request.url)
  }
  try{
    const output=[]
    for await(const chunk of createAdapter(f.ctx,()=>configure({routerUrl:'http://127.0.0.1:8787',
      routerCredential:'ROUTER_TOKEN',routerProject:'alpha',template:'auto'})).stream({...options,signal:controller.signal}))output.push(chunk)
    assert.equal(cancelled,true)
    assert.equal((output.at(-1)?.reason as {kind:string}).kind,'aborted')
  }finally{globalThis.fetch=originalFetch}
})
test('Router project discovery stays on the host and returns only authorized project ids',async()=>{
  const f=fixture();const originalFetch=globalThis.fetch;apply(f.ctx)
  globalThis.fetch=async(input,init)=>{
    const request=new Request(input,init)
    assert.equal(request.headers.get('authorization'),'Bearer private-test-key')
    if(request.url.endsWith('/healthz'))return Response.json({protocol:'refractagent-http-v1',status:'ok',
      protocols:['refractagent-http-v1','refractagent-http-v2']})
    return Response.json({protocol:'refractagent-http-v2',projects:[{id:'alpha',maxConcurrentTasks:2}]})
  }
  try{
    const projects=await f.discovery({baseURL:'http://127.0.0.1:8787',api:'ROUTER_TOKEN'})
    assert.deepEqual(projects,[{id:'alpha',name:'alpha（并发上限 2）'}])
    assert.deepEqual(f.credentialReferences,['ROUTER_TOKEN'])
    await assert.rejects(f.discovery({baseURL:'http://127.0.0.1:8787',apiKey:'raw-secret'}),/never a token/)
  }finally{globalThis.fetch=originalFetch}
})
test('Router URL validation rejects insecure remote endpoints and embedded credentials',()=>{
  assert.equal(configure({routerUrl:'http://127.0.0.1:8787/'}).routerUrl,'http://127.0.0.1:8787')
  assert.throws(()=>configure({routerUrl:'http://router.example/v1'}),/requires HTTPS/)
  assert.throws(()=>configure({routerUrl:'https://user:secret@router.example'}),/without credentials/)
  assert.throws(()=>configure({routerCredential:'ROUTER_TOKEN'}),/requires routerUrl/)
  assert.equal(configure({routerUrl:'http://127.0.0.1:8787',routerProject:'alpha'}).routerProject,'alpha')
  assert.throws(()=>configure({routerUrl:'http://127.0.0.1:8787',routerProject:'bad/project'}),/routerProject/)
})
test('automatic decomposition is passed to Python without a fabricated plan',async()=>{
  const f=fixture()
  await chunks(createAdapter(f.ctx, () => configure({template:'auto'})))
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
  const result = await chunks(createAdapter(f.ctx,() => config))
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
  await assert.rejects(chunks(createAdapter(f.ctx, () => configure({outputConstraints:{
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
  for await(const _ of createAdapter(f.ctx, () => configure()).stream({...options,messages})){}
  const payload=JSON.parse(f.spawns[0]!.input())
  assert.equal(payload.task,'只比较部署成本')
  assert.deepEqual(JSON.parse(payload.context).messages,messages)
  const empty=fixture()
  await assert.rejects(async()=>{
    for await(const _ of createAdapter(empty.ctx, () => configure()).stream({...options,messages:messages.slice(-2)})){}
  },/requires a text user task/)
  assert.equal(empty.spawns.length,0)
})
test('live deployment gate rejects before credential access or subprocess',async()=>{
  const f=fixture()
  await assert.rejects(chunks(createAdapter(f.ctx, () => configure({executionMode:'live'}))),/disabled/)
  assert.equal(f.credentials,0);assert.equal(f.spawns.length,0)
})
test('live resolves host credential only after enablement and preserves explicit limits',async()=>{
  const f=fixture({mode:'live',simulated:false,status:'completed'})
  await chunks(createAdapter(f.ctx, () => configure({executionMode:'live',preset:'ark-agent-plan',allowPaidRuns:true,maxProductionCost:7,maxEvaluationCost:9})))
  assert.equal(f.credentials,1)
  assert.deepEqual(f.credentialReferences,['CODEX_ARK_API_KEY'])
  const spawn=f.spawns[0]!
  assert.ok(spawn.argv.includes('--execute-paid-run'));assert.ok(spawn.argv.includes('7'));assert.ok(spawn.argv.includes('9'))
  assert.equal(spawn.env.CODEX_ARK_API_KEY,'private-test-key')
  assert.ok(!spawn.argv.join(' ').includes('private-test-key'))
  const custom=fixture({mode:'live',simulated:false,status:'completed'})
  await chunks(createAdapter(custom.ctx, () => configure({executionMode:'live',preset:'ark-agent-plan',allowPaidRuns:true,credentialEnv:'TEAM_ARK_KEY'})))
  assert.deepEqual(custom.credentialReferences,['TEAM_ARK_KEY'])
  assert.equal(custom.spawns[0]!.env.CODEX_ARK_API_KEY,'private-test-key')
})
test('malformed usage or mismatched strategy cannot become a successful model response',async()=>{
  for (const result of [{usage:{input_tokens:NaN,output_tokens:1}},
    {usage:{input_tokens:1,output_tokens:1,cache_read_tokens:-1}},
    {usage:{input_tokens:1,output_tokens:1,reasoning_tokens:0.5}},
    {strategy:'quality'},{mode:'live'},{costs:{production:-1,evaluation:0,unconfirmed:0}}]) {
    const f=fixture(result)
    await assert.rejects(chunks(createAdapter(f.ctx, () => configure())),/invalid|different/)
  }
})
test('cancelled requests never emit a completed answer',async()=>{
  const f=fixture(); const controller=new AbortController();controller.abort()
  await assert.rejects(async()=>{for await(const _ of createAdapter(f.ctx, () => configure({executionMode:'live',preset:'ark-agent-plan',allowPaidRuns:true})).stream({...options,signal:controller.signal})){}},/cancelled/)
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
  await assert.rejects(chunks(createAdapter(f.ctx, () => configure({executionMode:'live',allowPaidRuns:true}))),/configure providerConfig/)
  assert.equal(f.credentials,0);assert.equal(f.spawns.length,0)
})

test('custom providers receive separate host credential references outside the task payload',async()=>{
  const f=fixture({mode:'live',simulated:false,status:'completed',billing_unit:'USD'})
  f.ctx.credentials.resolve=async reference=>{f.credentialReferences.push(reference);return {value:reference+'-secret'}}
  await chunks(createAdapter(f.ctx, () => configure({executionMode:'live',allowPaidRuns:true,providerConfig:userConfiguration()})))
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
  await chunks(createAdapter(f.ctx, () => configure({providerConfig:userConfiguration()})))
  assert.equal(f.credentials,0)
  assert.equal(f.spawns[0]!.env.REFRACTROUTER_PROVIDER_CREDENTIALS,undefined)
  assert.deepEqual(JSON.parse(f.spawns[0]!.input()).providerConfig,userConfiguration())
})

test('demo with DSH provider declarations does not require or call the host model bridge',async()=>{
  const f=fixture({billing_unit:'USD'})
  await chunks(createAdapter(f.ctx, () => configure({providerConfig:userConfiguration(true)})))
  assert.equal(f.credentials,0)
  assert.equal(f.spawns.length,1)
  assert.equal(f.spawns[0]!.env.REFRACTROUTER_DSH_BRIDGE,undefined)
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
  await assert.rejects(chunks(createAdapter(f.ctx, () => configure({executionMode:'live',allowPaidRuns:true,providerConfig:userConfiguration(true)}))),/retry-policy-not-zero/)
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
  const result=await chunks(createAdapter(f.ctx, () => configure({executionMode:'live',allowPaidRuns:true,providerConfig:userConfiguration(true)})))
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
  await assert.rejects(chunks(createAdapter(f.ctx, () => configure({executionMode:'live',allowPaidRuns:true,providerConfig:userConfiguration()}))),
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
  await chunks(createAdapter(f.ctx, () => configure({executionMode:'live',allowPaidRuns:true,
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
  const output=await chunks(createAdapter(f.ctx, () => configure({providerConfig:input})))
  assert.deepEqual(JSON.parse(f.spawns[0]!.input()).providerConfig,input)
  assert.ok(String(output.find(c=>c.type==='reasoning-delta')?.text).includes(JSON.stringify(modelRoutes)))
  const replay=output.at(-1)?.replayState as {response:{refractagent:{modelRoutes:unknown;evaluationModel:unknown}}}
  assert.deepEqual(replay.response.refractagent.modelRoutes,modelRoutes)
  assert.deepEqual(replay.response.refractagent.evaluationModel,evaluationModel)
})

test('automatic mode starts reasoning lazily and forwards bounded planning controls', async()=>{
  const f=fixture()
  const adapter=createAdapter(f.ctx, () => configure({template:'auto',plannerModelId:'small',
    plannerTimeoutMs:8000,plannerMaxOutputTokens:900,maxDynamicSplits:1,maxConcurrency:3,verifyDependencies:true}))
  const output=await chunks(adapter)
  assert.equal(output[0]?.type,'block-start')
  assert.equal(f.spawns.length,1)
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
  const stream = createAdapter(f.ctx, () => configure({template:'auto',executionMode:'live',allowPaidRuns:true,preset:'ark-agent-plan'})).stream(options)[Symbol.asyncIterator]()
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

test('自动流程失败立即结束思考并发出可读错误，不生成伪成功答案',async()=>{
  const f=fixture({schema_version:'refractagent-error-v1',
    error:'node-input-budget-exceeded before deliverable'})
  const output=[]
  for await(const chunk of createAdapter(f.ctx,()=>configure({template:'auto'})).stream(options)) output.push(chunk)
  assert.equal(output.some(chunk=>chunk.type==='block-start'),false)
  assert.equal(output.some(chunk=>chunk.type==='reasoning-delta'),false)
  assert.equal(output.some(chunk=>chunk.type==='block-end'),false)
  assert.equal(output.some(chunk=>chunk.type==='text-delta'),false)
  assert.equal(output.filter(chunk=>chunk.type==='finish').length,1)
  assert.deepEqual(output.at(-1)?.reason,{kind:'error',failure:{
    code:'REFRACTAGENT_NODE_INPUT_CAPACITY',
    message:'RefractAgent 未执行：当前任务所需输入超过节点容量。请缩短会话、新建会话或选择更大上下文模型。',
  }})
})

test('自动流程区分应用上下文、模型窗口、路线与一般执行失败',async()=>{
  const cases:[string,string][]=[
    ['conversation context exceeds the RefractAgent input limit','REFRACTAGENT_CONTEXT_LIMIT'],
    ['input-or-output-capacity','REFRACTAGENT_MODEL_CONTEXT_LIMIT'],
    ['configured route unavailable','REFRACTAGENT_ROUTE_UNAVAILABLE'],
    ['security requires at least one sensitive-data-capable worker model','REFRACTAGENT_ROUTE_UNAVAILABLE'],
    ['invalid or truncated output for answer (finish_reason=length, output_cap=2048)','REFRACTAGENT_EXECUTION_FAILED'],
    ['ledger write failed','REFRACTAGENT_EXECUTION_FAILED'],
  ]
  for(const [error,code] of cases){
    const output=[]
    const f=fixture({schema_version:'refractagent-error-v1',error})
    for await(const chunk of createAdapter(f.ctx,()=>configure({template:'auto'})).stream(options)) output.push(chunk)
    const reason=output.at(-1)?.reason as {kind:string;failure:{code:string}}
    assert.equal(reason.kind,'error')
    assert.equal(reason.failure.code,code)
    assert.equal(output.some(chunk=>chunk.type==='text-delta'),false)
  }
})

test('自动流程取消保留取消语义并结束思考',async()=>{
  const controller=new AbortController();controller.abort()
  const output=[]
  for await(const chunk of createAdapter(fixture().ctx,()=>configure({template:'auto'}))
    .stream({...options,signal:controller.signal})) output.push(chunk)
  assert.equal(output.some(chunk=>chunk.type==='text-delta'),false)
  assert.deepEqual(output.at(-1)?.reason,{kind:'aborted',failure:{
    code:'REFRACTAGENT_EXECUTION_ABORTED',
    message:'RefractAgent 已停止：任务被取消或超时；请核对已保存的运行记录后再重试。',
  }})
})

test('strategy-scoped provider configuration passes through unchanged',async()=>{
  const f=fixture({billing_unit:'USD'})
  const config={...userConfiguration(),defaultReasoningEffort:'medium',
    strategies:{economy:{reasoningEffort:'low',models:['answer']},quality:{reasoningEffort:'high'}}}
  await chunks(createAdapter(f.ctx, () => configure({providerConfig:config})))
  assert.deepEqual(JSON.parse(f.spawns[0]!.input()).providerConfig,config)
})

test('invalid strategy or limits configuration is rejected at the host boundary',()=>{
  const base=userConfiguration()
  assert.throws(()=>configure({providerConfig:{...base,strategies:{turbo:{}}}}),/strategies/)
  assert.throws(()=>configure({providerConfig:{...base,strategies:{economy:{models:[]}}}}),/configured model ids/)
  assert.throws(()=>configure({providerConfig:{...base,strategies:{economy:{models:['missing']}}}}),/configured model ids/)
  assert.throws(()=>configure({providerConfig:{...base,strategies:{economy:{reasoningEffort:''}}}}),/reasoningEffort/)
  assert.throws(()=>configure({providerConfig:{...base,defaultReasoningEffort:17}}),/defaultReasoningEffort/)
  assert.throws(()=>configure({limits:{relaxBudget:'yes'}}),/limits/)
  assert.throws(()=>configure({limits:{unexpected:true}}),/limits/)
})

test('limit toggles reach Python and relaxed context accepts long conversations',async()=>{
  const long='x'.repeat(130000)
  await assert.rejects(async()=>{
    for await(const _ of createAdapter(fixture().ctx, () => configure()).stream({...options,system:long})){}
  },/too large/)
  await assert.rejects(async()=>{
    for await(const _ of createAdapter(fixture().ctx, () => configure({limits:{relaxBudget:true}})).stream({...options,system:long})){}
  },/too large/)
  const f=fixture({billing_unit:'USD'})
  for await(const _ of createAdapter(f.ctx, () => configure({limits:{relaxBudget:true,relaxContext:true}})).stream({...options,system:long})){}
  const payload=JSON.parse(f.spawns[0]!.input())
  assert.deepEqual(payload.limits,{relaxBudget:true,relaxContext:true})
  assert.ok(payload.context.length>130000)
})

test('adapter reads its configuration source on every call (mechanism for settings overrides)',async()=>{
  const f=fixture()
  let config=configure({maxOutputTokens:2048})
  const adapter=createAdapter(f.ctx,() => config)
  assert.equal((await adapter.resolveModel('refractagent','balanced')).defaultMaxTokens,2048)
  config=configure({maxOutputTokens:4096})
  assert.equal((await adapter.resolveModel('refractagent','balanced')).defaultMaxTokens,4096)
})
