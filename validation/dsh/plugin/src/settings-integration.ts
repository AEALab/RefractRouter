import examples from './provider-examples.json' with { type: 'json' }
/** DSH 设置命名空间集成：schema、组合 base、覆盖合成与宿主注册。
 * 命名空间出现在「设置 → 插件 → 插件配置」，浏览器半边由 src/client/ 提供。
 */
import {
  freezeConfiguration, isRecordValue, validateProviderConfiguration, type SettingsSection,
} from './provider-config.js'
import { SETTINGS_NAMESPACE } from './settings-card.js'
import type { Configuration } from './agent-provider.js'

interface SchemaNode {
  type: string
  meta: Record<string, unknown>
  dict?: Record<string, SchemaNode>
}

export interface RefractSettingsSchema {
  (value: unknown): SettingsSection
  type: 'object'
  meta: { default: Record<string, never> }
  dict: Record<string, SchemaNode>
  toJSON(): unknown
}

/**
 * 用户可调子集的命名空间 schema。
 *
 * DSH settings 只依赖 Schemastery 的可调用校验器、结构节点和 toJSON envelope。
 * 这里实现这个最小公开契约，让发布包继续保持自包含；providerConfig 的跨字段约束
 * 仍由 validate 钩子负责。
 */
export function buildSettingsSchema(): RefractSettingsSchema {
  const anyNode: SchemaNode = { type: 'any', meta: {} }
  const booleanNode = (): SchemaNode => ({ type: 'boolean', meta: {} })
  const limitsNode: SchemaNode = {
    type: 'object',
    meta: { default: {} },
    dict: { relaxBudget: booleanNode(), relaxContext: booleanNode() },
  }
  const schema = ((value: unknown): SettingsSection => {
    if (value === undefined || value === null) value = {}
    if (!isRecordValue(value)) throw new TypeError('RefractAgent settings must be an object')
    const resolved = structuredClone(value) as Record<string, unknown>
    const limits = resolved.limits
    if (limits === undefined || limits === null) {
      resolved.limits = {}
    } else {
      if (!isRecordValue(limits)) throw new TypeError('$.limits expected object')
      for (const key of ['relaxBudget', 'relaxContext']) {
        const entry = limits[key]
        if (entry !== undefined && typeof entry !== 'boolean') {
          throw new TypeError(`$.limits.${key} expected boolean`)
        }
      }
    }
    return resolved as SettingsSection
  }) as RefractSettingsSchema
  schema.type = 'object'
  schema.meta = { default: {} }
  schema.dict = { providerConfig: anyNode, limits: limitsNode }
  schema.toJSON = () => ({
    uid: 4,
    refs: {
      0: anyNode,
      1: limitsNode.dict!.relaxBudget,
      2: limitsNode.dict!.relaxContext,
      3: { type: limitsNode.type, meta: limitsNode.meta, dict: { relaxBudget: 1, relaxContext: 2 } },
      4: { type: 'object', meta: { default: {} }, dict: { providerConfig: 0, limits: 3 } },
    },
  })
  return schema
}

/** 组合配置作为设置 base 层；未配置的字段不进入 base。 */
export function buildSettingsBase(config: Readonly<Configuration>): Readonly<SettingsSection> {
  const base: SettingsSection = {}
  if (config.providerConfig !== undefined) base.providerConfig = config.providerConfig
  else if (config.preset === 'ark-agent-plan') {
    base.providerConfig = structuredClone(examples['ark-agent-plan']) as SettingsSection['providerConfig']
    base.providerConfig!.providers[0].credentialEnv = config.credentialEnv
  }
  if (config.limits !== undefined) base.limits = config.limits
  return freezeConfiguration(base)
}

/** 宿主 validate 钩子：schema 之外约束不了一个完整 providerConfig 的场景。 */
export function validateSettingsSection(section: Readonly<SettingsSection>): void {
  if (section.providerConfig !== undefined) validateProviderConfiguration(section.providerConfig)
  if (section.limits !== undefined && (
    !isRecordValue(section.limits)
    || Object.keys(section.limits).some(key => !['relaxBudget', 'relaxContext'].includes(key))
    || Object.values(section.limits).some(value => typeof value !== 'boolean')
  )) {
    throw new Error('limits may only contain boolean relaxBudget and relaxContext')
  }
}

/** 把设置段落叠加回组合配置；providerConfig 覆盖存在时取代 preset。 */
export function overlaySettings(
  composed: Readonly<Configuration>,
  section: Readonly<SettingsSection>,
): Readonly<Configuration> {
  if (section.providerConfig === undefined && section.limits === undefined) return composed
  const next: Configuration = { ...composed }
  if (section.providerConfig !== undefined) {
    next.preset = undefined
    next.providerConfig = section.providerConfig
  }
  if (section.limits !== undefined) next.limits = section.limits
  return freezeConfiguration(next)
}

export interface HostSettingsScope {
  get(): Readonly<SettingsSection>
  watch(callback: (next: Readonly<SettingsSection>) => void): unknown
}
export interface HostSettingsService {
  register(
    ns: string,
    schema: unknown,
    options?: { base?: Readonly<SettingsSection>; validate?: (value: Readonly<SettingsSection>) => void },
  ): HostSettingsScope
}
export interface SettingsFiberContext {
  settings: HostSettingsService
  effect(setup: () => (() => void) | void): unknown
}

/** 注册命名空间并让配置源跟随设置变化；未组合 settings 服务时静默保持组合配置。 */
export function installRefractSettings(
  host: { inject?: (deps: readonly string[], callback: (sctx: SettingsFiberContext) => void) => unknown },
  composed: Readonly<Configuration>,
  onChange: (section: Readonly<SettingsSection>) => void,
): void {
  host.inject?.(['settings'], sctx => {
    const scope = sctx.settings.register(SETTINGS_NAMESPACE, buildSettingsSchema(), {
      base: buildSettingsBase(composed),
      validate: validateSettingsSection,
    })
    const apply = () => onChange(scope.get())
    sctx.effect(() => () => {
      onChange({})
    })
    apply()
    scope.watch(apply)
  })
}
