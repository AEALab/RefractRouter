/** 宿主只读事实适配：固定清单、可信身份和进程边界；提取与断言规则全部在 Python。 */
import { resolve } from 'node:path'
import schemas from './readonly-facts-tools.json' with { type: 'json' }
import type { AgentContext, Configuration } from './agent-provider.js'
import { sessionEvents, type NativeAgent } from './native-tools.js'
import type { ProcessHandle } from './contracts.js'
import { CORE_RUNTIME_ENV,installedCoreCommand } from './core-command.js'

type Json=Record<string,any>
export interface FactToolsConfig {enabled:boolean;manifestPath:string;manifestSha256:string}
interface Session {config:FactToolsConfig;receipts:Json[];pending:number}
function object(value:unknown):value is Json{return value!==null&&typeof value==='object'&&!Array.isArray(value)}
export function validateFactTools(value:unknown):asserts value is FactToolsConfig{
  if(!object(value)||Object.keys(value).some(k=>!['enabled','manifestPath','manifestSha256'].includes(k))
    ||typeof value.enabled!=='boolean'||typeof value.manifestPath!=='string'||!value.manifestPath.trim()
    ||typeof value.manifestSha256!=='string'||!/^[0-9a-f]{64}$/.test(value.manifestSha256))
    throw new Error('只读事实工具需要 enabled、固定清单路径和 SHA-256')
}
export class ReadonlyFactTools {
  private sessions=new Map<string,Session>()
  constructor(private ctx:AgentContext,private source:()=>Readonly<Configuration>){
    ctx.on?.('session/event',(session,event)=>{
      if(event.type==='turn/end')for(const key of this.sessions.keys()){
        const owner=JSON.parse(key) as Json
        if(owner.session===session.header.id&&owner.turn===event.data.turn)this.sessions.delete(key)
      }
    })
  }
  private owner(agent:NativeAgent):Json{
    const event=[...sessionEvents(agent)].reverse().find(e=>e.type==='step/start'||e.type==='turn/end')
    if(!agent.id||!agent.session.header?.id||event?.type!=='step/start'||typeof event.data.turn!=='number')
      throw new Error('事实工具需要可信的当前宿主任务身份')
    return {session:agent.session.header.id,agent:agent.id,turn:event.data.turn}
  }
  private active(owner:Json):Session{
    const config=this.source().factTools
    if(!config?.enabled)throw new Error('只读事实工具未启用')
    const key=JSON.stringify(owner),existing=this.sessions.get(key)
    if(existing){
      if(JSON.stringify(existing.config)!==JSON.stringify(config))throw new Error('任务中的事实清单配置已冻结')
      return existing
    }
    if(this.sessions.size>=128)throw new Error('事实工具宿主会话容量已满')
    const created={config:structuredClone(config),receipts:[],pending:0}
    this.sessions.set(key,created);return created
  }
  private async call(config:FactToolsConfig,agent:NativeAgent,request:Json,signal:AbortSignal):Promise<Json>{
    const started=performance.now()
    const env:Record<string,string>={...CORE_RUNTIME_ENV}
    for(const key of ['PATH','HOME','LANG','LC_ALL','TMPDIR','SYSTEMROOT'])if(process.env[key])env[key]=process.env[key]!
    const deadline=AbortSignal.any([signal,AbortSignal.timeout(15000)])
    const executable=await this.ctx.subprocess.resolveExecutable(this.source().pythonExecutable,env,deadline)
    const policy=this.ctx.sandboxPolicy.resolve({session:{header:{cwd:agent.session.header?.cwd}}})
    const argv=[...installedCoreCommand(executable),'fact-tool',
      '--manifest',resolve(policy.workspaceRoot,config.manifestPath),'--manifest-sha256',config.manifestSha256,
      '--workspace-root',policy.workspaceRoot,'--request-stdin']
    const confined=this.ctx.sandbox.confine(argv,{...policy,mode:'read-only'})
    if(confined.enforcement!=='full')throw new Error('当前宿主未完整接通只读沙箱，事实工具未执行')
    const payload=JSON.stringify(request)
    if(Buffer.byteLength(payload)>1024*1024)throw new Error('事实工具请求超过容量')
    let handle:ProcessHandle|undefined
    try{
      handle=this.ctx.subprocess.spawn({argv:confined.argv,cwd:policy.workspaceRoot,env,
        stdio:{stdin:'pipe',stdout:{maxBytes:131072},stderr:{maxBytes:4096}},signal:deadline,graceMs:1000})
      if(!handle.stdin)throw new Error('事实工具进程缺少输入通道')
      await new Promise<void>((done,reject)=>{handle!.stdin!.on('error',reject);handle!.stdin!.end(payload,done)})
      const outcome=await handle.done;await handle.waitForExit();deadline.throwIfAborted()
      const output=handle.collected.stdout?.readFrom(0)
      if(outcome.exitCode!==0||!output||output.lossy)throw new Error('只读事实进程失败，未扩大范围或调用模型')
      const value:unknown=JSON.parse(output.text)
      if(!object(value)||value.schemaVersion!=='readonly-facts-host-v1')throw new Error('只读事实核心协议未接通')
      return {...value,hostWallMs:performance.now()-started}
    }catch(error){handle?.terminate?.();throw error}
  }
  async execute(operation:string,arguments_:unknown,agent:NativeAgent,signal:AbortSignal):Promise<Json>{
    const owner=this.owner(agent),session=this.active(owner)
    if(session.receipts.length+session.pending>=64)throw new Error('本任务的事实工具调用达到宿主上限')
    session.pending++
    try{
      const result=await this.call(session.config,agent,{op:'query',identity:owner,operation,arguments:arguments_},signal)
      if(typeof result.modelText!=='string'||(!object(result.receipt)&&result.receipt!==null))throw new Error('事实工具缺少核心回执')
      if(result.receipt!==null)session.receipts.push(structuredClone(result.receipt))
      return result
    }finally{session.pending--}
  }
  async verifyCandidate(owner:Json,candidateId:string,candidate:Json,agent:NativeAgent,signal:AbortSignal):Promise<Json|undefined>{
    const existing=this.sessions.get(JSON.stringify(owner))
    if(!existing?.receipts.length)return undefined
    try{
      const session=this.active(owner)
      const result=await this.call(session.config,agent,{op:'verify',identity:owner,candidateId,candidate,
        receipts:structuredClone(session.receipts)},signal)
      if(!object(result.verification))throw new Error('事实校验缺少核心报告')
      return {...result.verification,hostWallMs:result.hostWallMs}
    }catch{return {schemaVersion:'readonly-local-facts-v1',candidateId,candidateSha256:null,bindingStatus:'unavailable',allBoundFieldsSupported:false,
      wholeTaskQualityProven:false,reasonCode:'host-verification-unavailable'}}
  }
}

export function registerReadonlyFactTools(ctx:AgentContext,source:()=>Readonly<Configuration>):ReadonlyFactTools|undefined{
  if(!source().factTools?.enabled)return undefined
  if(!ctx.tools?.register)throw new Error('当前 DSH 未接通原生工具注册，不能启用只读事实工具')
  const host=new ReadonlyFactTools(ctx,source)
  for(const schema of schemas)ctx.tools.register({...schema,
    output:{schema:{type:'object'},render:(_args:unknown,value:Json)=>[{type:'text',text:value.modelText}]},
    async execute(args:unknown,exec:{agent?:NativeAgent;signal:AbortSignal}){
      if(!exec.agent)throw new Error('事实工具缺少宿主 Agent 身份')
      return host.execute(schema.name==='refract_source_excerpt'?'source-excerpt':'python-structure',args,exec.agent,exec.signal)
    }})
  return host
}
