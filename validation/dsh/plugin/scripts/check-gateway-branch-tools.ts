/** DSH 真实客户端的策略关键分支验收；工具仍由 DSH 执行。 */
import assert from 'node:assert/strict'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

const [modules, baseURL, outputLimit, strategy, repeatsText='1'] = process.argv.slice(2)
if (!modules || !baseURL) throw new Error('需要 DSH node_modules 和本地网关 Base URL')
if (!['stage', 'composite', 'advisor', 'escalation'].includes(strategy))
  throw new Error('未知关键分支策略')
const repeats = Number(repeatsText)
if (!Number.isSafeInteger(repeats) || repeats < 1 || repeats > 10) throw new Error('重复次数必须为 1—10')
const maxTokens = outputLimit ? Number(outputLimit) : 256
const virtualModel = `refract/${strategy}`
const load = (name:string) => import(pathToFileURL(resolve(modules, '@deepseek-ai', name, 'lib/index.js')).href)
const { Context } = await load('cordis')
const { Session } = await load('dsh-session')
const { SystemPrompt } = await load('dsh-system-prompt')
const { ToolRuntime } = await load('dsh-tools')
const { DeepSeekAdapter, resolveAdapterOptions } = await load('dsh-llm-deepseek')

const connection = resolveAdapterOptions({baseURL, maxTokens,
  models:[{id:virtualModel, contextWindow:1000000}],
  retryPolicy:{mode:'normal', maxRetries:0}})
const adapter = new DeepSeekAdapter({options:()=>connection,
  resolveApiKey:async()=> 'local-branch-acceptance', resolveUserId:()=> 'local-branch-acceptance',
  prepareExtensions:async()=>({fields:{}, accept:async()=>{}})})

async function postEvidence(callId:string, status:'failed'|'completed', fingerprint:string) {
  const root = baseURL.replace(/\/$/, '')
  const response = await fetch(root + '/tool-evidence', {method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({version:'refract-tool-evidence-v1', callId, status, kind:'unknown', fingerprint})})
  if (!response.ok) throw new Error(`工具证据提交失败：${String(response.status)}`)
}

const summaries:any[] = []
for (let iteration=1; iteration<=repeats; iteration++) {
  const ctx = new Context()
  new SystemPrompt(ctx, {})
  new ToolRuntime(ctx)
  let probes = 0
  let echoes = 0
  ctx.tools.register({name:'refract_branch_probe', description:'执行受控的四步宿主探针',
    parameters:{type:'object', properties:{}, additionalProperties:false},
    output:{schema:{type:'string'}, render:(_args:unknown, value:string)=>[{type:'text', text:value}]},
    execute:async()=> {
      probes++
      return probes <= 2 ? `CONTROLLED_FAILURE_${String(probes)}；请继续调用探针。`
        : probes < 4 ? `CONTROLLED_SUCCESS_${String(probes)}；请继续调用探针。`
        : 'CONTROLLED_SUCCESS_4；现在只回答 BRANCH_OK。'
    }})
  ctx.tools.register({name:'refract_branch_echo', description:'返回关键分支验收标记',
    parameters:{type:'object', properties:{}, additionalProperties:false},
    output:{schema:{type:'string'}, render:(_args:unknown, value:string)=>[{type:'text', text:value}]},
    execute:async()=> { echoes++; return 'REFRACT_HOST_TOOL_OK；现在只回答 BRANCH_OK。' }})
  const session = Session.create(`branch-${strategy}-${String(iteration)}`)
  const agent = {ctx, session}
  const prompt = strategy === 'stage' || strategy === 'composite'
    ? '依次调用 refract_branch_probe。每次只调用一次；即使失败也继续，直到第四次结果要求结束，随后只回答 BRANCH_OK。'
    : '必须调用 refract_branch_echo 一次；收到 REFRACT_HOST_TOOL_OK 后只回答 BRANCH_OK。不得在工具执行前声称完成。'
  const messages:any[] = [{id:'user', role:'user', source:{kind:'user'},
    content:[{type:'text', text:prompt}]}]
  let requests = 0
  let text = ''
  const maximumRequests = strategy === 'stage' || strategy === 'composite' ? 6 : 3
  for (let step=1; step<=maximumRequests; step++) {
    session.append('step/start', {turn:1, step})
    const chunks:any[] = []
    for await (const chunk of adapter.stream({provider:'refract-http', model:virtualModel, messages,
      tools:ctx.tools.schemas(), sessionId:session.header.id, signal:AbortSignal.timeout(120000)})) chunks.push(chunk)
    requests++
    const blocks = chunks.filter(c=>c.type==='block-end').map(c=>c.block)
    const finish = chunks.find(c=>c.type==='finish')
    assert.ok(finish)
    const assistant = {id:`assistant-${String(step)}`, role:'assistant',
      source:{kind:'model', provider:'refract-http', model:virtualModel,
        ...(finish.replayState ? {replayState:finish.replayState} : {})}, content:blocks}
    messages.push(assistant)
    session.append('assistant/message', {turn:1, step, message:assistant, stream:[]}, {surfaceOp:'append'})
    const calls = blocks.filter((b:any)=>b.type==='tool-call')
    for (const call of calls) {
      const expected = strategy === 'stage' || strategy === 'composite'
        ? 'refract_branch_probe' : 'refract_branch_echo'
      assert.equal(call.name, expected)
      session.append('tool/call', {turn:1, step, callId:call.id, name:call.name, arguments:call.arguments})
      const result = await ctx.tools.execute({callId:call.id, name:call.name,
        arguments:JSON.parse(call.arguments), agent, signal:new AbortController().signal})
      assert.equal(result.isError, false)
      const message = {id:`tool-${String(step)}`, role:'user', source:{kind:'tool', callId:call.id},
        content:[{type:'tool-result', toolCallId:call.id, content:result.content, isError:result.isError}]}
      messages.push(message)
      session.append('tool/result', {turn:1, step, message}, {surfaceOp:'append'})
      if (expected === 'refract_branch_probe') {
        const status = probes <= 2 ? 'failed' : 'completed'
        const fingerprint = probes <= 2 ? 'controlled-repeat-failure' : `controlled-success-${String(probes)}`
        await postEvidence(call.id, status, fingerprint)
      }
    }
    text = blocks.filter((b:any)=>b.type==='text').map((b:any)=>b.text).join('')
    if (text.includes('BRANCH_OK')) break
  }
  assert.match(text, /BRANCH_OK/)
  if (strategy === 'stage' || strategy === 'composite') assert.equal(probes, 4)
  else assert.equal(echoes, 1)
  summaries.push({iteration, requests, probes, echoes, final:'BRANCH_OK'})
}
console.log(JSON.stringify({client:'DSH', strategy, status:'pass', repeats, summaries}))
