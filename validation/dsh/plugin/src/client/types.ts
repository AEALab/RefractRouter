/** 浏览器半边的结构化契约：对应 DSH 客户端插件上下文提供的服务。 */
import type { CardScope } from '../settings-card.js'

export interface LocaleDictionary {
  [key: string]: string
}

export interface ClientLocaleService {
  register(ns: string, dictionaries: { zh: LocaleDictionary; en: LocaleDictionary }): unknown
}

export interface ClientSettingsScopeBinder {
  bind(spec: { namespace: string }): CardScope
}

export interface ClientSlotsService {
  inject(key: string, declaration: () => Generator<unknown>): unknown
  register(
    options: { name: string; key?: string; locale?: string; inject?: (...args: any[]) => unknown; id?:string;order?:number;label?:()=>string },
    component: unknown,
  ): unknown
}

export interface ClientContext {
  modelDirectories?:{directoryFor(sessionId:string):import('./planning.js').ModelDirectory}
  slots: ClientSlotsService
  locale: ClientLocaleService
  settingsScope: ClientSettingsScopeBinder
  remote: { session: { modelCatalog(): Promise<{ok:boolean;value?:DshModelCatalog;error?:{message:string}}> } }
    & {llm:{discoverModels(settingsNs:string,request:{provider?:string;baseURL?:string;api?:string}):Promise<{
      ok:boolean;value?:Array<{id:string;name?:string}>;error?:{message:string}
    }>}}
    & {settings:{mutate(ns:string,ops:Array<{op:'set'|'unset';path:string[];value?:unknown}>,
      expectedRevision?:number):Promise<{ok:true;value:unknown}|{ok:false;error:{code:string;message:string}}>}}
  effect(setup: () => unknown, label?: string): unknown
}

export interface RouterProjectDirectory {
  protocol:'refractagent-http-v1'|'refractagent-http-v2'
  projects:Array<{id:string;name:string}>
}

export interface RouteLatencyDirectory {
  profiles:Array<{route:string;effectiveModel:string;reasoningEffort:string;prediction_ms:number;
    samples:number;window:string;last_observed_at:string;snapshot_id:string;
    statusCounts:Record<string,number>}>
}

export interface DshModelCatalog {
  groups: Array<{id:string;name:string;models:Array<{id:string;name:string;description?:string;
    reasoning?:{efforts:Array<{id:string;name:string}>;defaultEffort?:string}}> }>
  failures: Array<{id:string;name:string;message:string}>
}
