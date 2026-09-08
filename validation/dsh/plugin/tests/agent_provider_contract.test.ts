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
  await chunks(createAdapter(f.ctx,configure({executionMode:'live',allowPaidRuns:true,maxProductionCost:7,maxEvaluationCost:9})))
  assert.equal(f.credentials,1)
  assert.deepEqual(f.credentialReferences,['CODEX_ARK_API_KEY'])
  const spawn=f.spawns[0]!
  assert.ok(spawn.argv.includes('--execute-paid-run'));assert.ok(spawn.argv.includes('7'));assert.ok(spawn.argv.includes('9'))
  assert.equal(spawn.env.CODEX_ARK_API_KEY,'private-test-key')
  assert.ok(!spawn.argv.join(' ').includes('private-test-key'))
  const custom=fixture({mode:'live',simulated:false,status:'completed'})
  await chunks(createAdapter(custom.ctx,configure({executionMode:'live',allowPaidRuns:true,credentialEnv:'TEAM_ARK_KEY'})))
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
  await assert.rejects(async()=>{for await(const _ of createAdapter(f.ctx,configure({executionMode:'live',allowPaidRuns:true})).stream({...options,signal:controller.signal})){}},/cancelled/)
  assert.equal(f.credentials,0)
  assert.equal(f.spawns.length,0)
})
