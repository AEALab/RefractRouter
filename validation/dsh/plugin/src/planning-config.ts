export type PlanningStrategy = 'stage'|'task'|'composite'|'advisor'|'escalation'|'static'
export type CapabilityLevel = 'unknown'|'declared'|'connected'|'verified'
export type TaskModality = 'imageInput'|'videoInput'|'imageOutput'|'videoOutput'
export interface PlanningModelCapabilities {
  mainExecutor?:boolean
  toolCalling?:CapabilityLevel
  modalities?:Partial<Record<TaskModality,CapabilityLevel>>
  formats?:Partial<Record<TaskModality,string[]>>
  limits?:Partial<Record<'maxImages'|'maxImageBytes'|'maxVideoBytes'|'maxVideoSeconds'|'maxWidth'|'maxHeight',number>>
  source?:string
  checkedAt?:string
}
export interface PlanningModelConfig {
  id:string;provider:string;model:string;contextWindow?:number;maxOutputTokens?:number
  inputPer1k?:number;outputPer1k?:number;cachedInputPer1k?:number;cacheWritePer1k?:number
  reasoningEffort?:string;billingUnit?:'USD'|'AFP'|'CNY';deployment?:string;trustPolicy?:string
  capabilityCard?:string;capabilities?:PlanningModelCapabilities
}
export type TaskJudgeConfig =
  | {type:'llm';modelId:string}
  | {type:'local-decision';adapter:'laya-mlx';modelPath:string;sourceModel?:string;revision?:string
      device?:'gpu'|'metal'|'cpu';dtype?:'float16'|'float32'|'bfloat16'
      method?:'ordinal-v1'|'choice-v2'}
export interface TaskRoutingConfig {
  pool:string[];fallback:string;judge:TaskJudgeConfig;threshold?:number;maxInputChars?:number
  maxExecutionOutputTokens?:number
}
export interface EscalationRoutingConfig {
  initial:string;takeover:string;judge:TaskJudgeConfig
  stallConfirmations?:number;threshold?:number;judgeTimeoutMs?:number;maxJudgeInputBytes?:number
  maxExecutionOutputTokens?:number;maxJudgeOutputTokens?:number
}
export interface MediaRouteConfig {
  id:string;provider:string;credentialProvider?:string;model:string
  operations:Array<'image-understand'|'video-understand'|'image-generate'|'image-edit'|'video-generate'|'image-to-video'>
  billingUnit?:'USD'|'AFP'|'CNY';pricing?:{basis:'image'|'output-10k-token'|'second';unitCost:number;source:string;checkedAt:string}
  deployment?:string;trustPolicy?:string
  verified?:boolean;verification?:CapabilityLevel;endpoint?:string
}
export interface PlanningConfig {
  schemaVersion:'refractagent-planning-v1'|'refractagent-planning-v2'|'refractagent-planning-v3'|'refractagent-planning-v4'
  enabled:boolean;defaultStrategy?:PlanningStrategy
  billingUnit?:'USD'|'AFP'|'CNY';maxProductionCost?:number
  maxProductionCostByUnit?:Partial<Record<'USD'|'AFP'|'CNY',number>>;timeoutMs?:number;maxCalls?:number
  models?:PlanningModelConfig[]
  roles?:Partial<Record<'efficient'|'capable'|'classifier'|'advisor',string>>
  parameters?:Record<string,string|number>
  security?:{sensitiveTerms?:string[];maxPromptBytes?:number}
  trustPolicies?:Array<Record<string,unknown>>
  compatiblePairs?:string[][]
  task?:TaskRoutingConfig
  escalation?:EscalationRoutingConfig
  mediaRoutes?:MediaRouteConfig[]
}
export const EMPTY_PLANNING:PlanningConfig={schemaVersion:'refractagent-planning-v4',enabled:false,defaultStrategy:'stage'}
export const PLANNING_NAMES={stage:'阶段 Stage',task:'任务 Task',composite:'组合 Composite',
  advisor:'审核 Advisor',escalation:'升级 Escalation',static:'静态 Static'} as const
export const PLANNING_PROTOCOL='refractagent-planning/4'
type Json=Record<string,unknown>
export function validatePlanningShape(value:unknown):asserts value is PlanningConfig {
  if(!value||typeof value!=='object'||Array.isArray(value))throw new Error('planningRouting 必须为对象')
  // 这里只约束传输类型。候选资格、计价、安全准入与 Judge 合同统一由 Python 检查。
  const v=value as Json
  if(!['refractagent-planning-v1','refractagent-planning-v2','refractagent-planning-v3','refractagent-planning-v4'].includes(String(v.schemaVersion))||typeof v.enabled!=='boolean')
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
  if(v.task!==undefined&&(!v.task||typeof v.task!=='object'||Array.isArray(v.task)))
    throw new Error('planningRouting.task 需要 Task 设置对象')
  if(v.escalation!==undefined&&(!v.escalation||typeof v.escalation!=='object'||Array.isArray(v.escalation)))
    throw new Error('planningRouting.escalation 需要 Escalation 设置对象')
  if(v.mediaRoutes!==undefined&&!Array.isArray(v.mediaRoutes))throw new Error('planningRouting.mediaRoutes 需要列表')
}
