/** node-as-tool 三路线研究的 DSH 个案宿主；策略、预算、评估均由 Python 管理。 */
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import net from 'node:net'
const [modules,executable,casePath,output,mode,approvedHash]=process.argv.slice(2)
if(!modules||!executable||!casePath||!output||!['--rehearse','--execute-paid-run'].includes(mode))
  throw new Error('需要 DSH 模块、Python、冻结个案、新证据目录及显式演练/付费模式')
const spec=JSON.parse(await readFile(casePath,'utf8'))
const live=mode==='--execute-paid-run'
const cli=JSON.parse(await readFile(resolve(modules,'../package.json'),'utf8'))
assert.equal(cli.version,spec.dshVersion,'DSH 版本与冻结清单不符')
if(live&&(!approvedHash||approvedHash!==spec.protocolSha256))throw new Error('未匹配明确批准的协议摘要')
await mkdir(output,{recursive:false})
const load=(name:string)=>import(pathToFileURL(resolve(modules,'@deepseek-ai',name,'lib/index.js')).href)
const {Context}=await load('cordis'),{Session}=await load('dsh-session')
const {ToolRuntime}=await load('dsh-tools'),{SystemPrompt}=await load('dsh-system-prompt')
const {LlmRuntime}=await load('dsh-llm'),{apply:piApply}=await load('dsh-llm-pi-ai')
const {PlanningController}=await import('../dist/planning-routing.js')
const {createAdapter,configure}=await import('../dist/agent-provider.js')
const {registerExperimentalNodeTools}=await import('../dist/node-tools.js')
let requests=0,unexpectedNetwork=0
const originalFetch=globalThis.fetch
const wireJobs:Promise<void>[]=[]
const scrub=(value:string)=>process.env.CODEX_ARK_API_KEY?value.split(process.env.CODEX_ARK_API_KEY).join('[已隐藏凭证]'):value
await mkdir(resolve(output,'wire'))
const safeRequest=(input:any)=>String(typeof input==='string'?input:input instanceof URL?input:input.url)
globalThis.fetch=async(input:any,init?:any)=>{
  const url=new URL(safeRequest(input))
  if(url.origin!=='https://ark.cn-beijing.volces.com'||url.pathname!=='/api/plan/v3/responses'){
    unexpectedNetwork++;throw new Error('研究入口拒绝非冻结模型端点')}
  const payload=JSON.parse(String(init?.body??''))
  assert.equal(payload.temperature,spec.sampling.temperature,'实际 DSH temperature 与冻结控制不符')
  if(spec.wireControls){
    const expert=JSON.stringify(payload).includes('你是文本专家')
    const binding=spec.nodeTools?.modelBindings
    const id=binding?.[expert?'expert':'main']??spec.planningConfig.roles.efficient
    const model=spec.planningConfig.models.find((m:any)=>m.id===id)
    assert.equal(payload.model,model.model,'实际主模型/专家独立选模不符')
    assert.equal(payload.max_output_tokens,model.maxOutputTokens,'实际输出容量与冻结模型不符')
    assert.equal(payload.top_p,undefined,'研究保持 top_p 提供方默认')
    assert.equal(payload.reasoning,undefined,'研究保持思考提供方默认')
    if(!live)await writeFile(resolve(output,'wire',String(requests+1).padStart(3,'0')+'-request.json'),
      scrub(String(init?.body??'')))
  }
  requests++
  if(requests>spec.maxModelCalls)throw new Error('宿主传输超过冻结模型调用数')
  if(live){
    const id=String(requests).padStart(3,'0')
    // 仅归档正文和非敏感关联 ID，不保存凭证头；clone 读取原请求的响应，不增加请求。
    await writeFile(resolve(output,'wire',id+'-request.json'),scrub(String(init?.body??'')))
    const response=await originalFetch(input,init)
    const job=response.clone().text().then(async body=>{
      await writeFile(resolve(output,'wire',id+'-response.txt'),scrub(body))
      await writeFile(resolve(output,'wire',id+'-receipt.json'),JSON.stringify({status:response.status,
        requestId:response.headers.get('x-request-id'),contentType:response.headers.get('content-type')}))
    })
    // 立即挂接异常处理，最终仍须确认归档全部成功，避免后台拒绝丢失证据。
    job.catch(()=>{});wireJobs.push(job)
    return response
  }
  const body=JSON.parse(init.body),all=JSON.stringify(body)
  const expert=all.includes('你是文本专家')
  const tools=body.tools??[]
  const prior=(body.input??[]).filter((i:any)=>i.type==='function_call_output').length
  const call=!expert&&tools.length>0&&prior<(spec.rehearsalExpertCalls??1)
  const content=expert?JSON.stringify({artifact:'离线中间产物，不构成真实能力证据',quotes:[],limitations:['模拟响应']}):
    JSON.stringify({answer:'离线交付，只验证协议与账本',findings:[]})
  const item=call?{type:'function_call',id:'fc-'+requests,call_id:'expert-'+requests,name:'refract_expert',
    arguments:JSON.stringify({intent:'analyze',task:'分析给定材料',context:'这是离线夹具材料。'})}:
    {type:'message',id:'msg-'+requests,role:'assistant',status:'completed',content:[{type:'output_text',text:content,annotations:[]}]}
  const events:any[]=[{type:'response.created',response:{id:'resp-'+requests,model:body.model,status:'in_progress',output:[]}},
    {type:'response.output_item.added',output_index:0,item:call?{...item,arguments:''}:{...item,content:[]}}]
  if(call)events.push({type:'response.function_call_arguments.delta',item_id:item.id,output_index:0,delta:item.arguments},
    {type:'response.function_call_arguments.done',item_id:item.id,output_index:0,arguments:item.arguments})
  else events.push({type:'response.content_part.added',item_id:item.id,output_index:0,content_index:0,
      part:{type:'output_text',text:'',annotations:[]}},
    {type:'response.output_text.delta',item_id:item.id,output_index:0,content_index:0,delta:content},
    {type:'response.output_text.done',item_id:item.id,output_index:0,content_index:0,text:content})
  events.push({type:'response.output_item.done',output_index:0,item},
    {type:'response.completed',response:{id:'resp-'+requests,model:body.model,status:'completed',output:[item],
      usage:{input_tokens:100,output_tokens:60,total_tokens:160,input_tokens_details:{cached_tokens:0},output_tokens_details:{reasoning_tokens:0}}}})
  return new Response(events.map(e=>'event: '+e.type+'\ndata: '+JSON.stringify(e)+'\n\n').join(''),{
    status:200,headers:{'content-type':'text/event-stream'}})
}
if(!live)net.Socket.prototype.connect=function(){unexpectedNetwork++;throw new Error('演练禁止实际套接字访问')} as any
const ctx=new Context();new SystemPrompt(ctx,{});new ToolRuntime(ctx);new LlmRuntime(ctx)
ctx.provide('credentials',{
  async resolve(ref:string){
    if(ref!=='CODEX_ARK_API_KEY')throw new Error('拒绝读取其他凭证')
    if(!live)return {value:'offline-fixture-not-a-secret',source:'env'}
    const value=process.env[ref];if(!value)throw new Error('缺少冻结凭证引用')
    return {value,source:'env'}
  },async describe(){return {configured:!live||!!process.env.CODEX_ARK_API_KEY}},
  async readRecord(){return undefined},async listRecords(){return []},
  async modifyRecord(){throw new Error('研究不写凭证')},async deleteRecord(){throw new Error('研究不删凭证')}
})
const provider=spec.provider
assert.equal(provider.baseURL,'https://ark.cn-beijing.volces.com/api/plan/v3')
assert.equal(provider.retryPolicy.maxRetries,0)
piApply(ctx,{providers:{[provider.id]:{api:provider.api,baseURL:provider.baseURL,apiKeyEnv:provider.credentialRef,retryPolicy:provider.retryPolicy,models:spec.planningConfig.models.map((m:any)=>({
  id:m.model,name:m.model,contextWindow:m.contextWindow,maxTokens:m.maxOutputTokens}))}}})
assert.equal(ctx.llm.providerRetryPolicy(provider.id).maxRetries,0)
const session=Session.create(spec.runId),agent={id:session.header.id,session,ctx}
const disposers:Array<()=>void>=[]
let workerStderr=''
const context:any={llm:ctx.llm,tools:ctx.tools,credentials:ctx.credentials,
  settings:{get:(key:string)=>key==='llm-pi-ai'?{providers:{[provider.id]:provider}}:undefined},agents:{requireInitiator:()=>agent},
  effect(setup:()=>()=>void){disposers.push(setup())},
  sandboxPolicy:{resolve:()=>({mode:'workspace-write',workspaceRoot:resolve(output)})},
  sandbox:{confine:(argv:string[])=>({argv,enforcement:'full'})},
  subprocess:{async resolveExecutable(){return executable},spawn(input:any){
    const child=spawn(input.argv[0],input.argv.slice(1),{cwd:input.cwd,env:input.env,stdio:'pipe',signal:input.signal})
    child.on('error',()=>{});child.stderr.on('data',(part:Buffer)=>{if(workerStderr.length<16384)workerStderr+=part.toString()})
    const done=new Promise(done=>child.once('exit',(exitCode,signal)=>done({exitCode,signal})))
    return {stdin:child.stdin,stdout:child.stdout,done,waitForExit:()=>done,terminate:()=>child.kill(),collected:{}}
  }}}
const config=configure({pythonExecutable:executable,runsDir:'evidence',planningRouting:spec.planningConfig})
const planning=new PlanningController(context,()=>config)
planning.setCallInputLimit(spec.inputLimit)
const adapter=createAdapter(context,()=>config,undefined,planning)
const messages:any[]=[{id:spec.runId,role:'user',source:{kind:'user'},
  content:[{type:'text',text:JSON.stringify(spec.payload)}]}]
const caseSignal=spec.timeoutMs>0?AbortSignal.timeout(spec.timeoutMs):new AbortController().signal
let runId:string|undefined,finished=false,outputText='',expertCalls=0
let entered=0
try{
  const hello=await planning.rpc.request({op:'handshake'})
  assert.ok(hello.capabilities?.includes('call-input-limit-v1'),'Python 核心没有冻结调用输入上限能力')
  if(spec.nodeTools?.modelBindings)assert.ok(hello.capabilities?.includes('node-tool-model-bindings-v1'),
    'Python 核心没有主模型和专家独立绑定能力')
  if(spec.nodeTools)disposers.push(await registerExperimentalNodeTools(context,planning,spec.nodeTools,()=>ctx.tools.schemas()))
  entered=performance.now()
  for(let step=1;step<=spec.maxMainCalls;step++){
    session.append('step/start',{turn:1,step})
    const chunks:any[]=[]
    for await(const c of adapter.stream({provider:'refractagent',model:'planning',reasoningEffort:'rr:static',
      system:spec.system,sessionId:session.header.id,messages,tools:ctx.tools.schemas(),signal:caseSignal}))chunks.push(c)
    const blocks=chunks.filter(c=>c.type==='block-end').map(c=>c.block),finish=chunks.find(c=>c.type==='finish')
    assert.ok(finish);runId=finish.replayState?.response?.refractPlanning?.runId
    const assistant={id:'assistant-'+step,role:'assistant',source:{kind:'model',provider:'refractagent',model:'planning',
      replayState:finish.replayState},content:blocks}
    messages.push(assistant);session.append('assistant/message',{turn:1,step,message:assistant,stream:[]},{surfaceOp:'append'})
    const calls=blocks.filter((b:any)=>b.type==='tool-call')
    if(!calls.length){outputText=blocks.filter((b:any)=>b.type==='text').map((b:any)=>b.text).join('');finished=true;break}
    for(const call of calls){
      assert.equal(call.name,'refract_expert')
      session.append('tool/call',{turn:1,step,callId:call.id,name:call.name,arguments:call.arguments})
      const result=await ctx.tools.execute({callId:call.id,name:call.name,arguments:JSON.parse(call.arguments),agent,
        signal:caseSignal})
      expertCalls++
      const message={id:'tool-'+call.id,role:'user',source:{kind:'tool',callId:call.id},content:[{
        type:'tool-result',toolCallId:call.id,content:result.content,isError:result.isError}]}
      messages.push(message);session.append('tool/result',{turn:1,step,message,
        ...(result.error?.info?{error:result.error.info}:{})},{surfaceOp:'append'})
      if(result.isError)throw new Error('专家调用失败；保留已执行费用，不自动重试')
    }
  }
  if(!finished)throw new Error('主循环调用数耗尽，未取得最终交付')
  assert.ok(runId);await planning.rpc.request({op:'end',runId})
  const record=await planning.rpc.request({op:'query',runId})
  assert.equal(record.status,'completed');assert.equal(record.callInputLimit,spec.inputLimit);assert.ok(record.calls.every((c:any)=>c.status==='billed'))
  assert.equal(record.calls.length,requests)
  await writeFile(resolve(output,'result.json'),JSON.stringify({status:'completed',simulated:!live,output:outputText,
    requests,expertCalls,taskElapsedMs:performance.now()-entered,unexpectedNetwork,
    transport:'DSH LlmRuntime + 官方 PiAiAdapter + /api/plan/v3/responses',recordPath:record.resultPath},null,2))
}catch(error){
  if(runId)await planning.rpc.request({op:'cancel',runId}).catch(()=>{})
  await writeFile(resolve(output,'failure.json'),JSON.stringify({error:String(error),requests,live},null,2))
  throw error
}finally{
  await Promise.all(wireJobs)
  await writeFile(resolve(output,'worker-stderr.log'),workerStderr)
  await writeFile(resolve(output,'session-events.json'),JSON.stringify(session.snapshotEvents(),null,2))
  for(const dispose of disposers.reverse())dispose()
}
