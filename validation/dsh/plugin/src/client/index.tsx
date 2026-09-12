/** RefractAgent 浏览器半边：在「设置 → 插件 → 插件配置」注册自己的设置卡片。 */
import { RefractCardController, SETTINGS_NAMESPACE } from '../settings-card.js'
import { RefractCard } from './refract-card.js'
import { en, LOCALE_NS, zh } from './locale.js'
import type { ClientContext } from './types.js'

export const inject = ['slots', 'locale', 'settingsScope']

export function apply(ctx: ClientContext): void {
  ctx.effect(() => ctx.locale.register(LOCALE_NS, { zh, en }), 'refractagent-settings-card: dictionaries')
  const controller = new RefractCardController(ctx.settingsScope.bind({ namespace: SETTINGS_NAMESPACE }))
  ctx.effect(() => () => {
    controller.dispose()
  }, 'refractagent-settings-card: card controller')
  ctx.slots.inject('settings.plugin.item', function* () {
    yield ctx.slots.register({
      name: 'settings.plugin.item',
      key: SETTINGS_NAMESPACE,
      locale: LOCALE_NS,
      inject: () => controller.inject(),
    }, RefractCard)
  })
}
