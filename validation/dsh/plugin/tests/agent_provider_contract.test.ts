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
          billing_unit:'AFP',result_path:'/tmp/agent-contract/runs/id/result.json',run_id:'id',...result }
        return {stdin,done:Promise.resolve({exitCode:0,signal:null}),async waitForExit(){},
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
  assert.deepEqual(result.at(-1)?.reason,{kind:'stop'})
  assert.equal(result.filter(c=>c.type==='finish').length,1)
  assert.equal(result.find(c=>c.type==='text-delta')?.text,'[SIMULATED] answer')
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
