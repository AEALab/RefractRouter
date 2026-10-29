/** 研究专用节点工具桥：工具 schema、参数校验、选模与记账均属于 Python。 */
import type { AgentContext } from './agent-provider.js'
import type { NativeAgent, ToolSchema } from './native-tools.js'
import type { PlanningController } from './planning-routing.js'
type Json=Record<string,any>

export async function registerExperimentalNodeTools(ctx:AgentContext,planning:PlanningController,
  profile:Json,hostSchemas:()=>ToolSchema[]):Promise<()=>void>{
  if(!ctx.tools?.register)throw new Error('DSH 没有工具注册服务')
  const catalog=await planning.enableNodeTools(profile)
  const schemas=catalog.tools as ToolSchema[]
  const current=hostSchemas(),names=new Set(current.map(t=>t.name))
  if(current.length+schemas.length>catalog.limits.maxTools)throw new Error('宿主与节点工具总数超过冻结上限')
  if(schemas.some(t=>names.has(t.name)))throw new Error('节点工具名与宿主工具冲突')
  const disposers:Array<()=>void>=[]
  try{
    for(const schema of schemas){
      const dispose=ctx.tools.register({...schema,
        output:{schema:{type:'object'},render:(_args:unknown,value:Json)=>[
          {type:'text',text:JSON.stringify(value)}]},
        async execute(args:unknown,exec:{callId:string;signal:AbortSignal;agent?:NativeAgent}){
          if(!exec.agent)throw new Error('专家工具缺少可信 Agent 身份')
          return planning.executeNodeTool(exec.agent,exec.callId,schema.name,args,exec.signal)
        }})
      if(typeof dispose==='function')disposers.push(dispose as ()=>void)
    }
    planning.activateNodeTools(catalog.limits)
  }catch(error){for(const dispose of disposers.reverse())dispose();throw error}
  return ()=>{for(const dispose of disposers.reverse())dispose()}
}
