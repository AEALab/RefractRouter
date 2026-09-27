/** 原生 DSH 标准适配器经 Base URL 调用独立网关；不导入 RefractAgent 插件。 */
import assert from 'node:assert/strict'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
const [modules,baseURL,outputLimit,strategy='static']=process.argv.slice(2)
if(!['static','stage'].includes(strategy))throw new Error('验收策略只支持 Static 或 Stage')
const virtualModel=`refract/${strategy}`
const maxTokens=outputLimit?Number(outputLimit):256
if(!modules||!baseURL)throw new Error('需要 DSH node_modules 和本地网关 Base URL')
const load=(name:string)=>import(pathToFileURL(resolve(modules,'@deepseek-ai',name,'lib/index.js')).href)
const {Context}=await load('cordis')
const {Session}=await load('dsh-session')
const {SystemPrompt}=await load('dsh-system-prompt')
const {ToolRuntime}=await load('dsh-tools')
const {DeepSeekAdapter,resolveAdapterOptions}=await load('dsh-llm-deepseek')
const ctx=new Context();new SystemPrompt(ctx,{});new ToolRuntime(ctx)
let executed=0
ctx.tools.register({name:'refract_local_echo',description:'返回本地验收标记',
 parameters:{type:'object',properties:{},additionalProperties:false},
 output:{schema:{type:'string'},render:(_args:unknown,v:string)=>[{type:'text',text:v}]},
 execute:async()=>{executed++;return 'REFRACT_HOST_TOOL_OK'}})
const connection=resolveAdapterOptions({baseURL,maxTokens,models:[{id:virtualModel,contextWindow:1000000}],retryPolicy:{mode:"normal",maxRetries:0}})
const adapter=new DeepSeekAdapter({options:()=>connection,resolveApiKey:async()=>'local-fixture',
 resolveUserId:()=>'local-fixture',prepareExtensions:async()=>({fields:{},accept:async()=>{}})})
const session=Session.create('base-url-contract');const agent={ctx,session}
const messages:any[]=[{id:'user',role:'user',source:{kind:'user'},content:[{type:'text',text:'调用 refract_local_echo 一次，收到 REFRACT_HOST_TOOL_OK 后回答 GATEWAY_CLIENT_OK。'}]}]
let requests=0,text=''
for(let step=1;step<=2;step++){
 session.append('step/start',{turn:1,step})
 const chunks:any[]=[]
 for await(const chunk of adapter.stream({provider:'refract-http',model:virtualModel,messages,
   tools:ctx.tools.schemas(),sessionId:session.header.id,signal:AbortSignal.timeout(30000)}))chunks.push(chunk)
 requests++
 const blocks=chunks.filter(c=>c.type==='block-end').map(c=>c.block)
 const finish=chunks.find(c=>c.type==='finish');assert.ok(finish)
 const assistant={id:'assistant-'+step,role:'assistant',source:{kind:'model',provider:'refract-http',model:virtualModel,...(finish.replayState?{replayState:finish.replayState}:{})},content:blocks}
 messages.push(assistant)
 session.append('assistant/message',{turn:1,step,message:assistant,stream:[]},{surfaceOp:'append'})
 for(const call of blocks.filter((b:any)=>b.type==='tool-call')){
  assert.equal(call.name,'refract_local_echo')
  session.append('tool/call',{turn:1,step,callId:call.id,name:call.name,arguments:call.arguments})
  const result=await ctx.tools.execute({callId:call.id,name:call.name,arguments:JSON.parse(call.arguments),agent,signal:new AbortController().signal})
  assert.equal(result.isError,false)
  const message={id:'tool-'+step,role:'user',source:{kind:'tool',callId:call.id},content:[{type:'tool-result',toolCallId:call.id,content:result.content,isError:result.isError}]}
  messages.push(message);session.append('tool/result',{turn:1,step,message},{surfaceOp:'append'})
 }
 text=blocks.filter((b:any)=>b.type==='text').map((b:any)=>b.text).join('')
}
assert.equal(executed,1);assert.match(text,/GATEWAY_CLIENT_OK/)
console.log(JSON.stringify({client:'DSH',status:'pass',requests,hostTools:executed,refractPluginLoaded:false}))
