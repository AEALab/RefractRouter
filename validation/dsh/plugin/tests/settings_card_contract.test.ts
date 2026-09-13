import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { configure } from '../dist/agent-provider.js'
import {
  buildSettingsBase, installRefractSettings, overlaySettings, validateSettingsSection,
} from '../dist/settings-integration.js'
import {
  candidateChoices, RefractCardController, SETTINGS_NAMESPACE,
  type CardScope, type CardScopeSnapshot, type SectionView,
} from '../dist/settings-card.js'

const dshProviderConfig = () => ({
  schemaVersion: 'refractagent-providers-v1' as const,
  billingUnit: 'USD',
  providers: [{ id: 'p', type: 'dsh' as const, dshProvider: 'deepseek' }],
  models: [{ id: 'm', provider: 'p', model: 'deepseek-chat', contextWindow: 64000, pricing: {} }],
})

test('settings base reflects the tunable subset of the composed configuration', () => {
  const config = configure({ executionMode: 'live', allowPaidRuns: true, preset: 'ark-agent-plan',
    limits: { relaxBudget: false, relaxContext: false } })
  const base = buildSettingsBase(config)
  assert.equal(base.providerConfig?.providers[0].type, 'ark-agent-plan')
  assert.ok(base.providerConfig!.models.length > 1)
  assert.equal(overlaySettings(config, base).providerConfig?.models.filter(m => m.role === 'candidate').length, 11)
  assert.deepEqual(base.limits, { relaxBudget: false, relaxContext: false })

  const withProviders = configure({ executionMode: 'live', allowPaidRuns: true,
    providerConfig: dshProviderConfig() })
  assert.deepEqual(buildSettingsBase(withProviders).providerConfig, dshProviderConfig())
})

test('overlaySettings overlays limits and keeps the rest of the composed configuration', () => {
  const config = configure({ executionMode: 'live', allowPaidRuns: true, preset: 'ark-agent-plan',
    limits: { relaxBudget: false, relaxContext: false } })
  assert.equal(overlaySettings(config, {}), config)
  const next = overlaySettings(config, { limits: { relaxBudget: true, relaxContext: true } })
  assert.deepEqual(next.limits, { relaxBudget: true, relaxContext: true })
  assert.equal(next.preset, 'ark-agent-plan')
  assert.equal(next.allowPaidRuns, true)
})

test('overlaySettings providerConfig override replaces the composed preset', () => {
  const config = configure({ executionMode: 'live', allowPaidRuns: true, preset: 'ark-agent-plan' })
  const providerConfig = dshProviderConfig()
  const next = overlaySettings(config, { providerConfig, limits: { relaxBudget: true } })
  assert.equal(next.preset, undefined)
  assert.deepEqual(next.providerConfig, providerConfig)
  assert.deepEqual(next.limits, { relaxBudget: true })
})

test('validateSettingsSection accepts a valid providerConfig and rejects an invalid one', () => {
  validateSettingsSection({ providerConfig: dshProviderConfig() })
  validateSettingsSection({ limits: { relaxBudget: true, relaxContext: false } })
  assert.throws(() => validateSettingsSection({ providerConfig: { schemaVersion: 'wrong' } as never }), /providerConfig/)
  assert.throws(() => validateSettingsSection({
    providerConfig: { ...dshProviderConfig(), strategies: { economy: { models: ['unknown'] } } },
  }), /model ids/)
  assert.throws(() => validateSettingsSection({ limits: { unexpected: true } as never }), /limits/)
})

test('installRefractSettings registers the namespace and follows the settings scope', () => {
  const config = configure({ executionMode: 'live', allowPaidRuns: true, preset: 'ark-agent-plan',
    limits: { relaxBudget: false, relaxContext: false } })
  const sections: Array<Record<string, unknown>> = []
  let current: Record<string, unknown> = {}
  let notify: ((section: Record<string, unknown>) => void) | undefined
  let disposal: (() => void) | undefined
  const registrations: Array<{ ns: string; options: Record<string, unknown> }> = []
  installRefractSettings(
    {
      inject: (deps, callback) => {
        assert.deepEqual(deps, ['settings'])
        callback({
          settings: {
            register: (ns, _schema, options) => {
              registrations.push({ ns, options: options as Record<string, unknown> })
              return {
                get: () => current,
                watch: (cb: (section: Record<string, unknown>) => void) => { notify = cb },
              }
            },
          },
          effect: (setup: () => (() => void) | void) => { disposal = setup() as () => void },
        })
      },
    },
    config,
    section => { sections.push(section as Record<string, unknown>) },
  )
  assert.equal(registrations.length, 1)
  assert.equal(registrations[0].ns, SETTINGS_NAMESPACE)
  assert.deepEqual(registrations[0].options.base, buildSettingsBase(config))
  assert.equal(typeof registrations[0].options.validate, 'function')
  assert.equal(sections.length, 1)
  current = { limits: { relaxBudget: true, relaxContext: false } }
  notify?.(current)
  assert.equal(sections.length, 2)
  assert.deepEqual(sections[1], current)
  disposal?.()
  assert.equal(sections.length, 3)
  assert.deepEqual(sections[2], {})
})

function fakeScope(section: SectionView, user?: SectionView, base?: SectionView) {
  const listeners = new Set<() => void>()
  const writes: Array<{ op: 'set' | 'unset'; field: string; value?: unknown }> = []
  let acceptWrites = true
  let snapshot: CardScopeSnapshot = {
    status: 'ready', value: section, base: base ?? section, user, writable: true,
  }
  const publish = () => { for (const listener of [...listeners]) listener() }
  const scope: CardScope & { writes: typeof writes; setAccepting(next: boolean): void; refresh(): void } = {
    writes,
    refresh: publish,
    setAccepting: (next: boolean) => { acceptWrites = next },
    getSnapshot: () => snapshot,
    subscribe: listener => {
      listeners.add(listener)
      return () => { listeners.delete(listener) }
    },
    set: async (field, value) => {
      writes.push({ op: 'set', field, value })
      if (!acceptWrites) return
      const user = { ...((snapshot.user as Record<string, unknown> | undefined) ?? {}), [field]: value }
      const merged = { ...((snapshot.value as Record<string, unknown> | undefined) ?? {}), [field]: value }
      snapshot = { ...snapshot, user: user as SectionView, value: merged as SectionView }
      publish()
    },
    unset: async field => {
      writes.push({ op: 'unset', field })
      if (!acceptWrites) return
      const user = { ...((snapshot.user as Record<string, unknown> | undefined) ?? {}) }
      delete user[field]
      const base = snapshot.base as Record<string, unknown> | undefined
      const merged = { ...((snapshot.value as Record<string, unknown> | undefined) ?? {}), [field]: base?.[field] }
      snapshot = { ...snapshot, user: user as SectionView, value: merged as SectionView }
      publish()
    },
  }
  return scope
}

test('controller projects the resolved section and stages limit edits', async () => {
  const scope = fakeScope({ limits: { relaxBudget: false, relaxContext: false } })
  const controller = new RefractCardController(scope)
  const face = controller.inject()
  const initial = controller.getSnapshot()
  assert.equal(initial.status, 'ready')
  assert.deepEqual(initial.limits, { relaxBudget: false, relaxContext: false })
  assert.equal(initial.dirty, false)
  assert.equal(initial.overriddenLimits, false)
  face.editLimit('relaxBudget', true)
  assert.equal(controller.getSnapshot().dirty, true)
  await controller.save()
  assert.deepEqual(scope.writes, [{ op: 'set', field: 'limits', value: { relaxBudget: true, relaxContext: false } }])
  assert.equal(controller.getSnapshot().dirty, false)
  assert.equal(controller.getSnapshot().overriddenLimits, true)
  controller.dispose()
})

test('controller blocks save on invalid provider JSON and keeps drafts', async () => {
  const scope = fakeScope({ limits: {} })
  const controller = new RefractCardController(scope)
  const face = controller.inject()
  face.editProviderJson('{ not json')
  assert.match(String(controller.getSnapshot().providerJsonError), /JSON/)
  await controller.save()
  assert.equal(controller.getSnapshot().failed, true)
  assert.deepEqual(scope.writes, [])
  face.discard()
  assert.equal(controller.getSnapshot().failed, false)
  assert.equal(controller.getSnapshot().dirty, false)
  controller.dispose()
})

test('controller saves a valid providerConfig edit and restores it via reset', async () => {
  const providerConfig = dshProviderConfig()
  const scope = fakeScope({ providerConfig })
  const controller = new RefractCardController(scope)
  const face = controller.inject()
  assert.equal(controller.getSnapshot().hasProvider, true)
  assert.equal(controller.getSnapshot().providerJson, JSON.stringify(providerConfig, null, 2))
  face.editDefaultEffort('high')
  assert.equal(controller.getSnapshot().provider?.defaultReasoningEffort, 'high')
  face.editStrategyModels('economy', 'm\nm')
  await controller.save()
  assert.equal(scope.writes.length, 1)
  assert.equal(scope.writes[0].op, 'set')
  assert.equal(scope.writes[0].field, 'providerConfig')
  const saved = scope.writes[0].value as Record<string, unknown>
  assert.equal(saved.defaultReasoningEffort, 'high')
  assert.deepEqual((saved.strategies as Record<string, { models?: string[] }>).economy.models, ['m'])
  assert.equal(controller.getSnapshot().overriddenProvider, true)
  face.resetField('providerConfig')
  await controller.save()
  assert.deepEqual(scope.writes[1], { op: 'unset', field: 'providerConfig' })
  assert.equal(controller.getSnapshot().overriddenProvider, false)
  assert.equal(controller.getSnapshot().providerJson, JSON.stringify(providerConfig, null, 2))
  controller.dispose()
})

test('controller reports failure and keeps drafts when the host rejects a write', async () => {
  const scope = fakeScope({ limits: { relaxBudget: false, relaxContext: false } })
  scope.setAccepting(false)
  const controller = new RefractCardController(scope)
  const face = controller.inject()
  face.editLimit('relaxContext', true)
  await controller.save()
  assert.equal(controller.getSnapshot().failed, true)
  assert.equal(controller.getSnapshot().dirty, true)
  assert.deepEqual(controller.getSnapshot().limits, { relaxBudget: false, relaxContext: true })
  controller.dispose()
})

test('client bundle registers in the host module format and exports the plugin face', async () => {
  const source = await readFile(new URL('../dist/client.js', import.meta.url), 'utf8')
  assert.ok(source.startsWith('window.__ModuleLoader__.load({'), 'bundle must register a module factory')
  assert.ok(source.includes('"dsh-refractrouter-validation"'))
  const registrations: Array<{ id: string; factory: (require: (spec: string) => unknown) => unknown }> = []
  const sandboxWindow = {
    __ModuleLoader__: {
      load: (registration: (typeof registrations)[number]) => { registrations.push(registration) },
    },
  }
  new Function('window', source)(sandboxWindow)
  assert.equal(registrations.length, 1)
  assert.equal(registrations[0].id, 'dsh-refractrouter-validation')
  const exports = registrations[0].factory(spec => {
    if (spec === 'react') return { useState: () => [false, () => undefined] }
    if (spec === 'react/jsx-runtime') return { jsx: () => null, jsxs: () => null, Fragment: 'rra-fragment' }
    throw new Error('unexpected require: ' + spec)
  }) as { apply: (ctx: unknown) => void; inject: string[] }
  assert.equal(typeof exports.apply, 'function')
  assert.deepEqual(exports.inject, ['slots', 'locale', 'settingsScope'])

  const effects: Array<() => unknown> = []
  let boundNamespace: string | undefined
  let slotDeclaration: (() => Generator<unknown>) | undefined
  let registeredOptions: Record<string, unknown> | undefined
  exports.apply({
    effect: (setup: () => unknown) => { effects.push(setup) },
    locale: { register: () => undefined },
    settingsScope: { bind: (spec: { namespace: string }) => { boundNamespace = spec.namespace; return fakeScope({}) } },
    slots: {
      inject: (_key: string, declaration: () => Generator<unknown>) => { slotDeclaration = declaration },
      register: (options: Record<string, unknown>) => { registeredOptions = options; return () => undefined },
    },
  })
  assert.equal(boundNamespace, SETTINGS_NAMESPACE)
  assert.ok(slotDeclaration !== undefined)
  const slotResults = [...(slotDeclaration as () => Generator<unknown>)()]
  assert.equal(slotResults.length, 1)
  assert.equal(typeof slotResults[0], 'function')
  assert.equal(registeredOptions?.name, 'settings.plugin.item')
  assert.equal(registeredOptions?.key, SETTINGS_NAMESPACE)
  assert.equal(typeof registeredOptions?.inject, 'function')
  for (const dispose of effects.map(effect => effect as () => (() => void) | void)) {
    const result = dispose()
    if (typeof result === 'function') result()
  }
})


test('preset fields can be edited, saved and reset with the complete documented model pool', async () => {
  const composed = configure({ preset: 'ark-agent-plan', credentialEnv: 'TEAM_ARK_KEY' })
  const base = buildSettingsBase(composed)
  assert.equal(base.providerConfig!.providers[0].credentialEnv, 'TEAM_ARK_KEY')
  const scope = fakeScope(base as unknown as SectionView)
  const controller = new RefractCardController(scope)
  assert.equal(controller.getSnapshot().hasProvider, true)
  controller.editDefaultEffort('medium')
  controller.editStrategyEffort('quality', 'high')
  controller.editStrategyModels('economy', 'deepseek-v4-flash\n')
  assert.equal(controller.getSnapshot().strategyModelText.economy, 'deepseek-v4-flash\n')
  await controller.save()
  const saved = scope.getSnapshot().value as Parameters<typeof overlaySettings>[1]
  assert.equal(overlaySettings(composed, saved).preset, undefined)
  assert.equal(saved.providerConfig?.defaultReasoningEffort, 'medium')
  assert.equal(saved.providerConfig?.strategies?.quality?.reasoningEffort, 'high')
  controller.resetField('providerConfig')
  await controller.save()
  assert.deepEqual(overlaySettings(composed, scope.getSnapshot().value as typeof saved).providerConfig, base.providerConfig)
  controller.dispose()
})

test('incomplete JSON survives host refresh and can be discarded before attempting save', () => {
  const scope = fakeScope({})
  const controller = new RefractCardController(scope)
  controller.editProviderJson('{')
  scope.refresh()
  assert.equal(controller.getSnapshot().providerJson, '{')
  assert.equal(controller.getSnapshot().dirty, true)
  controller.discard()
  assert.equal(controller.getSnapshot().providerJson, '')
  assert.equal(controller.getSnapshot().providerJsonError, null)
  assert.equal(controller.getSnapshot().dirty, false)
  controller.dispose()
})

test('unconfigured form fields initialize an editable example and preserve multiline input', () => {
  const controller = new RefractCardController(fakeScope({}))
  controller.editDefaultEffort('medium')
  assert.equal(controller.getSnapshot().provider?.defaultReasoningEffort, 'medium')
  controller.editStrategyModels('balanced', 'answer\n')
  assert.equal(controller.getSnapshot().strategyModelText.balanced, 'answer\n')
  controller.editStrategyModels('balanced', 'answer\nother')
  assert.deepEqual(controller.getSnapshot().provider?.strategies?.balanced?.models, ['answer', 'other'])
  controller.dispose()
})


test('model choices show actual names, exclude judges and disambiguate duplicate names', () => {
  assert.deepEqual(candidateChoices(undefined), [])
  const config = { models: [
    { id: 'cheap', model: 'deepseek-v4-flash', provider: 'ark-plan' },
    { id: 'mid', model: 'minimax-m3', provider: 'ark-plan' },
    { id: 'judge', model: 'kimi-k3', role: 'judge' },
  ] }
  assert.deepEqual(candidateChoices(config), [
    { id: 'cheap', label: 'deepseek-v4-flash' },
    { id: 'mid', label: 'minimax-m3' },
  ])
  config.models.push({ id: 'second', model: 'deepseek-v4-flash', provider: 'team' })
  const duplicateLabels = candidateChoices(config).filter(row => row.label.includes('deepseek-v4-flash'))
  assert.equal(new Set(duplicateLabels.map(row => row.label)).size, 2)
})


test('AFP ceiling is staged, saved and removed independently of reasoning effort', async () => {
  const base = buildSettingsBase(configure({ preset: 'ark-agent-plan' }))
  const scope = fakeScope(base as unknown as SectionView)
  const controller = new RefractCardController(scope)
  controller.editStrategyAfpCeiling('economy', '0.5')
  controller.editStrategyEffort('economy', 'high')
  await controller.save()
  assert.deepEqual(controller.getSnapshot().provider?.strategies?.economy,
    { maxAfpCoefficient: 0.5, reasoningEffort: 'high' })
  controller.editStrategyAfpCeiling('economy', '')
  assert.deepEqual(controller.getSnapshot().provider?.strategies?.economy, { reasoningEffort: 'high' })
  controller.dispose()
})


test('planner thinking is editable, persisted and can return to inheritance', async () => {
  const scope = fakeScope({ providerConfig: dshProviderConfig() })
  const controller = new RefractCardController(scope)
  controller.inject().editPlannerThinking('enabled')
  await controller.save()
  assert.equal((scope.writes[0].value as { plannerThinking?: string }).plannerThinking, 'enabled')
  controller.inject().editPlannerThinking('inherit')
  await controller.save()
  assert.equal((scope.writes[1].value as { plannerThinking?: string }).plannerThinking, undefined)
  controller.dispose()
})
