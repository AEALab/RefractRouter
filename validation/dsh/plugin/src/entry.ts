/**
 * DSH 仅从启用的包主入口发现前端。生产配置在主入口启动路由，
 * 验收工具保留独立子入口；旧主入口配置仍按原验收工具合同读取。
 */
import {
  apply as applyValidation, Config as ValidationConfig, inject as validationInject,
  type DshContext,
} from './index.js'
import {
  apply as applyRouting, Config as RoutingConfig, inject as routingInject,
  type AgentContext,
} from './agent-provider.js'

export * from './index.js'
export const inject = [...new Set([...validationInject, ...routingInject])]

function entry(value: unknown): { mode: 'routing' | 'validation-tools'; config: unknown } {
  if (value === null || value === undefined) return { mode: 'validation-tools', config: {} }
  if (typeof value !== 'object' || Array.isArray(value)) throw new Error('插件配置必须是对象')
  const { entryMode, ...config } = value as Record<string, unknown>
  if (entryMode === undefined) {
    // DSH 的 profile 覆盖会替换整份入口配置，新增的 bundle 标记未必进入旧覆盖。
    // 这些字段只属于已有路由 schema，旧验收 schema 从未接受它们。
    const savedRouting = ['pythonExecutable', 'executionMode', 'providerConfig', 'dshModelPool',
      'planningRouting', 'liveExecution', 'routerUrl'].some(key => Object.hasOwn(config, key))
    return { mode: savedRouting ? 'routing' : 'validation-tools', config }
  }
  if (entryMode !== 'routing' && entryMode !== 'validation-tools') throw new Error('未知插件入口模式')
  return { mode: entryMode, config }
}

export const Config = { '~standard': {
  version: 1 as const,
  vendor: 'dsh-refractrouter-entry',
  validate(value: unknown) {
    try {
      const selected = entry(value)
      const checked = (selected.mode === 'routing' ? RoutingConfig : ValidationConfig)['~standard'].validate(selected.config)
      if ('issues' in checked) return checked
      return { value: { ...checked.value, entryMode: selected.mode } }
    } catch (error) {
      return { issues: [{ message: error instanceof Error ? error.message : String(error) }] }
    }
  },
} }

export function apply(ctx: AgentContext | DshContext, raw: unknown = {}): void {
  const selected = entry(raw)
  if (selected.mode === 'routing') applyRouting(ctx as AgentContext, selected.config)
  else applyValidation(ctx as DshContext, selected.config)
}
