import { createElement } from 'react'
import { graphModule } from './graph.js'
/** RefractAgent 浏览器半边：在「设置 → 插件 → 插件配置」注册自己的设置卡片。 */
import { RefractCardController, SETTINGS_NAMESPACE } from '../settings-card.js'
import { RefractCard } from './refract-card.js'
import { en, LOCALE_NS, zh } from './locale.js'
import type { ClientContext, RouterProjectDirectory } from './types.js'
import { FROZEN_MODEL_PROFILES } from './model-profiles.js'

const graph = graphModule(createElement as unknown as Parameters<typeof graphModule>[0])
export const parse = graph.parse
export const layout = graph.layout
export const applyGraph = graph.apply

export const inject = ['slots', 'locale', 'remote', 'remote.session', 'remote.llm', 'settingsScope']

export function apply(ctx: ClientContext): void {
  graph.apply(ctx)
  ctx.effect(() => ctx.locale.register(LOCALE_NS, { zh, en }), 'refractagent-settings-card: dictionaries')
  const controller = new RefractCardController(ctx.settingsScope.bind({ namespace: SETTINGS_NAMESPACE }),
    FROZEN_MODEL_PROFILES.profiles)
  ctx.effect(() => () => {
    controller.dispose()
  }, 'refractagent-settings-card: card controller')
  ctx.slots.inject('settings.plugin.item', function* () {
    yield ctx.slots.register({
      name: 'settings.plugin.item',
      key: SETTINGS_NAMESPACE,
      locale: LOCALE_NS,
      inject: () => ({...controller.inject(),loadCatalog:async()=>{
        const result=await ctx.remote.session.modelCatalog()
        if(!result.ok||!result.value)throw new Error(result.error?.message??'DSH model catalog unavailable')
        return result.value
      },loadRouterProjects:async(connection:{url:string;credential?:string}):Promise<RouterProjectDirectory>=>{
        const result=await ctx.remote.llm.discoverModels('refractagent-router-projects',{
          baseURL:connection.url,...(connection.credential?{api:connection.credential}:{})})
        if(!result.ok||!result.value)throw new Error(result.error?.message??'Router project discovery unavailable')
        const legacy=result.value.some(row=>row.id==='__refractrouter_http_v1__')
        return {protocol:legacy?'refractagent-http-v1':'refractagent-http-v2',projects:legacy?[]:
          result.value.map(row=>({id:row.id,name:row.name??row.id}))}
      }}),
    }, RefractCard)
  })
}
