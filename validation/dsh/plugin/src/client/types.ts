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
    options: { name: string; key?: string; locale?: string; inject?: () => unknown },
    component: unknown,
  ): unknown
}

export interface ClientContext {
  slots: ClientSlotsService
  locale: ClientLocaleService
  settingsScope: ClientSettingsScopeBinder
  effect(setup: () => unknown, label?: string): unknown
}
