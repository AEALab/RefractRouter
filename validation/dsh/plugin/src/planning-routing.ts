import { sessionEvents, type NativeAgent } from './native-tools.js'
/** DSH 只执行核心签发的单次模型调用；原生工具始终由宿主循环执行。 */
import { randomUUID } from 'node:crypto'
import { resolve } from 'node:path'
import type { AgentContext, Configuration, ModelOptions } from './agent-provider.js'
import type { LlmOptions, ProcessHandle, TokenUsage } from './contracts.js'

import { EMPTY_PLANNING, PLANNING_PROTOCOL } from './planning-config.js'
import { ToolEvidenceCapture } from './tool-evidence.js'
type Json=Record<string,any>
export interface PlanningRpc {request(value:Json):Promise<Json>;dispose():void}
export class PlanningWorker implements PlanningRpc {
  private handle?:ProcessHandle
  private starting?:Promise<void>
  private failure?:Error
  private lifecycle=new AbortController()
  private pending=new Map<string,{resolve:(v:Json)=>void;reject:(e:Error)=>void}>()
  constructor(private ctx:AgentContext,private source:()=>Readonly<Configuration>) {}
  dispose():void {this.lifecycle.abort();this.handle?.terminate?.();this.fail(new Error('规划路由进程已关闭'))}
  private fail(error:Error):void {this.failure=error;for(const p of this.pending.values())p.reject(error);this.pending.clear()}
  private async start():Promise<void> {
    const config=this.source(),env:Record<string,string>={PYTHONUNBUFFERED:'1'}
    for(const key of ['PATH','HOME','LANG','LC_ALL','TMPDIR','SYSTEMROOT']){
      if(process.env[key])env[key]=process.env[key]!
    }
    const executable=await this.ctx.subprocess.resolveExecutable(config.pythonExecutable,env,this.lifecycle.signal)
    const module=/(?:^|\/|\\)python(?:\d+(?:\.\d+)?)?(?:\.exe)?$/i.test(executable)
    const argv=[executable,...(module?['-m','refractrouter.agent_cli']:[]),'planning-worker','--runs-dir',resolve(config.runsDir)]
    const policy=this.ctx.sandboxPolicy.resolve({})
    this.handle=this.ctx.subprocess.spawn({argv:this.ctx.sandbox.confine(argv,policy).argv,
      cwd:policy.workspaceRoot,env,stdio:{stdin:'pipe',stdout:'pipe',stderr:{maxBytes:16384}},
      signal:this.lifecycle.signal,graceMs:2000})
    if(!this.handle.stdin||!this.handle.stdout)throw new Error('规划路由需要双向进程流')
    let buffer=''
    this.handle.stdout.setEncoding('utf8')
    this.handle.stdout.on('data',(part:string)=>{
      buffer+=part
      if(Buffer.byteLength(buffer)>32*1024*1024){this.dispose();return}
      let n:number
      while((n=buffer.indexOf('\n'))>=0){
        const line=buffer.slice(0,n);buffer=buffer.slice(n+1)
        try{
          const value=JSON.parse(line) as Json
          if(value.protocol!==PLANNING_PROTOCOL||typeof value.id!=='string')throw new Error('进程协议错误')
          const pending=this.pending.get(value.id)
          if(!pending)throw new Error('未知进程响应')
          this.pending.delete(value.id)
          if(value.ok)pending.resolve(value.result)
          else pending.reject(new Error(String(value.error??'规划路由失败')))
        }catch(error){this.fail(error instanceof Error?error:new Error(String(error)));this.handle?.terminate?.()}
      }
    })
    this.handle.stdin.on('error',(e:Error)=>this.fail(e))
    void this.handle.done.then(()=>this.fail(new Error('规划路由进程结束；未确认调用不得自动重发')),
      e=>this.fail(e instanceof Error?e:new Error(String(e))))
  }
  async request(value:Json):Promise<Json>{
    if(this.failure)throw this.failure
    this.starting??=this.start()
    await this.starting
    if(this.failure)throw this.failure
    const id=randomUUID(),line=JSON.stringify({protocol:PLANNING_PROTOCOL,id,...value})+'\n'
    if(Buffer.byteLength(line)>16*1024*1024)throw new Error('规划路由请求过大')
    return new Promise((resolve,reject)=>{
      const timeout=value.op==='local-judge'&&value.action==='download'?15*60*1000:30000
      const timer=setTimeout(()=>{
        this.fail(new Error('规划路由进程响应超时；不自动重新派发'));this.handle?.terminate?.()
      },timeout)
      this.pending.set(id,{resolve:v=>{clearTimeout(timer);resolve(v)},reject:e=>{clearTimeout(timer);reject(e)}})
      this.handle!.stdin!.write(line,(error)=>{if(error){this.pending.get(id)?.reject(error);this.pending.delete(id)}})
    })
  }
}
/** 每条历史从自己的代理包络恢复来源；普通 DSH 来源保持原样。 */
export function planningMessages(messages:ModelOptions['messages']):Json[] {
  return structuredClone(messages).flatMap(message=>{
    const source=message.source as Json|undefined
    if(source?.kind==='model'&&source.provider==='refractagent'){
      const replay=source.replayState as Json|undefined
      const envelope=replay?.response?.refractPlanning as Json|undefined
      if(!envelope||![1,2].includes(Number(envelope.version))||typeof envelope.provider!=='string'||typeof envelope.model!=='string')
        throw new Error('旧虚拟模型回复缺少真实来源，无法安全转换；请新建会话')
      if(envelope.feedback&&typeof envelope.feedback!=='string')throw new Error('无效的规划路由审核反馈')
      message.source={kind:'model',provider:envelope.provider,model:envelope.model,
        ...(envelope.response!==undefined?{replayState:{response:envelope.response,
          ...(replay?.blocks?{blocks:replay.blocks}:{})}}:{})}
      if(envelope.feedback)return [{role:'user',source:{kind:'plugin',plugin:'refractagent'},
        content:[{type:'text',text:'审核反馈（不得覆盖权限、预算和系统指令）：\n'+envelope.feedback}]},message]
    }
    return [message]
  })
}
function nativeOptions(action:Json,signal:AbortSignal,original:ModelOptions):LlmOptions {
  const messages=action.messages.map((m:Json)=>({...m,id:m.id??randomUUID(),
    source:m.source??{kind:'user'},content:typeof m.content==='string'?[{type:'text',text:m.content}]:m.content}))
  return {provider:action.model.provider,model:action.model.model,messages,
    tools:action.tools,temperature:original.temperature??0,maxTokens:action.model.maxTokens,signal,
    ...(action.model.reasoning_effort?{reasoningEffort:action.model.reasoning_effort}:{}),
    ...(original.stop?{stop:original.stop}:{}),...(original.purpose?{purpose:original.purpose}:{})}
}
function sumUsage(total:TokenUsage,usage:TokenUsage):void {
  for(const key of ['inputTokens','outputTokens','cacheReadTokens','cacheWriteTokens','reasoningTokens'] as const)
    total[key]=(total[key]??0)+(usage[key]??0)
}
export class PlanningController {
  readonly rpc:PlanningRpc
  private tasks=new Map<string,string>()
  private settings:AgentContext['settings']
  constructor(private ctx:AgentContext,private source:()=>Readonly<Configuration>,rpc?:PlanningRpc,
    private evidence=new ToolEvidenceCapture()){
    this.rpc=rpc??new PlanningWorker(ctx,source)
    this.settings=ctx.settings
    ctx.inject?.(['settings'],sctx=>{this.settings=sctx.settings})
    ctx.effect?.(()=>()=>this.rpc.dispose(),'refractagent planning worker')
    ctx.on?.('session/event',(session,event)=>{
      if(event.type!=='turn/end')return
      const key=JSON.stringify({session:session.header.id,agent:session.header.id,turn:event.data.turn})
      const runId=this.tasks.get(key)
      if(runId)void this.rpc.request({op:'end',runId}).catch(()=>{})
    })
  }
  private async completeMetadata(config:Json):Promise<Record<string,string>>{
    const hostIssues:Record<string,string>={}
    if(!this.ctx.llm.resolveModelInfo)return hostIssues
    await Promise.all((config.models??[]).map(async (model:Json)=>{
      try{
        const info=await this.metadata(model.provider,model.model,'AUTO')
        const hostModel=await this.ctx.llm.resolveModelInfo!(model.provider,model.model) as Json
        const reasoning=hostModel.reasoning as Json|undefined
        const efforts=Array.isArray(reasoning?.efforts)
          ?reasoning.efforts.map((entry:Json)=>entry.id).filter((id:unknown):id is string=>typeof id==='string')
          :[]
        if(model.reasoningEffort){
          if(!efforts.includes(model.reasoningEffort)){
            hostIssues[model.id]=`目标模型不支持推理等级 ${model.reasoningEffort}`
            return
          }
        }else if(efforts.length){
          model.reasoningEffort=typeof reasoning?.defaultEffort==='string'
            ?reasoning.defaultEffort:efforts[0]
        }else{
          // DSH 通用模型层不接受未声明的 off；pi-ai 又会继承 provider 默认档位。
          const llmSettings=this.settings?.get?.('llm-pi-ai') as Json|undefined
          const provider=(llmSettings?.providers as Json|undefined)?.[model.provider] as Json|undefined
          if(typeof provider?.reasoning==='string'){
            hostIssues[model.id]=`DSH 模型未声明推理等级，且 provider 默认 ${provider.reasoning}；请先补齐模型能力`
            return
          }
        }
        // Python 已识别实际 Ark Agent Plan 端点；旧配置中的手填价格不能覆盖单位冲突。
        const unitIssue=Array.isArray(info.issues)?info.issues.find((issue:unknown)=>
          typeof issue==='string'&&issue.includes('Ark Agent Plan 按 AFP 计量')):undefined
        if(unitIssue){hostIssues[model.id]=unitIssue;return}
        if(info.billingUnit==='AFP'||info.billingUnit==='CNY'){
          model.billingUnit=info.billingUnit
          if(config.schemaVersion==='refractagent-planning-v1')config.schemaVersion='refractagent-planning-v2'
        }
        if(info.capacity)for(const key of ['contextWindow','maxOutputTokens']){
          const value=info.capacity[key]
          if(Number.isInteger(value)&&value>0)model[key]=value
        }
        if(info.capabilities&&typeof info.capabilities==='object')model.capabilities=info.capabilities
        if(info.pricing)for(const key of ['inputPer1k','outputPer1k','cachedInputPer1k']){
          const value=info.pricing[key]
          if(typeof value==='number'&&Number.isFinite(value)&&value>=0)model[key]=value
        }
        if((typeof model.inputPer1k!=='number'||!Number.isFinite(model.inputPer1k)
            ||typeof model.outputPer1k!=='number'||!Number.isFinite(model.outputPer1k))
            &&Array.isArray(info.issues)){
          const reason=info.issues.find((issue:unknown)=>typeof issue==='string'&&issue.includes('价格'))
          if(reason)hostIssues[model.id]=reason
        }
      }catch{hostIssues[model.id]='目标模型不能解析或资料查询失败'}
    }))
    return hostIssues
  }
  async preview():Promise<Json>{
    const config=structuredClone(this.source().planningRouting??EMPTY_PLANNING)
    const hostIssues=await this.completeMetadata(config)
    return this.rpc.request({op:'preview',config,hostIssues})
  }
  async simulate():Promise<Json>{
    const config=structuredClone(this.source().planningRouting??EMPTY_PLANNING)
    await this.completeMetadata(config)
    return this.rpc.request({op:'simulate',config})
  }
  async metadata(provider:string,model:string,billingUnit:string):Promise<Json>{
    if(!this.ctx.llm.resolveModelInfo)throw new Error('DSH 不提供模型资料查询')
    const raw=await this.ctx.llm.resolveModelInfo(provider,model) as Json
    const context=raw.context as Json|undefined
    const llmSettings=this.settings?.get?.('llm-pi-ai') as Json|undefined
    const route=llmSettings?.providers?.[provider] as Json|undefined
    return this.rpc.request({op:'metadata',provider,model,billingUnit,host:{
      contextWindow:context?.contextWindow,maxOutputTokens:raw.defaultMaxTokens,
      inputModalities:Array.isArray(raw.inputModalities)?raw.inputModalities:undefined,
    },providerBaseURL:route?.baseURL})
  }
  async fx():Promise<Json>{return this.rpc.request({op:'fx'})}
  async localJudge(config:Json,action:'status'|'download'|'load'|'unload'):Promise<Json>{
    return this.rpc.request({op:'local-judge',config,action,confirmed:action==='download'})
  }
  async history(session:string):Promise<Json>{return this.rpc.request({op:'history',session})}
  private runForAgent(agent:NativeAgent):string{
    const event=[...sessionEvents(agent)].reverse().find(item=>item.type==='step/start'||item.type==='turn/end')
    const session=agent.session.header?.id,agentId=agent.id,turn=event?.data.turn
    if(!session||!agentId||typeof turn!=='number')throw new Error('媒体工具缺少可信任务身份')
    const runId=this.tasks.get(JSON.stringify({session,agent:agentId,turn}))
    if(!runId)throw new Error('媒体工具只能在已启动的规划路由任务中使用')
    return runId
  }
  async reserveMedia(agent:NativeAgent,input:Json):Promise<Json>{
    return this.rpc.request({op:'media-reserve',runId:this.runForAgent(agent),...input})
  }
  async updateMedia(agent:NativeAgent,input:Json):Promise<Json>{
    return this.rpc.request({op:'media-update',runId:this.runForAgent(agent),...input})
  }
  async mediaCredential(provider:string):Promise<string>{
    if(!/^[A-Za-z0-9._-]{1,128}$/.test(provider))throw new Error('媒体凭证 provider ID 无效')
    const settings=this.settings?.get?.('llm-pi-ai') as Json|undefined
    const route=(settings?.providers as Json|undefined)?.[provider] as Json|undefined
    const reference=typeof route?.apiKeyEnv==='string'&&route.apiKeyEnv
      ?route.apiKeyEnv:`llm-pi-ai/${provider}`
    const credential=await this.ctx.credentials.resolve(reference)
    if(!credential?.value)throw new Error(`媒体路线 ${provider} 的 DSH 凭证不可用；请为该 provider 登录或登记 apiKeyEnv`)
    return credential.value
  }
  async *stream(options:ModelOptions):AsyncGenerator<Record<string,unknown>> {
    if(!this.ctx.llm.stream||!this.ctx.agents)throw new Error('规划路由需要 DSH 原生模型与 Agent 服务')
    const agent=this.ctx.agents.requireInitiator()
    const session=agent.session.header?.id,agentId=agent.id
    const event=[...sessionEvents(agent)].reverse().find(e=>e.type==='step/start'||e.type==='turn/end'
      ||(options.purpose==='compaction'&&e.type==='compaction/start'))
    const standalone=options.purpose==='compaction'&&event?.type==='compaction/start'&&event.data.turn===null
    const turn=standalone?'compaction:'+String(event?.data.compactionId):event?.data.turn
    if(!session||!agentId||!['step/start','compaction/start'].includes(event?.type??'')||(!standalone&&typeof turn!=='number')
      ||(options.sessionId&&options.sessionId!==session))throw new Error('缺少可信的会话、Agent 或轮次身份')
    if(options.purpose&&options.purpose!=='compaction')throw new Error('会话命名需配置普通 DSH 模型')
    const identity={session,agent:agentId,turn}
    const key=JSON.stringify(identity)
    const config=structuredClone(this.source().planningRouting??EMPTY_PLANNING)
    // 会话菜单选择优先；未选择时使用插件设置默认值。物理模型推理等级由角色配置决定。
    const strategy=options.reasoningEffort?.startsWith('rr:')?options.reasoningEffort.slice(3):config.defaultStrategy
    if(options.reasoningEffort&&!options.reasoningEffort.startsWith('rr:'))
      throw new Error('规划路由选择值必须使用 rr: 策略标识')
    const cancelled=new AbortController()
    const signal=AbortSignal.any([cancelled.signal,...(options.signal?[options.signal]:[])])
    let runId=this.tasks.get(key),done=false
    try{
      signal.throwIfAborted()
      if(!runId){
        const hostIssues=await this.completeMetadata(config)
        const started=await this.rpc.request({op:'begin',identity,config,strategy,hostIssues,
          child:agent.session.header?.origin==='subagent'})
        runId=String(started.runId);this.tasks.set(key,runId)
        if(this.ctx.llm.resolveModelInfo)for(const route of started.models??[])
          await this.ctx.llm.resolveModelInfo(route.provider,route.model)
      }
      const messages=planningMessages(options.messages)
      if(options.system)messages.unshift({role:'system',content:options.system})
      const nativeEvents=sessionEvents(agent)
        .filter(e=>(e.type==='tool/result'||e.type==='tool/call'||e.type==='compaction/end')&&e.data.turn===turn)
        .map(e=>({type:e.type,data:e.data}))
      let action=await this.rpc.request({op:'step',runId,messages,tools:options.tools??[],
        requestId:randomUUID(),maxTokens:options.maxTokens,purpose:options.purpose,
        events:this.evidence.enrich(session,nativeEvents)})
      const outputs=new Map<string,{chunks:Json[];finish:Json;model:Json;buffered:boolean}>()
      const total:TokenUsage={}
      while(action.action==='call'){
        signal.throwIfAborted()
        const callSignal=action.remainingMs===null?signal:AbortSignal.any([signal,AbortSignal.timeout(Math.max(1,action.remainingMs))])
        const chunks:Json[]=[],blocks=new Map<number,Json>()
        let content='',usage:TokenUsage|undefined,finish:Json|undefined,bytes=0,ttftMs:number|undefined
        const started=performance.now()
        let streamError:unknown
        try{for await(const native of this.ctx.llm.stream(nativeOptions(action,callSignal,options))){
          callSignal.throwIfAborted()
          const chunk=native as Json
          bytes+=Buffer.byteLength(JSON.stringify(chunk))
          if(bytes>8*1024*1024)throw new Error('规划路由回复缓冲超过 8 MiB')
          if(chunk.type==='usage'){usage=chunk.usage as TokenUsage;continue}
          if(chunk.type==='finish'){finish=chunk;continue}
          if(finish)throw new Error('模型 finish 后继续输出')
          if(chunk.type==='text-delta'){content+=String(chunk.text);ttftMs??=performance.now()-started}
          if(chunk.type==='block-end')blocks.set(chunk.index,chunk.block)
          chunks.push(chunk)
          if(!action.buffered)yield chunk
        }}catch(error){streamError=error}
        if(!streamError&&finish?.reason?.kind==='error'){
          const failure=finish.reason.failure as Json|undefined
          streamError=new Error('底层模型调用失败'+(failure?.code?'（'+String(failure.code)+'）':'')+
            (failure?.message?'：'+String(failure.message).slice(0,500):''))
        }
        if(!streamError&&!finish)streamError=new Error('底层模型没有返回完成回执；用量待核对')
        if(streamError||callSignal.aborted){
          await this.rpc.request({op:'cancel',runId})
          if(streamError)throw streamError
          callSignal.throwIfAborted()
        }
        const tools=[...blocks.values()].filter(b=>b.type==='tool-call')
        if(!content)content=[...blocks.values()].filter(b=>b.type==='text').map(b=>b.text).join('')
        if(usage)sumUsage(total,usage)
        outputs.set(action.callId,{chunks,finish:finish??{},model:action.model,buffered:action.buffered})
        action=await this.rpc.request({op:'complete',runId,callId:action.callId,response:{
          content,toolCalls:tools,finishReason:finish?.reason?.kind==='tool-calls'?'tool_calls':finish?.reason?.kind,
          usageAvailable:!!usage&&typeof usage.inputTokens==='number'&&typeof usage.outputTokens==='number',
          inputTokens:(usage?.inputTokens??0)+(usage?.cacheReadTokens??0)+(usage?.cacheWriteTokens??0),
          cacheWriteTokens:usage?.cacheWriteTokens??0,ttftMs,replayState:finish?.replayState,
          cachedInputTokens:usage?.cacheReadTokens??0,outputTokens:usage?.outputTokens??0,
          reasoningTokens:usage?.reasoningTokens??0,latencyMs:performance.now()-started}})
        callSignal.throwIfAborted()
      }
      signal.throwIfAborted()
      if(action.action!=='release')throw new Error('核心没有接受回复')
      const accepted=outputs.get(action.callId)
      if(!accepted)throw new Error('已接受回复不属于当前请求')
      if(accepted.buffered)for(const chunk of accepted.chunks){signal.throwIfAborted();yield chunk}
      yield {type:'usage',usage:total}
      const replay=accepted.finish.replayState as Json|undefined
      done=true
      if(standalone)await this.rpc.request({op:'end',runId})
      yield {...accepted.finish,type:'finish',replayState:{response:{refractPlanning:{
        version:2,contentContract:'dsh-content-blocks-v1',provider:accepted.model.provider,model:accepted.model.model,
        ...(replay?{response:replay.response}:{}),...(action.feedback?{feedback:action.feedback}:{}),runId}},...(replay?.blocks?{blocks:replay.blocks}:{})}}
    }finally{
      cancelled.abort()
      if(runId&&!done)await this.rpc.request({op:'cancel',runId}).catch(()=>{})
    }
  }
}
