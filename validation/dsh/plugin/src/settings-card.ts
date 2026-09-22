import afpData from './afp-metadata.json' with { type: 'json' }
export const afpMetadata: { snapshotDate: string; sourceUrl: string; tiers: number[];
  models: Array<{model: string; coefficient: number; inputCoefficient: number; outputCoefficient: number; planTiers: string[]; thinkingAuto: string}>
} = afpData
import examples from './provider-examples.json' with { type: 'json' }
/** RefractAgent 设置卡片的纯逻辑层：staged 表单、写入规划与快照投影。
 * 宿主契约测试与浏览器 client bundle 共用；不依赖 React、Node API 或 DSH 包。
 */
export const SETTINGS_NAMESPACE = 'refractagent'
export const DEPLOYMENT_OPTIONS = [
  { value: 'local', label: '真实本地（local）' },
  { value: 'external-cloud', label: '普通外部云（external-cloud）' },
  { value: 'trusted-cloud', label: '可信外部云（trusted-cloud）' },
  { value: 'simulated-local', label: '云模型模拟本地（simulated-local）' },
] as const

export type ModeKey = 'economy' | 'balanced' | 'quality'
export const MODE_KEYS: readonly ModeKey[] = ['economy', 'balanced', 'quality']
export type LimitKey = 'relaxBudget' | 'relaxContext' | 'unlimitedTime'
export type CardField = 'router' | 'providerConfig' | 'dshModelPool' | 'limits'
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

export interface V4FeasibilityPreview {
  providerCount: number
  modelCount: number
  trustPolicyCount: number
  roleCounts: Record<'planner' | 'worker' | 'judge' | 'classifier', number>
  deploymentCounts: Record<string, number>
  missingRoles: Array<'planner' | 'worker' | 'judge'>
  hasLocalDeployment: boolean
  requiresCoreValidation: true
}

/**
 * 浏览器只投影配置清单事实，不判断敏感数据是否合法或选择路线。
 * 完整可行性必须交给 Python compile_configuration。
 */
export function buildV4FeasibilityPreview(provider: ProviderConfigView | undefined): V4FeasibilityPreview | undefined {
  if (provider?.schemaVersion !== 'refractagent-providers-v4') return undefined
  const providers = (Array.isArray(provider.providers) ? provider.providers : []).filter(isRecord)
  const models = (Array.isArray(provider.models) ? provider.models : []).filter(isRecord)
  const policies = (Array.isArray(provider.trustPolicies) ? provider.trustPolicies : []).filter(isRecord)
  const roleCounts: V4FeasibilityPreview['roleCounts'] = { planner: 0, worker: 0, judge: 0, classifier: 0 }
  for (const model of models) {
    const roles = Array.isArray(model.roles) ? model.roles : []
    for (const role of Object.keys(roleCounts) as Array<keyof typeof roleCounts>) {
      if (roles.includes(role)) roleCounts[role] += 1
    }
  }
  const deploymentCounts: Record<string, number> = {}
  for (const row of providers) {
    const deployment = typeof row.deployment === 'string' ? row.deployment : 'missing'
    deploymentCounts[deployment] = (deploymentCounts[deployment] ?? 0) + 1
  }
  return {
    providerCount: providers.length,
    modelCount: models.length,
    trustPolicyCount: policies.length,
    roleCounts,
    deploymentCounts,
    missingRoles: (['planner', 'worker', 'judge'] as const).filter(role => roleCounts[role] === 0),
    hasLocalDeployment: (deploymentCounts.local ?? 0) > 0,
    requiresCoreValidation: true,
  }
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
  router?: RouterConnectionView
  providerConfig?: ProviderConfigView
  dshModelPool?: DshModelPoolView
  limits?: LimitsView
}
export interface RouterConnectionView { url:string; credential?:string; project?:string }
export interface DshModelPoolView {
  schemaVersion: 'refractagent-dsh-model-pool-v1' | 'refractagent-dsh-model-pool-v2'
  billingUnit?: string
  allowSharedJudge?: boolean
  routes: Array<{provider:string;model:string;enabled?:boolean;deployment:string;trustPolicy?:string;
    overrides?:Record<string,unknown>}>
  roleOverrides?: {planner?:string;judge?:string;classifier?:string;workers?:string[]}
  objective?:Record<string,unknown>
  security?:Record<string,unknown>
  trustPolicies?:Array<Record<string,unknown>>
  [field:string]:unknown
}

export type SettingsIssueCode =
  | 'DSH_POOL_DEPLOYMENT_REQUIRED'
  | 'DSH_POOL_TRUST_POLICY_REQUIRED'
  | 'DSH_POOL_TRUST_POLICY_INVALID'
  | 'DSH_POOL_EXTERNAL_ACK_REQUIRED'
  | 'DSH_POOL_ROLE_ROUTE_UNAVAILABLE'
  | 'DSH_POOL_SHARED_JUDGE_FORBIDDEN'
  | 'DSH_POOL_LEGACY_SCHEMA'
  | 'DSH_POOL_INDEPENDENT_QUALITY_REQUIRED'
  | 'DSH_POOL_PUBLIC_PROFILE_INCOMPLETE'
  | 'DSH_POOL_MANUAL_PROFILE_INCOMPLETE'
  | 'DSH_POOL_USER_DECLARED_UNCALIBRATED'
  | 'SETTINGS_HOST_REJECTED'
  | 'SETTINGS_READBACK_UNCONFIRMED'

export interface SettingsIssue {
  code: SettingsIssueCode
  severity: 'error' | 'warning'
  field: string
  route?: string
  message: string
}

export interface PublicModelProfileSummary {
  provider: string
  model: string
  pricing: Record<string, number | string>
  quality_profile?: { score: number; source: { kind: string } } | null
}

const NON_RUNNABLE_CODES = new Set<SettingsIssueCode>([
  'DSH_POOL_INDEPENDENT_QUALITY_REQUIRED',
  'DSH_POOL_PUBLIC_PROFILE_INCOMPLETE',
  'DSH_POOL_MANUAL_PROFILE_INCOMPLETE',
])

export function blocksDshModelPoolRun(issue: SettingsIssue): boolean {
  return NON_RUNNABLE_CODES.has(issue.code)
}

function policyId(value: Record<string, unknown>): string | undefined {
  return typeof value.id === 'string' && value.id.trim() ? value.id : undefined
}

/** 仅检查设置与部署边界；质量排序、职责分配和运行准入仍由 Python 核心决定。 */
export function buildDshModelPoolIssues(pool: DshModelPoolView | undefined,
  publicProfiles: readonly PublicModelProfileSummary[] = []): SettingsIssue[] {
  if (!pool) return []
  const issues: SettingsIssue[] = []
  if (pool.schemaVersion === 'refractagent-dsh-model-pool-v1') {
    issues.push({code:'DSH_POOL_LEGACY_SCHEMA',severity:'warning',field:'schemaVersion',
      message:'这是旧版模型池配置。迁移到 v2 后，旧的手工质量与时延值将被移除，不会作为运行证据。'})
  }
  const policies = new Map((pool.trustPolicies ?? []).map(row => [policyId(row), row] as const)
    .filter((row): row is [string, Record<string, unknown>] => row[0] !== undefined))
  const dataMode = typeof pool.security?.dataMode === 'string' ? pool.security.dataMode : 'live'
  const enabledRoutes = pool.routes.filter(row => row.enabled !== false)
  const routeKeys = new Set(enabledRoutes.map(row => `${row.provider}/${row.model}`))
  for (const route of enabledRoutes) {
    const identity = `${route.provider}/${route.model}`
    if (!DEPLOYMENT_OPTIONS.some(option => option.value === route.deployment)) {
      issues.push({code:'DSH_POOL_DEPLOYMENT_REQUIRED',severity:'error',field:'deployment',route:identity,
        message:`${identity}：请选择部署属性。`})
    }
    const needsPolicy = route.deployment === 'trusted-cloud'
      || (route.deployment === 'simulated-local' && dataMode === 'live')
    const policy = route.trustPolicy ? policies.get(route.trustPolicy) : undefined
    if (needsPolicy && !policy) {
      issues.push({code:'DSH_POOL_TRUST_POLICY_REQUIRED',severity:'error',field:'trustPolicy',route:identity,
        message:`${identity}：当前部署和数据模式需要选择有效的信任策略。`})
    }
    if (policy && (typeof policy.residency !== 'string' || !policy.residency.trim()
      || policy.auditLogging !== true || policy.allowsSensitiveData !== true)) {
      issues.push({code:'DSH_POOL_TRUST_POLICY_INVALID',severity:'error',field:'trustPolicies',route:identity,
        message:`${identity}：信任策略必须填写驻留区域，并明确启用审计及允许敏感数据。`})
    }
    if (route.deployment === 'simulated-local' && dataMode === 'live' && policy
      && policy.acknowledgeExternalTransmission !== true) {
      issues.push({code:'DSH_POOL_EXTERNAL_ACK_REQUIRED',severity:'error',field:'trustPolicies',route:identity,
        message:`${identity}：云模型模拟本地仍会外传真实数据，必须明确确认外部传输。`})
    }
    const profile = publicProfiles.find(row => row.provider === route.provider && row.model === route.model)
    const overrides = route.overrides ?? {}
    if (!profile) {
      const missing = ['inputPer1k','outputPer1k']
        .filter(key => typeof overrides[key] !== 'number')
      if (missing.length) {
        issues.push({code:'DSH_POOL_MANUAL_PROFILE_INCOMPLETE',severity:'warning',field:'overrides',route:identity,
          message:`${identity}：没有公开价格档案，仍缺少 ${missing.join('、')}；可以保存草稿，但尚不能运行。`})
      }
    }
    if (profile?.quality_profile?.source.kind !== 'independent-third-party') {
      issues.push({code:'DSH_POOL_INDEPENDENT_QUALITY_REQUIRED',severity:'warning',field:'quality_profile',route:identity,
        message:`${identity}：没有合规的独立第三方质量先验，无法参与路由；这不是价格或时延配置问题。`})
    }
  }
  const roles = pool.roleOverrides
  if (roles) {
    for (const role of ['planner','judge','classifier'] as const) {
      const route = roles[role]
      if (route && !routeKeys.has(route)) issues.push({code:'DSH_POOL_ROLE_ROUTE_UNAVAILABLE',severity:'error',
        field:`roleOverrides.${role}`,route,message:`${role} 引用了已删除或未启用的路线 ${route}。`})
    }
    for (const route of roles.workers ?? []) {
      if (!routeKeys.has(route)) issues.push({code:'DSH_POOL_ROLE_ROUTE_UNAVAILABLE',severity:'error',
        field:'roleOverrides.workers',route,message:`执行模型池引用了已删除或未启用的路线 ${route}。`})
    }
    if (!pool.allowSharedJudge && roles.judge && roles.workers?.includes(roles.judge)) {
      issues.push({code:'DSH_POOL_SHARED_JUDGE_FORBIDDEN',severity:'error',field:'roleOverrides',route:roles.judge,
        message:'评审模型与执行模型默认必须分离；仅开发测试可启用共用职责。'})
    }
  }
  return issues
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
  failureMessage: string | null
  issues: SettingsIssue[]
  hasProvider: boolean
  overriddenProvider: boolean
  overriddenDshPool: boolean
  overriddenLimits: boolean
  overriddenRouter: boolean
  router: RouterConnectionView | undefined
  provider: ProviderConfigView | undefined
  dshModelPool: DshModelPoolView | undefined
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
  editV4Classifier(enabled: boolean, modelId?: string): void
  upsertV4Row(collection: V4CollectionKey, value: Record<string, unknown>, previousId?: string): void
  removeV4Row(collection: V4CollectionKey, id: string): void
  editLimit(key: LimitKey, checked: boolean): void
  editProviderJson(text: string): void
  editDshModelPool(value: DshModelPoolView): void
  editRouter(value: RouterConnectionView | undefined): void
  resetField(field: CardField): void
  save(): void
  discard(): void
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function assertCredentialReferences(provider: ProviderConfigView, validateReference = true): void {
  for (const row of Array.isArray(provider.providers) ? provider.providers : []) {
    if (!isRecord(row)) continue
    if (['apiKey', 'api_key', 'token', 'secret', 'credential'].some(key => Object.hasOwn(row, key))) {
      throw new Error('provider credentials must be saved as credentialEnv references')
    }
    if (validateReference && row.credentialEnv !== undefined
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

/** DSH 远程设置协议只接受 JsonValue；表单清空字段时产生的 undefined 必须在写入前移除。 */
function jsonValue<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

function sanitizeHostErrorDetail(value: unknown): string {
  return (value instanceof Error ? value.message : String(value))
    .replace(/\b(Bearer)\s+[^\s,;]+/gi, '$1 [REDACTED]')
    .replace(/(["']?(?:api[_-]?key|token|secret|password|credential)["']?\s*[:=]\s*)["']?[^\s,;}"']+["']?/gi,
      '$1[REDACTED]')
    .replace(/(https?:\/\/)[^\s/@:]+:[^\s/@]+@/gi, '$1[REDACTED]@')
    .slice(0, 500)
}

export class RefractCardController {
  private readonly scope: CardScope
  private readonly publicProfiles: readonly PublicModelProfileSummary[]
  private readonly listeners = new Set<() => void>()
  private readonly staged = new Map<CardField, StagedEdit>()
  private providerJson = ''
  private jsonEdited = false
  private modelText: Partial<Record<ModeKey, string>> = {}
  private providerJsonError: string | null = null
  private saving = false
  private failed = false
  private failureMessage: string | null = null
  private saveIssue: SettingsIssue | null = null
  private cached: RefractCardProjection | undefined
  private readonly offScope: () => void

  constructor(scope: CardScope, publicProfiles: readonly PublicModelProfileSummary[] = []) {
    this.scope = scope
    this.publicProfiles = publicProfiles
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
      editV4Classifier: (enabled, modelId) => this.editV4Classifier(enabled, modelId),
      upsertV4Row: (collection, value, previousId) => this.upsertV4Row(collection, value, previousId),
      removeV4Row: (collection, id) => this.removeV4Row(collection, id),
      editLimit: (key, checked) => this.editLimit(key, checked),
      editProviderJson: text => this.editProviderJson(text),
      editDshModelPool: value => this.editDshModelPool(value),
      editRouter: value => this.editRouter(value),
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

  editV4Classifier(enabled: boolean, modelId?: string): void {
    const provider = this.v4Provider()
    const classifier: Record<string, unknown> = {
      ...(isRecord(provider.security?.classifier) ? provider.security.classifier : {}), enabled,
    }
    if (modelId === undefined || modelId === '') delete classifier.modelId
    else classifier.modelId = modelId
    this.stageProvider({ ...provider, security: { ...provider.security, classifier } })
  }

  upsertV4Row(collection: V4CollectionKey, value: Record<string, unknown>, previousId?: string): void {
    const provider = this.v4Provider()
    if (typeof value.id !== 'string') throw new Error(`${collection} rows require an id`)
    if (collection === 'providers') assertCredentialReferences({ providers: [value] }, false)
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
    this.beginEdit()
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

  editDshModelPool(value: DshModelPoolView): void {
    this.beginEdit()
    this.staged.set('dshModelPool', {kind:'set',value:structuredClone(value)})
    this.publish()
  }

  editRouter(value: RouterConnectionView | undefined): void {
    this.beginEdit()
    if (value === undefined) {
      if (this.overridden('router')) this.staged.set('router',{kind:'clear'})
      else this.staged.delete('router')
    } else this.staged.set('router',{kind:'set',value:structuredClone(value)})
    this.publish()
  }

  resetField(field: CardField): void {
    if (!this.overridden(field)) return
    this.beginEdit()
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
    this.failureMessage = null
    this.saveIssue = null
    this.syncProviderJson()
    this.publish()
  }

  /** 写出全部 staged 编辑，然后按宿主接受的段落核对是否落盘。 */
  async save(): Promise<void> {
    if (this.saving) return
    if (this.providerJsonError !== null) {
      this.failed = true
      this.failureMessage = this.providerJsonError
      this.publish()
      return
    }
    const blocking = buildDshModelPoolIssues(this.currentDshPool(), this.publicProfiles)
      .filter(issue => issue.severity === 'error')
    if (blocking.length) {
      this.failed = true
      this.failureMessage = '保存前检查未通过，请修正下方标记的问题。'
      this.saveIssue = null
      this.publish()
      return
    }
    for (const [field, edit] of this.staged) {
      if (edit.kind === 'set') this.staged.set(field, {kind:'set', value:jsonValue(edit.value)})
    }
    const snap = this.snapshot()
    if (snap.status !== 'ready' || !snap.writable) return
    const writes: Array<{ field: CardField; run: () => Promise<void> }> = []
    const router = this.staged.get('router')
    if (router?.kind === 'clear') {
      if (this.overridden('router')) writes.push({field:'router',run:()=>this.scope.unset('router')})
    } else if (router?.kind === 'set' && stableStringify(router.value)!==stableStringify(snap.value?.router)) {
      writes.push({field:'router',run:()=>this.scope.set('router',router.value)})
    }
    const provider = this.staged.get('providerConfig')
    if (provider?.kind === 'clear') {
      if (this.overridden('providerConfig')) writes.push({ field: 'providerConfig', run: () => this.scope.unset('providerConfig') })
    } else if (provider?.kind === 'set' && stableStringify(provider.value) !== stableStringify(snap.value?.providerConfig)) {
      writes.push({ field: 'providerConfig', run: () => this.scope.set('providerConfig', provider.value) })
    }
    const pool = this.staged.get('dshModelPool')
    if (pool?.kind === 'clear') {
      if (this.overridden('dshModelPool')) writes.push({field:'dshModelPool',run:()=>this.scope.unset('dshModelPool')})
    } else if (pool?.kind === 'set' && stableStringify(pool.value)!==stableStringify(snap.value?.dshModelPool)) {
      writes.push({field:'dshModelPool',run:()=>this.scope.set('dshModelPool',pool.value)})
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
    this.failureMessage = null
    this.saveIssue = null
    this.publish()
    for (const write of writes) await write.run().catch(error => {
      if (this.failureMessage === null) {
        const detail = sanitizeHostErrorDetail(error)
        this.failureMessage = `宿主拒绝保存 ${write.field}：${detail}`
        this.saveIssue = {code:'SETTINGS_HOST_REJECTED',severity:'error',field:write.field,
          message:this.failureMessage}
      }
    })
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
    if (!landed && this.failureMessage === null) {
      this.failureMessage = '保存结果未确认，修改仍保留在页面中；请检查宿主状态后重试。'
      this.saveIssue = {code:'SETTINGS_READBACK_UNCONFIRMED',severity:'error',field:'dshModelPool',
        message:this.failureMessage}
    }
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

  private currentRouter(): RouterConnectionView | undefined {
    const staged=this.staged.get('router')
    if(staged?.kind==='set')return staged.value as RouterConnectionView
    if(staged?.kind==='clear')return this.baseSection()?.router
    return this.snapshot().value?.router
  }

  private currentDshPool(): DshModelPoolView | undefined {
    const staged=this.staged.get('dshModelPool')
    if(staged?.kind==='set')return staged.value as DshModelPoolView
    if(staged?.kind==='clear')return this.baseSection()?.dshModelPool
    return this.snapshot().value?.dshModelPool
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
    this.beginEdit()
    this.staged.set('providerConfig', { kind: 'set', value })
    this.providerJson = JSON.stringify(value, null, 2)
    try {
      assertCredentialReferences(value)
      this.providerJsonError = null
    } catch (error) {
      this.providerJsonError = error instanceof Error ? error.message : String(error)
    }
    this.publish()
  }

  private stageLimits(value: LimitsView): void {
    this.beginEdit()
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

  private beginEdit(): void {
    this.failed = false
    this.failureMessage = null
    this.saveIssue = null
  }

  private project(): RefractCardProjection {
    const snap = this.snapshot()
    const providerStage = this.staged.get('providerConfig')
    const limitsStage = this.staged.get('limits')
    const issues = buildDshModelPoolIssues(this.currentDshPool(), this.publicProfiles)
    if (this.saveIssue) issues.push(this.saveIssue)
    return {
      status: snap.status,
      writable: snap.writable,
      dirty: this.staged.size > 0 || this.jsonEdited,
      saving: this.saving,
      failed: this.failed,
      failureMessage: this.failureMessage,
      issues,
      hasProvider: this.currentProvider() !== undefined || this.currentDshPool() !== undefined,
      overriddenProvider: this.overridden('providerConfig'),
      overriddenDshPool:this.overridden('dshModelPool'),
      overriddenLimits: this.overridden('limits'),
      overriddenRouter:this.overridden('router'),
      router:this.currentRouter(),
      provider: this.currentProvider(),
      dshModelPool:this.currentDshPool(),
      providerCleared: providerStage?.kind === 'clear',
      providerJson: this.providerJson,
      providerJsonError: this.providerJsonError,
      limits: this.currentLimits(),
      automaticRouting: this.currentDshPool()!==undefined||this.currentProvider()?.schemaVersion === 'refractagent-providers-v4',
      strategyModelText: { ...this.modelText },
      limitsCleared: limitsStage?.kind === 'clear',
    }
  }

  private publish(): void {
    this.cached = undefined
    for (const listener of [...this.listeners]) listener()
  }
}
