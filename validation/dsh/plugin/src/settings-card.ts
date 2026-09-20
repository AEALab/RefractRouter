import afpData from './afp-metadata.json' with { type: 'json' }
export const afpMetadata: { snapshotDate: string; sourceUrl: string; tiers: number[];
  models: Array<{model: string; coefficient: number; inputCoefficient: number; outputCoefficient: number; planTiers: string[]; thinkingAuto: string}>
} = afpData
import examples from './provider-examples.json' with { type: 'json' }
/** RefractAgent 设置卡片的纯逻辑层：staged 表单、写入规划与快照投影。
 * 宿主契约测试与浏览器 client bundle 共用；不依赖 React、Node API 或 DSH 包。
 */
export const SETTINGS_NAMESPACE = 'refractagent'

export type ModeKey = 'economy' | 'balanced' | 'quality'
export const MODE_KEYS: readonly ModeKey[] = ['economy', 'balanced', 'quality']
export type LimitKey = 'relaxBudget' | 'relaxContext' | 'unlimitedTime'
export type CardField = 'providerConfig' | 'limits'
export type V4CollectionKey = 'providers' | 'models' | 'trustPolicies'
export type V4DagMode = 'auto' | 'never' | 'force'
export type V4DataMode = 'live' | 'desensitized' | 'synthetic'

/** 卡片侧的 providerConfig 视图：结构化字段之外的原样保留，确保编辑往返不丢数据。 */
export interface ProviderConfigView {
  schemaVersion?: string
  billingUnit?: string
  qualityMin?: number
  plannerThinking?: string
  defaultReasoningEffort?: string
  strategies?: Partial<Record<ModeKey, StrategyView>>
  objective?: { qualityMin?: number; primary?: string; secondary?: string; dagMode?: string; [field: string]: unknown }
  security?: { dataMode?: string; sensitiveTerms?: unknown[]; [field: string]: unknown }
  trustPolicies?: unknown[]
  providers?: unknown[]
  models?: unknown[]
  [field: string]: unknown
}
export interface StrategyView {
  maxAfpCoefficient?: number
  reasoningEffort?: string
  models?: string[]
}
/** 表单只把配置 ID 映射为可读名称，不参与候选模型的路由判定。 */
export function candidateChoices(provider: ProviderConfigView | undefined): Array<{ id: string; label: string; costLabel?: string; planLabel?: string; thinkingAuto?: string }> {
  const models = (Array.isArray(provider?.models) ? provider.models : []).filter(
    (row): row is Record<string, unknown> => isRecord(row) && row.role !== 'judge'
      && typeof row.id === 'string' && typeof row.model === 'string',
  )
  return models.map(row => {
    const duplicate = models.filter(other => other.model === row.model).length > 1
    const reference = afpMetadata.models.find(m => m.model === row.model)
    const providerRow = provider?.providers?.find(p => isRecord(p) && p.id === row.provider)
    const ark = isRecord(providerRow) && providerRow.type === 'ark-agent-plan'
    return {
      ...(ark && reference ? { costLabel: `AFP ${reference.inputCoefficient} / ${reference.outputCoefficient}`,
        thinkingAuto: reference.thinkingAuto,
        planLabel: reference.planTiers.includes('small') ? 'Small / Medium / Large / Max' : 'Medium / Large / Max' } : {}),
      id: row.id as string,
      label: duplicate ? `${row.model} · ${row.provider} (${row.id})` : row.model as string,
    }
  })
}

export interface LimitsView {
  relaxBudget?: boolean
  relaxContext?: boolean
  unlimitedTime?: boolean
}
export interface SectionView {
  providerConfig?: ProviderConfigView
  limits?: LimitsView
}

/** 浏览器 settingsScope 的结构化契约（dsh-client-ui-settings 提供实现）。 */
export interface CardScopeSnapshot {
  status: 'loading' | 'ready' | 'unavailable'
  value?: SectionView
  base?: SectionView
  user?: SectionView
  writable: boolean
}
export interface CardScope {
  getSnapshot(): CardScopeSnapshot
  subscribe(listener: () => void): () => void
  set(field: string, value: unknown): Promise<void>
  unset(field: string): Promise<void>
}

export interface RefractCardProjection {
  status: 'loading' | 'ready' | 'unavailable'
  writable: boolean
  dirty: boolean
  saving: boolean
  failed: boolean
  hasProvider: boolean
  overriddenProvider: boolean
  overriddenLimits: boolean
  provider: ProviderConfigView | undefined
  providerCleared: boolean
  providerJson: string
  providerJsonError: string | null
  limits: LimitsView
  automaticRouting: boolean
  strategyModelText: Partial<Record<ModeKey, string>>
  limitsCleared: boolean
}

type StagedEdit = { kind: 'clear' } | { kind: 'set'; value: unknown }

export interface RefractCardFace {
  hooks: { refractCard: { subscribe(listener: () => void): () => void; getSnapshot(): RefractCardProjection } }
  editPlannerThinking(value: string): void
  editDefaultEffort(value: string): void
  editStrategyEffort(mode: ModeKey, value: string): void
  editStrategyAfpCeiling(mode: ModeKey, value: string): void
  editStrategyModels(mode: ModeKey, text: string): void
  editV4QualityMin(value: number): void
  editV4DagMode(value: V4DagMode): void
  editV4DataMode(value: V4DataMode): void
  editV4SensitiveTerms(text: string): void
  upsertV4Row(collection: V4CollectionKey, value: Record<string, unknown>, previousId?: string): void
  removeV4Row(collection: V4CollectionKey, id: string): void
  editLimit(key: LimitKey, checked: boolean): void
  editProviderJson(text: string): void
  resetField(field: CardField): void
  save(): void
  discard(): void
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function assertCredentialReferences(provider: ProviderConfigView): void {
  for (const row of Array.isArray(provider.providers) ? provider.providers : []) {
    if (!isRecord(row)) continue
    if (['apiKey', 'api_key', 'token', 'secret', 'credential'].some(key => Object.hasOwn(row, key))) {
      throw new Error('provider credentials must be saved as credentialEnv references')
    }
    if (row.credentialEnv !== undefined
      && (typeof row.credentialEnv !== 'string' || !/^[A-Z][A-Z0-9_]*$/.test(row.credentialEnv))) {
      throw new Error('credentialEnv must be an environment-variable reference')
    }
  }
}

/** 键序无关的 JSON 等值比较，用于写入前后核对宿主是否接受了值。 */
function stableStringify(value: unknown): string {
  if (Array.isArray(value)) return '[' + value.map(stableStringify).join(',') + ']'
  if (isRecord(value)) {
    return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + stableStringify(value[key])).join(',') + '}'
  }
  return JSON.stringify(value) ?? 'null'
}

export class RefractCardController {
  private readonly scope: CardScope
  private readonly listeners = new Set<() => void>()
  private readonly staged = new Map<CardField, StagedEdit>()
  private providerJson = ''
  private jsonEdited = false
  private modelText: Partial<Record<ModeKey, string>> = {}
  private providerJsonError: string | null = null
  private saving = false
  private failed = false
  private cached: RefractCardProjection | undefined
  private readonly offScope: () => void

  constructor(scope: CardScope) {
    this.scope = scope
    this.offScope = scope.subscribe(() => {
      if (!this.jsonEdited && !this.staged.has('providerConfig')) this.syncProviderJson()
      this.publish()
    })
    this.syncProviderJson()
  }

  /** store 面：供 slot 系统包装成 useRefractCard hook。 */
  subscribe(listener: () => void): () => void {
    this.listeners.add(listener)
    return () => { this.listeners.delete(listener) }
  }

  getSnapshot(): RefractCardProjection {
    if (this.cached === undefined) this.cached = this.project()
    return this.cached
  }

  /** slot 注入面：快照源与全部表单动作。 */
  inject(): RefractCardFace {
    return {
      hooks: { refractCard: this },
      editPlannerThinking: value => this.editPlannerThinking(value),
      editDefaultEffort: value => this.editDefaultEffort(value),
      editStrategyEffort: (mode, value) => this.editStrategyEffort(mode, value),
      editStrategyAfpCeiling: (mode, value) => this.editStrategyAfpCeiling(mode, value),
      editStrategyModels: (mode, text) => this.editStrategyModels(mode, text),
      editV4QualityMin: value => this.editV4QualityMin(value),
      editV4DagMode: value => this.editV4DagMode(value),
      editV4DataMode: value => this.editV4DataMode(value),
      editV4SensitiveTerms: text => this.editV4SensitiveTerms(text),
      upsertV4Row: (collection, value, previousId) => this.upsertV4Row(collection, value, previousId),
      removeV4Row: (collection, id) => this.removeV4Row(collection, id),
      editLimit: (key, checked) => this.editLimit(key, checked),
      editProviderJson: text => this.editProviderJson(text),
      resetField: field => this.resetField(field),
      save: () => { void this.save() },
      discard: () => this.discard(),
    }
  }

  editPlannerThinking(value: string): void {
    const provider = this.currentProvider() ?? structuredClone(examples['openai-compatible'])
    const next: ProviderConfigView = { ...provider }
    if (value === 'inherit') delete next.plannerThinking
    else if (['enabled','disabled'].includes(value)) next.plannerThinking = value
    else throw new Error('invalid plannerThinking')
    this.stageProvider(next)
  }

  editDefaultEffort(value: string): void {
    const provider: ProviderConfigView = this.currentProvider() ?? structuredClone(examples['openai-compatible'])
    const effort = value.trim()
    const next: ProviderConfigView = { ...provider }
    if (effort === '') delete next.defaultReasoningEffort
    else next.defaultReasoningEffort = effort
    this.stageProvider(next)
  }

  editStrategyEffort(mode: ModeKey, value: string): void {
    const provider: ProviderConfigView = this.currentProvider() ?? structuredClone(examples['openai-compatible'])
    const effort = value.trim()
    const strategies = { ...provider.strategies }
    const entry: StrategyView = { ...strategies[mode] }
    if (effort === '') delete entry.reasoningEffort
    else entry.reasoningEffort = effort
    if (Object.keys(entry).length > 0) strategies[mode] = entry
    else delete strategies[mode]
    this.stageProvider({ ...provider, strategies })
  }

  editStrategyAfpCeiling(mode: ModeKey, value: string): void {
    const provider = this.currentProvider()
    if (!provider || provider.billingUnit !== 'AFP') return
    const entry = { ...provider.strategies?.[mode] }
    if (value === '') delete entry.maxAfpCoefficient
    else {
      const coefficient = Number(value)
      if (!Number.isFinite(coefficient) || coefficient <= 0) return
      entry.maxAfpCoefficient = coefficient
    }
    this.stageProvider({ ...provider, strategies: { ...provider.strategies, [mode]: entry } })
  }

  editStrategyModels(mode: ModeKey, text: string): void {
    const provider: ProviderConfigView = this.currentProvider() ?? structuredClone(examples['openai-compatible'])
    this.modelText[mode] = text
    const models = [...new Set(text.split(/\r?\n/).map(line => line.trim()).filter(line => line !== ''))]
    const strategies = { ...provider.strategies }
    const entry: StrategyView = { ...strategies[mode] }
    if (models.length === 0) delete entry.models
    else entry.models = models
    if (Object.keys(entry).length > 0) strategies[mode] = entry
    else delete strategies[mode]
    this.stageProvider({ ...provider, strategies })
  }

  editV4QualityMin(value: number): void {
    if (!Number.isFinite(value) || value < 0 || value > 100) throw new Error('qualityMin must be in 0..100')
    const provider = this.v4Provider()
    this.stageProvider({ ...provider, objective: { ...provider.objective, qualityMin: value } })
  }

  editV4DagMode(value: V4DagMode): void {
    if (!['auto', 'never', 'force'].includes(value)) throw new Error('invalid dagMode')
    const provider = this.v4Provider()
    this.stageProvider({ ...provider, objective: { ...provider.objective, dagMode: value } })
  }

  editV4DataMode(value: V4DataMode): void {
    if (!['live', 'desensitized', 'synthetic'].includes(value)) throw new Error('invalid dataMode')
    const provider = this.v4Provider()
    this.stageProvider({ ...provider, security: { ...provider.security, dataMode: value } })
  }

  editV4SensitiveTerms(text: string): void {
    const provider = this.v4Provider()
    const sensitiveTerms = [...new Set(text.split(/\r?\n/).map(value => value.trim()).filter(Boolean))]
    this.stageProvider({ ...provider, security: { ...provider.security, sensitiveTerms } })
  }

  upsertV4Row(collection: V4CollectionKey, value: Record<string, unknown>, previousId?: string): void {
    const provider = this.v4Provider()
    if (typeof value.id !== 'string' || value.id.trim() === '') throw new Error(`${collection} rows require an id`)
    if (collection === 'providers') assertCredentialReferences({ providers: [value] })
    const target = previousId ?? value.id
    const rows = Array.isArray(provider[collection]) ? [...provider[collection] as unknown[]] : []
    const index = rows.findIndex(row => isRecord(row) && row.id === target)
    const cloned = structuredClone(value)
    if (index === -1) rows.push(cloned)
    else rows[index] = cloned
    this.stageProvider({ ...provider, [collection]: rows })
  }

  removeV4Row(collection: V4CollectionKey, id: string): void {
    const provider = this.v4Provider()
    const rows = (Array.isArray(provider[collection]) ? provider[collection] as unknown[] : [])
      .filter(row => !isRecord(row) || row.id !== id)
    this.stageProvider({ ...provider, [collection]: rows })
  }

  editLimit(key: LimitKey, checked: boolean): void {
    this.stageLimits({ ...this.currentLimits(), [key]: checked })
  }

  editProviderJson(text: string): void {
    this.jsonEdited = true
    this.modelText = {}
    this.providerJson = text
    if (text.trim() === '') {
      this.providerJsonError = null
      if (this.overridden('providerConfig')) this.staged.set('providerConfig', { kind: 'clear' })
      else this.staged.delete('providerConfig')
      this.publish()
      return
    }
    try {
      const parsed: unknown = JSON.parse(text)
      if (!isRecord(parsed)) throw new Error('providerConfig must be a JSON object')
      assertCredentialReferences(parsed)
      if (parsed.strategies !== undefined && (!isRecord(parsed.strategies)
        || Object.values(parsed.strategies).some(row => !isRecord(row)
          || (row.models !== undefined && (!Array.isArray(row.models) || row.models.some(id => typeof id !== 'string')))))) {
        throw new Error('strategies.models must be an array of model IDs')
      }
      this.staged.set('providerConfig', { kind: 'set', value: parsed })
      this.providerJsonError = null
    } catch (error) {
      this.providerJsonError = error instanceof Error ? error.message : String(error)
    }
    this.publish()
  }

  resetField(field: CardField): void {
    if (!this.overridden(field)) return
    this.staged.set(field, { kind: 'clear' })
    if (field === 'providerConfig') {
      const baseProvider = this.baseSection()?.providerConfig
      this.providerJson = baseProvider === undefined ? '' : JSON.stringify(baseProvider, null, 2)
      this.providerJsonError = null
    }
    this.publish()
  }

  discard(): void {
    if (this.staged.size === 0 && !this.failed && !this.jsonEdited) return
    this.staged.clear()
    this.failed = false
    this.syncProviderJson()
    this.publish()
  }

  /** 写出全部 staged 编辑，然后按宿主接受的段落核对是否落盘。 */
  async save(): Promise<void> {
    if (this.saving) return
    if (this.providerJsonError !== null) {
      this.failed = true
      this.publish()
      return
    }
    const snap = this.snapshot()
    if (snap.status !== 'ready' || !snap.writable) return
    const writes: Array<{ field: CardField; run: () => Promise<void> }> = []
    const provider = this.staged.get('providerConfig')
    if (provider?.kind === 'clear') {
      if (this.overridden('providerConfig')) writes.push({ field: 'providerConfig', run: () => this.scope.unset('providerConfig') })
    } else if (provider?.kind === 'set' && stableStringify(provider.value) !== stableStringify(snap.value?.providerConfig)) {
      writes.push({ field: 'providerConfig', run: () => this.scope.set('providerConfig', provider.value) })
    }
    const limits = this.staged.get('limits')
    if (limits?.kind === 'clear') {
      if (this.overridden('limits')) writes.push({ field: 'limits', run: () => this.scope.unset('limits') })
    } else if (limits?.kind === 'set' && stableStringify(limits.value) !== stableStringify(snap.value?.limits)) {
      writes.push({ field: 'limits', run: () => this.scope.set('limits', limits.value) })
    }
    if (writes.length === 0) {
      this.staged.clear()
      this.syncProviderJson()
      this.publish()
      return
    }
    this.saving = true
    this.failed = false
    this.publish()
    for (const write of writes) await write.run().catch(() => undefined)
    let landed = true
    const user = this.userLayer()
    for (const write of writes) {
      const staged = this.staged.get(write.field)
      if (staged?.kind === 'set') {
        if (user === undefined || user[write.field] === undefined
          || stableStringify(user[write.field]) !== stableStringify(staged.value)) landed = false
      } else if (staged?.kind === 'clear') {
        if (user !== undefined && Object.hasOwn(user, write.field)) landed = false
      }
    }
    if (landed) {
      this.staged.clear()
      this.syncProviderJson()
    }
    this.saving = false
    this.failed = !landed
    this.publish()
  }

  dispose(): void {
    this.offScope()
    this.listeners.clear()
  }

  private snapshot(): CardScopeSnapshot {
    return this.scope.getSnapshot()
  }

  private baseSection(): SectionView | undefined {
    return this.snapshot().base
  }

  private userLayer(): SectionView | undefined {
    return this.snapshot().user
  }

  private overridden(field: CardField): boolean {
    const user = this.userLayer()
    return user !== undefined && Object.hasOwn(user, field)
  }

  private currentProvider(): ProviderConfigView | undefined {
    const staged = this.staged.get('providerConfig')
    if (staged?.kind === 'set') return staged.value as ProviderConfigView
    if (staged?.kind === 'clear') return this.baseSection()?.providerConfig
    return this.snapshot().value?.providerConfig
  }

  private v4Provider(): ProviderConfigView {
    const provider = this.currentProvider()
    if (provider?.schemaVersion !== 'refractagent-providers-v4') {
      throw new Error('structured automatic-routing edits require providerConfig v4')
    }
    return provider
  }

  private currentLimits(): LimitsView {
    const staged = this.staged.get('limits')
    if (staged?.kind === 'set') return staged.value as LimitsView
    if (staged?.kind === 'clear') return this.baseSection()?.limits ?? {}
    return this.snapshot().value?.limits ?? {}
  }

  private stageProvider(value: ProviderConfigView): void {
    this.staged.set('providerConfig', { kind: 'set', value })
    this.providerJson = JSON.stringify(value, null, 2)
    this.providerJsonError = null
    this.publish()
  }

  private stageLimits(value: LimitsView): void {
    this.staged.set('limits', { kind: 'set', value })
    this.publish()
  }

  private syncProviderJson(): void {
    this.jsonEdited = false
    this.modelText = {}
    const provider = this.currentProvider()
    this.providerJson = provider === undefined ? '' : JSON.stringify(provider, null, 2)
    this.providerJsonError = null
  }

  private project(): RefractCardProjection {
    const snap = this.snapshot()
    const providerStage = this.staged.get('providerConfig')
    const limitsStage = this.staged.get('limits')
    return {
      status: snap.status,
      writable: snap.writable,
      dirty: this.staged.size > 0 || this.jsonEdited,
      saving: this.saving,
      failed: this.failed,
      hasProvider: this.currentProvider() !== undefined,
      overriddenProvider: this.overridden('providerConfig'),
      overriddenLimits: this.overridden('limits'),
      provider: this.currentProvider(),
      providerCleared: providerStage?.kind === 'clear',
      providerJson: this.providerJson,
      providerJsonError: this.providerJsonError,
      limits: this.currentLimits(),
      automaticRouting: this.currentProvider()?.schemaVersion === 'refractagent-providers-v4',
      strategyModelText: { ...this.modelText },
      limitsCleared: limitsStage?.kind === 'clear',
    }
  }

  private publish(): void {
    this.cached = undefined
    for (const listener of [...this.listeners]) listener()
  }
}
