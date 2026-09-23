export type PlanningStrategy = 'stage'|'task'|'composite'|'advisor'|'escalation'|'static'
export interface PlanningConfig {
  schemaVersion:'refractagent-planning-v1'; enabled:boolean; defaultStrategy?:PlanningStrategy
  billingUnit?:'USD'|'AFP'|'CNY'; maxProductionCost?:number; timeoutMs?:number; maxCalls?:number
  models?:Array<{id:string;provider:string;model:string;contextWindow:number;maxOutputTokens:number
    inputPer1k:number;outputPer1k:number;cachedInputPer1k?:number;cacheWritePer1k?:number;reasoningEffort?:string
    deployment?:string;trustPolicy?:string;capabilityCard?:string}>
  roles?:Partial<Record<'efficient'|'capable'|'classifier'|'advisor',string>>
  parameters?:Record<string,string|number>
  security?:{sensitiveTerms?:string[];maxPromptBytes?:number}
  trustPolicies?:Array<Record<string,unknown>>
  compatiblePairs?:string[][]
}
export const EMPTY_PLANNING:PlanningConfig={schemaVersion:'refractagent-planning-v1',enabled:false,defaultStrategy:'stage'}
export const PLANNING_NAMES={stage:'阶段 Stage',task:'任务 Task',composite:'组合 Composite',
  advisor:'审核 Advisor',escalation:'升级 Escalation',static:'静态 Static'} as const
export const PLANNING_PROTOCOL='refractagent-planning/1'
type Json=Record<string,unknown>
export function validatePlanningShape(value:unknown):asserts value is PlanningConfig {
  if(!value||typeof value!=='object'||Array.isArray(value))throw new Error('planningRouting 必须为对象')
  // 这里只约束传输类型。角色、计价、策略可用性与安全准入统一由 Python 检查。
  const v=value as Json
  if(v.schemaVersion!=='refractagent-planning-v1'||typeof v.enabled!=='boolean')
    throw new Error('planningRouting 需要 schemaVersion 与 enabled')
  if(v.defaultStrategy!==undefined&&(typeof v.defaultStrategy!=='string'||!(v.defaultStrategy in PLANNING_NAMES)))
    throw new Error('未知规划路由策略')
  if(v.models!==undefined&&(!Array.isArray(v.models)||v.models.some(m=>
    !m||typeof m!=='object'||typeof m.id!=='string'||typeof m.provider!=='string'||typeof m.model!=='string')))
    throw new Error('planningRouting.models 需要模型目录列表')
  if(v.roles!==undefined&&(!v.roles||typeof v.roles!=='object'||Array.isArray(v.roles)))
    throw new Error('planningRouting.roles 需要角色引用对象')
  if(v.parameters!==undefined&&(!v.parameters||typeof v.parameters!=='object'||Array.isArray(v.parameters)))
    throw new Error('planningRouting.parameters 需要对象')
}
