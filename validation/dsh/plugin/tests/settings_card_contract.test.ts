import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { configure } from '../dist/agent-provider.js'
import { migrateDshModelPool } from '../dist/provider-config.js'
import {
  buildSettingsBase, installRefractSettings, overlaySettings, validateSettingsSection,
} from '../dist/settings-integration.js'
import {
  blocksDshModelPoolRun, buildDshModelPoolIssues, buildV4FeasibilityPreview, candidateChoices, DEPLOYMENT_OPTIONS,
  RefractCardController, SETTINGS_NAMESPACE,
  type CardScope, type CardScopeSnapshot, type DshModelPoolView, type SectionView,
} from '../dist/settings-card.js'

const publicProfiles = [{ provider: 'deepseek-official', model: 'deepseek-v4-pro',
  pricing: { unit: 'USD', inputPer1k: 0.00132, cachedInputPer1k: 0.000044, outputPer1k: 0.00396 },
  quality_profile: null }]
const qualityPublicProfiles = [{ ...publicProfiles[0], quality_profile: {
  score: 91, source: { kind: 'independent-third-party' },
} }]

const dshProviderConfig = () => ({
  schemaVersion: 'refractagent-providers-v1' as const,
  billingUnit: 'USD',
  providers: [{ id: 'p', type: 'dsh' as const, dshProvider: 'deepseek' }],
  models: [{ id: 'm', provider: 'p', model: 'deepseek-chat', contextWindow: 64000, pricing: {} }],
})

const v4ProviderConfig = () => ({
  schemaVersion: 'refractagent-providers-v4' as const,
  billingUnit: 'USD',
  objective: { qualityMin: 80, primary: 'cost' as const, secondary: 'latency' as const, dagMode: 'auto' as const },
  security: { dataMode: 'synthetic', sensitiveTerms: ['内部'] },
  trustPolicies: [{ id: 'team-cn', residency: 'CN', auditLogging: true, allowsSensitiveData: true }],
  providers: [
    { id: 'external', type: 'openai-compatible' as const, baseUrl: 'https://example.test/v1',
      credentialEnv: 'TEAM_MODEL_KEY', deployment: 'external-cloud' as const },
    { id: 'local', type: 'dsh' as const, dshProvider: 'local-model-provider', deployment: 'local' as const },
  ],
  models: [
    { id: 'worker', provider: 'external', model: 'worker-model', roles: ['worker' as const], contextWindow: 128000,
      pricing: { unit: 'USD', inputPer1k: 0.1, outputPer1k: 0.2 }, routing: { quality: 90, latencyMs: 1000 } },
    { id: 'router', provider: 'local', model: 'router-model', roles: ['planner' as const, 'worker' as const,
      'classifier' as const], contextWindow: 128000, pricing: { unit: 'USD', inputPer1k: 0, outputPer1k: 0 } },
    { id: 'judge', provider: 'local', model: 'judge-model', roles: ['judge' as const], contextWindow: 128000,
      pricing: { unit: 'USD', inputPer1k: 0, outputPer1k: 0 } },
  ],
})

const dshModelPool = () => ({
  schemaVersion: 'refractagent-dsh-model-pool-v1' as const,
  billingUnit: 'USD',
  security: { dataMode: 'synthetic' },
  routes: [
    { provider: 'team', model: 'planner', deployment: 'local' as const, overrides: {
      inputPer1k: 0, outputPer1k: 0, quality: 90, latencyMs: 100,
    } },
    { provider: 'team', model: 'worker', deployment: 'local' as const, overrides: {
      inputPer1k: 0, outputPer1k: 0, quality: 80, latencyMs: 50,
    } },
  ],
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

test('Router URL settings overlay a real remote connection and enforce transport safety', () => {
  const config=configure({})
  const router={url:'https://router.example/team',credential:'ROUTER_TOKEN',project:'alpha'}
  validateSettingsSection({router})
  const next=overlaySettings(config,{router})
  assert.equal(next.routerUrl,'https://router.example/team')
  assert.equal(next.routerCredential,'ROUTER_TOKEN')
  assert.deepEqual(buildSettingsBase(next).router,router)
  assert.throws(()=>validateSettingsSection({router:{url:'http://router.example'}}),/requires HTTPS/)
  assert.throws(()=>validateSettingsSection({router:{url:'https://user:secret@router.example'}}),/without credentials/)
  assert.throws(()=>validateSettingsSection({router:{url:'https://router.example',project:'bad/project'}}),/project/)
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

test('DSH 模型池只接受目录身份、明确部署和有效职责覆盖', () => {
  const pool = dshModelPool()
  validateSettingsSection({ dshModelPool: pool })
  validateSettingsSection({ dshModelPool: {...pool, allowSharedJudge:true} })
  assert.throws(() => validateSettingsSection({ dshModelPool: {
    ...pool, allowSharedJudge:'yes',
  } as never }), /allowSharedJudge/)
  assert.throws(() => validateSettingsSection({ dshModelPool: {
    ...pool, routes: [...pool.routes, {...pool.routes[0]}],
  } }), /unique/)
  assert.throws(() => validateSettingsSection({ dshModelPool: {
    ...pool, routes: [{...pool.routes[0], provider:'refractagent'}, pool.routes[1]],
  } }), /route/)
  assert.throws(() => validateSettingsSection({ dshModelPool: {
    ...pool, roleOverrides: {planner:'missing/model'},
  } }), /unavailable route/)
  assert.throws(() => validateSettingsSection({ dshModelPool: {
    ...pool, routes: [{...pool.routes[0], deployment:'trusted-cloud'}, pool.routes[1]],
  } as never }), /trustPolicy/)
})

test('DSH 模型池覆盖保留旧 providerConfig 供迁移回退，但运行时选择模型池', () => {
  const config = configure({providerConfig:dshProviderConfig()})
  const pool = dshModelPool()
  const section = {providerConfig:dshProviderConfig(), dshModelPool:pool}
  validateSettingsSection(section)
  const next = overlaySettings(config, section)
  assert.deepEqual(next.dshModelPool, pool)
  assert.equal(next.providerConfig, undefined)
})

test('v3 security configuration passes through while trust domains stay explicit', () => {
  const base = dshProviderConfig()
  const providerConfig = {
    ...base,
    schemaVersion: 'refractagent-providers-v3' as const,
    security: { dataMode: 'live' },
    trustPolicies: [{ id: 'team-cn', residency: 'CN', auditLogging: true, allowsSensitiveData: true }],
    providers: base.providers.map((provider, index) => ({ ...provider,
      deployment: index === 0 ? 'trusted-cloud' as const : 'local' as const,
      ...(index === 0 ? { trustPolicy: 'team-cn' } : {}) })),
  }
  validateSettingsSection({ providerConfig })
  assert.deepEqual(overlaySettings(configure({}), { providerConfig }).providerConfig, providerConfig)
  assert.throws(() => validateSettingsSection({ providerConfig: {
    ...providerConfig,
    providers: [{ ...providerConfig.providers[0], trustPolicy: 'missing' }],
  } }), /trustPolicy/)
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
  let writeError: Error | undefined
  let snapshot: CardScopeSnapshot = {
    status: 'ready', value: section, base: base ?? section, user, writable: true,
  }
  const publish = () => { for (const listener of [...listeners]) listener() }
  const scope: CardScope & { writes: typeof writes; setAccepting(next: boolean): void;
    setWriteError(next: Error | undefined): void; refresh(): void } = {
    writes,
    refresh: publish,
    setAccepting: (next: boolean) => { acceptWrites = next },
    setWriteError: next => { writeError = next },
    getSnapshot: () => snapshot,
    subscribe: listener => {
      listeners.add(listener)
      return () => { listeners.delete(listener) }
    },
    set: async (field, value) => {
      writes.push({ op: 'set', field, value })
      if (writeError) throw writeError
      if (!acceptWrites) return
      const user = { ...((snapshot.user as Record<string, unknown> | undefined) ?? {}), [field]: value }
      const merged = { ...((snapshot.value as Record<string, unknown> | undefined) ?? {}), [field]: value }
      snapshot = { ...snapshot, user: user as SectionView, value: merged as SectionView }
      publish()
    },
    unset: async field => {
      writes.push({ op: 'unset', field })
      if (writeError) throw writeError
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

test('controller saves and resets the Router service URL without storing a token',async()=>{
  const scope=fakeScope({})
  const controller=new RefractCardController(scope)
  const face=controller.inject()
  face.editRouter({url:'http://127.0.0.1:8787',credential:'ROUTER_TOKEN',project:'alpha'})
  assert.deepEqual(controller.getSnapshot().router,{url:'http://127.0.0.1:8787',credential:'ROUTER_TOKEN',project:'alpha'})
  await controller.save()
  assert.deepEqual(scope.writes[0],{op:'set',field:'router',value:{url:'http://127.0.0.1:8787',credential:'ROUTER_TOKEN',project:'alpha'}})
  assert.equal(JSON.stringify(scope.writes).includes('private-test-key'),false)
  face.resetField('router')
  await controller.save()
  assert.deepEqual(scope.writes[1],{op:'unset',field:'router'})
  controller.dispose()
})

test('controller strips undefined form fields before sending DSH settings mutations',async()=>{
  const scope=fakeScope({})
  const controller=new RefractCardController(scope)
  const pool=dshModelPool()
  controller.inject().editDshModelPool({...pool,routes:[{
    ...pool.routes[0],trustPolicy:undefined,overrides:{...pool.routes[0].overrides,note:undefined},
  }]})
  await controller.save()
  const saved=scope.writes[0]?.value as Record<string,unknown>
  assert.equal(JSON.stringify(saved).includes('undefined'),false)
  const route=(saved.routes as Array<Record<string,unknown>>)[0]!
  assert.equal(Object.hasOwn(route,'trustPolicy'),false)
  assert.equal(Object.hasOwn(route.overrides as object,'note'),false)
  assert.equal(controller.getSnapshot().failed,false)
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

test('部署属性选项同时展示中文含义与稳定合同值', () => {
  assert.deepEqual(DEPLOYMENT_OPTIONS, [
    { value: 'local', label: '真实本地（local）' },
    { value: 'external-cloud', label: '普通外部云（external-cloud）' },
    { value: 'trusted-cloud', label: '可信外部云（trusted-cloud）' },
    { value: 'simulated-local', label: '云模型模拟本地（simulated-local）' },
  ])
})

test('DSH 模型池区分安全错误、独立质量缺口与旧合同迁移', () => {
  const blocked: DshModelPoolView = structuredClone(dshModelPool())
  blocked.security = { dataMode: 'live' }
  blocked.routes[0] = { ...blocked.routes[0], deployment: 'simulated-local' as const,
    trustPolicy: 'cloud-cn' }
  Object.assign(blocked, { trustPolicies: [{ id: 'cloud-cn', residency: 'CN', auditLogging: true,
    allowsSensitiveData: true, acknowledgeExternalTransmission: false }] })
  const issues = buildDshModelPoolIssues(blocked)
  assert.ok(issues.some(issue => issue.code === 'DSH_POOL_EXTERNAL_ACK_REQUIRED' && issue.severity === 'error'))
  assert.ok(issues.some(issue => issue.code === 'DSH_POOL_LEGACY_SCHEMA'))
  assert.ok(issues.some(issue => issue.code === 'DSH_POOL_INDEPENDENT_QUALITY_REQUIRED'
    && blocksDshModelPoolRun(issue)))

  const publicDraft = { schemaVersion: 'refractagent-dsh-model-pool-v1' as const, security: { dataMode: 'synthetic' },
    routes: [{ provider: 'deepseek-official', model: 'deepseek-v4-pro', deployment: 'external-cloud' }] }
  const publicIssues = buildDshModelPoolIssues(publicDraft, publicProfiles)
  assert.ok(publicIssues.some(issue => issue.code === 'DSH_POOL_INDEPENDENT_QUALITY_REQUIRED'
    && issue.severity === 'warning'))
  assert.equal(publicIssues.some(issue => issue.severity === 'error'), false)
  const readyIssues = buildDshModelPoolIssues({ ...publicDraft,
    schemaVersion: 'refractagent-dsh-model-pool-v2' }, qualityPublicProfiles)
  assert.equal(readyIssues.some(blocksDshModelPoolRun), false)
})

test('模型池 v1 显式迁移到 v2 并移除手工质量与时延', () => {
  const migrated = migrateDshModelPool(dshModelPool())
  assert.equal(migrated.schemaVersion, 'refractagent-dsh-model-pool-v2')
  assert.deepEqual(migrated.routes[0]?.overrides, { inputPer1k: 0, outputPer1k: 0 })
})

test('合成与已脱敏数据不会套用 live 的 simulated-local 外传确认门槛', () => {
  for (const dataMode of ['synthetic', 'desensitized'] as const) {
    const pool: DshModelPoolView = structuredClone(dshModelPool())
    pool.security = { dataMode }
    pool.routes[0] = { ...pool.routes[0], deployment: 'simulated-local', trustPolicy: undefined }
    const issues = buildDshModelPoolIssues(pool)
    assert.equal(issues.some(issue => issue.code === 'DSH_POOL_EXTERNAL_ACK_REQUIRED'), false)
    assert.equal(issues.some(issue => issue.code === 'DSH_POOL_TRUST_POLICY_REQUIRED'), false)
  }
})

test('阻断问题不写入宿主，档案警告允许保存草稿', async () => {
  const blockedScope = fakeScope({})
  const blockedController = new RefractCardController(blockedScope)
  const blocked: DshModelPoolView = structuredClone(dshModelPool())
  blocked.routes[0] = { ...blocked.routes[0], deployment: '' as 'local' }
  blockedController.inject().editDshModelPool(blocked)
  await blockedController.save()
  assert.deepEqual(blockedScope.writes, [])
  assert.equal(blockedController.getSnapshot().failed, true)
  assert.match(String(blockedController.getSnapshot().failureMessage), /保存前检查/)
  blockedController.dispose()

  const draftScope = fakeScope({})
  const draftController = new RefractCardController(draftScope, publicProfiles)
  draftController.inject().editDshModelPool({ schemaVersion: 'refractagent-dsh-model-pool-v2',
    security: { dataMode: 'synthetic' }, routes: [{ provider: 'deepseek-official',
      model: 'deepseek-v4-pro', deployment: 'external-cloud' }] })
  await draftController.save()
  assert.equal(draftScope.writes.length, 1)
  assert.equal(draftController.getSnapshot().failed, false)
  assert.ok(draftController.getSnapshot().issues.some(issue => issue.code === 'DSH_POOL_INDEPENDENT_QUALITY_REQUIRED'))
  draftController.dispose()
})

test('宿主拒绝与无回读使用不同诊断并保留草稿', async () => {
  const rejectedScope = fakeScope({ limits: {} })
  rejectedScope.setWriteError(new Error('policy denied token=super-secret'))
  const rejected = new RefractCardController(rejectedScope)
  rejected.inject().editLimit('relaxBudget', true)
  await rejected.save()
  assert.match(String(rejected.getSnapshot().failureMessage), /宿主拒绝保存.*policy denied/)
  assert.doesNotMatch(String(rejected.getSnapshot().failureMessage), /super-secret/)
  assert.match(String(rejected.getSnapshot().failureMessage), /token=\[REDACTED\]/)
  assert.ok(rejected.getSnapshot().issues.some(issue => issue.code === 'SETTINGS_HOST_REJECTED'))
  assert.equal(rejected.getSnapshot().dirty, true)
  rejected.dispose()

  const unreadScope = fakeScope({ limits: {} })
  unreadScope.setAccepting(false)
  const unread = new RefractCardController(unreadScope)
  unread.inject().editLimit('relaxContext', true)
  await unread.save()
  assert.match(String(unread.getSnapshot().failureMessage), /保存结果未确认/)
  assert.ok(unread.getSnapshot().issues.some(issue => issue.code === 'SETTINGS_READBACK_UNCONFIRMED'))
  assert.equal(unread.getSnapshot().dirty, true)
  unread.dispose()
})

test('设置页直接复用核心冻结档案并保留条件价格来源', async () => {
  const raw = JSON.parse(await readFile(new URL('../../../../data/model-profiles-v2.json', import.meta.url), 'utf8'))
  const direct = raw.profiles.find((row: {provider:string;model:string}) =>
    row.provider === 'deepseek-official' && row.model === 'deepseek-v4-pro')
  assert.equal(raw.schema_version, 'refractrouter-model-profiles-v2')
  assert.equal(direct.pricing_materialization.selectedTier, 'peak')
  assert.equal(direct.pricing.inputPer1k * 1000, 1.32)
  const ark = raw.profiles.find((row: {provider:string;model:string}) =>
    row.provider === 'ark' && row.model === 'deepseek-v4-pro')
  assert.equal(ark.pricing_basis.actualProviderBilling, false)
  assert.ok(ark.sources[0].url.startsWith('https://'))
})

test('client bundle registers in the host module format and exports the plugin face', async () => {
  const source = await readFile(new URL('../dist/client.js', import.meta.url), 'utf8')
  const localeSource = await readFile(new URL('../src/client/locale.ts', import.meta.url), 'utf8')
  assert.ok(source.startsWith('window.__ModuleLoader__.load({'), 'bundle must register a module factory')
  assert.ok(source.includes('"dsh-refractrouter-validation"'))
  assert.ok(source.includes('v4ShowAdvanced'))
  assert.ok(source.includes('v4HideAdvanced'))
  assert.ok(localeSource.includes('规划模型（Planner）'))
  assert.ok(source.includes('Planner model'))
  assert.ok(localeSource.includes('当前生产合同也要求存在'))
  assert.ok(source.includes('Manufacturer reference only'))
  assert.ok(localeSource.includes('请先修正以下阻断问题'))
  assert.ok(source.includes('saveBlockedButton'))
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
  assert.deepEqual(exports.inject, ['slots', 'locale', 'remote', 'remote.session', 'remote.llm', 'settingsScope'])

  const effects: Array<() => unknown> = []
  const discoveryCalls: Array<{namespace:string;request:Record<string,unknown>}> = []
  let boundNamespace: string | undefined
  let slotDeclaration: (() => Generator<unknown>) | undefined
  let registeredOptions: Record<string, unknown> | undefined
  exports.apply({
    effect: (setup: () => unknown) => { effects.push(setup) },
    locale: { register: () => undefined },
    remote: { session: { modelCatalog: async () => ({ ok: true, value: { groups: [], failures: [] } }) },
      llm:{discoverModels:async(namespace:string,request:Record<string,unknown>)=>{
        discoveryCalls.push({namespace,request});return {ok:true,value:[]}}} },
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
  const injected = (registeredOptions!.inject as () => {
    loadRouteProfiles(connection?:unknown):Promise<unknown>
  })()
  await injected.loadRouteProfiles()
  assert.deepEqual(discoveryCalls, [{namespace:'refractagent-route-profiles',request:{provider:'local'}}])
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

test('unlimited time overlays independently and can be switched off', () => {
  const config=configure({limits:{unlimitedTime:false,relaxBudget:false,relaxContext:false}})
  validateSettingsSection({limits:{unlimitedTime:true}})
  const enabled=overlaySettings(config,{limits:{unlimitedTime:true,relaxBudget:false,relaxContext:false}})
  assert.equal(enabled.limits?.unlimitedTime,true)
  assert.equal(enabled.limits?.relaxBudget,false)
  assert.equal(overlaySettings(enabled,{limits:{unlimitedTime:false}}).limits?.unlimitedTime,false)
  assert.throws(()=>validateSettingsSection({limits:{unlimitedTime:'yes'} as never}),/boolean/)
})

test('v4 structured edits cover objective, security and repeatable rows without losing JSON-only fields', async () => {
  const original = v4ProviderConfig()
  const providerConfig = { ...original, models: original.models.map(model => model.id === 'router'
    ? { ...model, requestOptions: { futureOption: { retained: true } } } : model) }
  validateSettingsSection({ providerConfig })
  const scope = fakeScope({ providerConfig })
  const controller = new RefractCardController(scope)
  const face = controller.inject()
  assert.equal(controller.getSnapshot().automaticRouting, true)
  face.editV4QualityMin(87)
  face.editV4DagMode('never')
  face.editV4DataMode('desensitized')
  face.editV4SensitiveTerms('内部\n客户\n内部\n')
  face.editV4Classifier(true, 'router')
  face.upsertV4Row('trustPolicies', {
    id: 'team-us', residency: 'US', auditLogging: true, allowsSensitiveData: false,
  })
  face.upsertV4Row('providers', {
    id: 'trusted', type: 'openai-compatible', baseUrl: 'https://trusted.example/v1',
    credentialEnv: 'TRUSTED_MODEL_KEY', deployment: 'trusted-cloud', trustPolicy: 'team-us',
  })
  face.upsertV4Row('models', {
    id: 'trusted-worker', provider: 'trusted', model: 'trusted-model', roles: ['worker'],
    contextWindow: 64000, pricing: { unit: 'USD', inputPer1k: 0.01, outputPer1k: 0.02 },
  })
  face.removeV4Row('models', 'worker')
  await controller.save()
  const saved = scope.getSnapshot().value?.providerConfig
  assert.equal(saved?.objective?.qualityMin, 87)
  assert.equal(saved?.objective?.dagMode, 'never')
  assert.equal(saved?.security?.dataMode, 'desensitized')
  assert.deepEqual(saved?.security?.sensitiveTerms, ['内部', '客户'])
  assert.deepEqual(saved?.security?.classifier, { enabled: true, modelId: 'router' })
  assert.deepEqual((saved?.models?.[0] as { requestOptions?: unknown }).requestOptions,
    { futureOption: { retained: true } })
  assert.equal(saved?.trustPolicies?.length, 2)
  assert.equal(saved?.providers?.length, 3)
  assert.deepEqual(saved?.models?.map(row => (row as { id: string }).id), ['router', 'judge', 'trusted-worker'])
  assert.deepEqual(JSON.parse(controller.getSnapshot().providerJson), saved)
  controller.dispose()
})

test('v4 structured edits can update, rename and remove rows, then discard as one rollback', () => {
  const providerConfig = v4ProviderConfig()
  const controller = new RefractCardController(fakeScope({ providerConfig }))
  const face = controller.inject()
  face.upsertV4Row('providers', { ...providerConfig.providers[0], id: 'external-next' }, 'external')
  assert.equal((controller.getSnapshot().provider?.providers?.[0] as { id: string }).id, 'external-next')
  face.removeV4Row('trustPolicies', 'team-cn')
  assert.deepEqual(controller.getSnapshot().provider?.trustPolicies, [])
  face.discard()
  assert.deepEqual(controller.getSnapshot().provider, providerConfig)
  assert.equal(controller.getSnapshot().dirty, false)
  controller.dispose()
})

test('v4 structural preview reports inventory without making a routing or security decision', () => {
  const preview = buildV4FeasibilityPreview(v4ProviderConfig())
  assert.deepEqual(preview?.roleCounts, { planner: 1, worker: 2, judge: 1, classifier: 1 })
  assert.deepEqual(preview?.missingRoles, [])
  assert.equal(preview?.hasLocalDeployment, true)
  assert.equal(preview?.providerCount, 2)
  assert.equal(preview?.modelCount, 3)
  assert.equal(preview?.requiresCoreValidation, true)
  assert.equal(buildV4FeasibilityPreview(dshProviderConfig()), undefined)
})

test('settings drafts reject embedded secrets and expose incomplete credential references as validation errors', () => {
  const controller = new RefractCardController(fakeScope({ providerConfig: v4ProviderConfig() }))
  const face = controller.inject()
  assert.throws(() => face.upsertV4Row('providers', {
    id: 'bad', type: 'openai-compatible', deployment: 'external-cloud', apiKey: 'secret-value',
  }), /credentialEnv references/)
  face.editProviderJson(JSON.stringify({ ...v4ProviderConfig(), providers: [{
    id: 'bad', type: 'openai-compatible', deployment: 'external-cloud', token: 'secret-value',
  }] }))
  assert.match(String(controller.getSnapshot().providerJsonError), /credentialEnv references/)
  face.upsertV4Row('providers', {
    id: 'bad-ref', type: 'openai-compatible', deployment: 'external-cloud', credentialEnv: 'not-an-env-ref',
  })
  assert.match(String(controller.getSnapshot().providerJsonError), /environment-variable reference/)
  controller.dispose()
})
