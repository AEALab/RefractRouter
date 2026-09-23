/** RefractAgent provider/model 配置契约与校验。
 * 被 configure() 与设置命名空间集成共用；仅宿主侧使用（依赖 Buffer）。
 */
export interface StrategyConfiguration {
  maxAfpCoefficient?: number
  reasoningEffort?: string
  models?: string[]
}

export interface ProviderConfiguration {
  schemaVersion: 'refractagent-providers-v1' | 'refractagent-providers-v2' | 'refractagent-providers-v3' | 'refractagent-providers-v4'
  billingUnit: string
  allowSharedJudge?: boolean
  qualityMin?: number
  objective?: { qualityMin: number; primary: 'cost'; secondary: 'latency'; dagMode: 'auto' | 'never' | 'force' }
  plannerThinking?: 'inherit' | 'enabled' | 'disabled'
  defaultReasoningEffort?: string
  strategies?: Partial<Record<'economy' | 'balanced' | 'quality', StrategyConfiguration>>
  privacy?: Record<string, unknown>
  security?: Record<string, unknown>
  trustPolicies?: Array<{ id: string; residency: string; auditLogging: boolean; allowsSensitiveData: boolean;
    expiresOn?: string; acknowledgeExternalTransmission?: boolean }>
  providers: Array<{ id: string; type: 'openai-compatible' | 'openai-responses' | 'ark-agent-plan' | 'dsh';
    baseUrl?: string; credentialEnv?: string; dshProvider?: string; maxTokensParameter?: string;
    deployment?: 'cloud' | 'external-cloud' | 'trusted-cloud' | 'local' | 'simulated-local'; trustPolicy?: string }>
  models: Array<{ id: string; provider: string; model: string; role?: 'candidate' | 'judge';
    roles?: Array<'planner' | 'worker' | 'judge' | 'classifier'>;
    contextWindow: number; maxOutputTokens?: number; pricing: Record<string, unknown>;
    reasoningEffort?: string; routing?: Record<string, unknown>; requestOptions?: Record<string, unknown>; jsonMode?: string;
    deployment?: 'cloud' | 'external-cloud' | 'trusted-cloud' | 'local' | 'simulated-local' }>
}

export interface LimitsConfiguration {
  relaxBudget?: boolean
  relaxContext?: boolean
  unlimitedTime?: boolean
}

export interface LiveExecutionConfiguration {
  schemaVersion: 'refractagent-live-execution-v1'
  enabled: boolean
  maxProductionCost?: number
  maxEvaluationCost?: number
  complexityPolicy: 'auto' | 'direct' | 'dag'
  reviewPolicy: 'adaptive' | 'always'
  maxConcurrency?: number
  providerConcurrency?: Record<string, number>
  providerMinIntervalMs?: Record<string, number>
  maxOutputTokens?: number | 'unlimited'
  maxTotalOutputTokens?: number
}

export type DshDeployment = 'local' | 'external-cloud' | 'trusted-cloud' | 'simulated-local'
export interface DshModelPoolRoute {
  provider: string
  model: string
  enabled?: boolean
  deployment: DshDeployment
  trustPolicy?: string
  overrides?: { inputPer1k?: number; cachedInputPer1k?: number; outputPer1k?: number;
    note?: string; quality?: number; latencyMs?: number }
}
export interface DshModelPool {
  schemaVersion: 'refractagent-dsh-model-pool-v1' | 'refractagent-dsh-model-pool-v2'
  billingUnit?: string
  allowSharedJudge?: boolean
  routes: DshModelPoolRoute[]
  roleOverrides?: { planner?: string; judge?: string; classifier?: string; workers?: string[] }
  objective?: Record<string, unknown>
  security?: Record<string, unknown>
  trustPolicies?: Array<Record<string, unknown>>
}

export interface RouterConnection {
  url: string
  credential?: string
  project?: string
}

/** DSH 设置命名空间承载的用户可调子集。 */
export interface SettingsSection {
  router?: RouterConnection
  providerConfig?: ProviderConfiguration
  dshModelPool?: DshModelPool
  limits?: LimitsConfiguration
  liveExecution?: LiveExecutionConfiguration
}

export function validateLiveExecution(value: unknown): asserts value is LiveExecutionConfiguration {
  if (!isRecordValue(value) || value.schemaVersion !== 'refractagent-live-execution-v1'
    || typeof value.enabled !== 'boolean'
    || !['auto','direct','dag'].includes(String(value.complexityPolicy))
    || !['adaptive','always'].includes(String(value.reviewPolicy))
    || Object.keys(value).some(key => !['schemaVersion','enabled','maxProductionCost','maxEvaluationCost',
      'complexityPolicy','reviewPolicy','maxConcurrency','providerConcurrency','providerMinIntervalMs',
      'maxOutputTokens','maxTotalOutputTokens'].includes(key))) {
    throw new Error('invalid liveExecution configuration')
  }
  for (const key of ['maxProductionCost','maxEvaluationCost'] as const) {
    const entry = value[key]
    if (entry !== undefined && (typeof entry !== 'number' || !Number.isFinite(entry) || entry <= 0)) {
      throw new Error(`liveExecution.${key} must be a positive CNY hard limit`)
    }
  }
  const maxConcurrency = value.maxConcurrency
  if (maxConcurrency !== undefined && (typeof maxConcurrency !== 'number' || !Number.isInteger(maxConcurrency)
    || maxConcurrency < 1 || maxConcurrency > 8)) {
    throw new Error('liveExecution.maxConcurrency must be an integer in 1..8')
  }
  const maxOutputTokens = value.maxOutputTokens
  if (maxOutputTokens !== undefined && maxOutputTokens !== 'unlimited'
    && (typeof maxOutputTokens !== 'number' || !Number.isInteger(maxOutputTokens)
      || maxOutputTokens < 1000 || maxOutputTokens > 128000)) {
    throw new Error('liveExecution.maxOutputTokens must be unlimited or an integer in 1000..128000')
  }
  const maxTotalOutputTokens = value.maxTotalOutputTokens
  if (maxTotalOutputTokens !== undefined && (typeof maxTotalOutputTokens !== 'number'
    || !Number.isInteger(maxTotalOutputTokens) || maxTotalOutputTokens < 1000 || maxTotalOutputTokens > 1_000_000)) {
    throw new Error('liveExecution.maxTotalOutputTokens must be an integer in 1000..1000000')
  }
  for (const [field, minimum, maximum] of [['providerConcurrency', 1, 8],
      ['providerMinIntervalMs', 0, 60000]] as const) {
    const rows = value[field]
    if (rows !== undefined && (!isRecordValue(rows) || Object.entries(rows).some(([provider, entry]) => !provider
      || typeof entry !== 'number' || !Number.isInteger(entry) || entry < minimum || entry > maximum))) {
      throw new Error(`invalid liveExecution.${field}`)
    }
  }
  if (value.enabled && (value.maxProductionCost === undefined || value.maxEvaluationCost === undefined)) {
    throw new Error('enabled liveExecution requires explicit production and evaluation hard limits')
  }
}

export function validateRouterConnection(value: unknown): asserts value is RouterConnection {
  if (!isRecordValue(value) || typeof value.url !== 'string'
    || Object.keys(value).some(key => !['url','credential','project'].includes(key))) throw new Error('invalid Router connection')
  let url: URL
  try { url = new URL(value.url) } catch { throw new Error('invalid Router URL') }
  if (!['http:','https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new Error('Router URL must be an HTTP(S) service root without credentials, query or fragment')
  }
  if (url.protocol !== 'https:' && !['localhost','127.0.0.1','::1'].includes(url.hostname)) {
    throw new Error('non-loopback Router URL requires HTTPS')
  }
  if (value.credential !== undefined && (typeof value.credential !== 'string'
    || !/^[A-Za-z_][A-Za-z0-9_.:-]*$/.test(value.credential))) throw new Error('invalid Router credential reference')
  if (value.project !== undefined && (typeof value.project !== 'string'
    || !/^[A-Za-z0-9._-]{1,128}$/.test(value.project))) throw new Error('invalid Router project')
}

export function validateDshModelPool(value: unknown): asserts value is DshModelPool {
  if (!isRecordValue(value) || !['refractagent-dsh-model-pool-v1','refractagent-dsh-model-pool-v2'].includes(String(value.schemaVersion))
    || !Array.isArray(value.routes) || value.routes.length > 128
    || Object.keys(value).some(key => !['schemaVersion','billingUnit','allowSharedJudge','routes','roleOverrides','objective','security','trustPolicies'].includes(key))) {
    throw new Error('invalid dshModelPool')
  }
  if (value.allowSharedJudge !== undefined && typeof value.allowSharedJudge !== 'boolean') {
    throw new Error('invalid dshModelPool allowSharedJudge')
  }
  const identities = new Set<string>()
  for (const route of value.routes) {
    if (!isRecordValue(route) || typeof route.provider !== 'string' || !route.provider
      || typeof route.model !== 'string' || !route.model || route.provider === 'refractagent'
      || !['local','external-cloud','trusted-cloud','simulated-local'].includes(String(route.deployment))
      || (route.enabled !== undefined && typeof route.enabled !== 'boolean')
      || Object.keys(route).some(key => !['provider','model','enabled','deployment','trustPolicy','overrides'].includes(key))) {
      throw new Error('invalid dshModelPool route')
    }
    const identity = `${route.provider}\u0000${route.model}`
    if (identities.has(identity)) throw new Error('dshModelPool route identities must be unique')
    identities.add(identity)
    const allowedOverrides = value.schemaVersion === 'refractagent-dsh-model-pool-v2'
      ? ['inputPer1k','cachedInputPer1k','outputPer1k','note']
      : ['inputPer1k','cachedInputPer1k','outputPer1k','quality','latencyMs','note']
    if (route.overrides !== undefined && (!isRecordValue(route.overrides)
      || Object.keys(route.overrides).some(key => !allowedOverrides.includes(key))
      || Object.entries(route.overrides).some(([key, entry]) => key === 'note'
        ? typeof entry !== 'string' : typeof entry !== 'number' || !Number.isFinite(entry) || entry < 0))) {
      throw new Error('invalid dshModelPool route overrides')
    }
  }
  if (value.roleOverrides !== undefined) {
    if (!isRecordValue(value.roleOverrides)
      || Object.keys(value.roleOverrides).some(key => !['planner','judge','classifier','workers'].includes(key))) {
      throw new Error('invalid dshModelPool roleOverrides')
    }
    const roles = value.roleOverrides
    if (['planner','judge','classifier'].some(key => roles[key] !== undefined
      && (typeof roles[key] !== 'string' || !roles[key]))
      || (roles.workers !== undefined && (!Array.isArray(roles.workers) || roles.workers.length === 0
        || roles.workers.some(entry => typeof entry !== 'string' || !entry)))) {
      throw new Error('invalid dshModelPool roleOverrides')
    }
  }
  if (value.billingUnit !== undefined && (typeof value.billingUnit !== 'string' || !value.billingUnit.trim())) {
    throw new Error('invalid dshModelPool billingUnit')
  }
  const routeKeys = new Set(value.routes.filter(route => route.enabled !== false)
    .map(route => `${route.provider}/${route.model}`))
  const policyRows = (Array.isArray(value.trustPolicies) ? value.trustPolicies : []).filter(isRecordValue)
  const policyIds = new Set(policyRows.map(policy => policy.id)
    .filter((id): id is string => typeof id === 'string' && !!id))
  const policies = new Map(policyRows.map(policy => [policy.id, policy] as const)
    .filter((row): row is [string, Record<string, unknown>] => typeof row[0] === 'string' && !!row[0]))
  const liveData = !isRecordValue(value.security) || (value.security.dataMode ?? 'live') === 'live'
  for (const route of value.routes) {
    if ((route.deployment === 'trusted-cloud' || (route.deployment === 'simulated-local' && liveData))
      && (typeof route.trustPolicy !== 'string' || !policyIds.has(route.trustPolicy))) {
      throw new Error(`${route.deployment} requires a configured trustPolicy`)
    }
    if (!['trusted-cloud','simulated-local'].includes(route.deployment) && route.trustPolicy !== undefined) {
      throw new Error('trustPolicy requires trusted-cloud or simulated-local')
    }
    const policy = typeof route.trustPolicy === 'string' ? policies.get(route.trustPolicy) : undefined
    if (policy && (typeof policy.residency !== 'string' || !policy.residency.trim()
      || policy.auditLogging !== true || policy.allowsSensitiveData !== true)) {
      throw new Error('trustPolicy must declare residency, audit logging and sensitive-data permission')
    }
    if (route.deployment === 'simulated-local' && liveData && policy
      && policy.acknowledgeExternalTransmission !== true) {
      throw new Error('live simulated-local requires acknowledgeExternalTransmission')
    }
  }
  const roles = value.roleOverrides as DshModelPool['roleOverrides']
  if (roles !== undefined) {
    for (const key of ['planner','judge','classifier'] as const) {
      if (roles[key] !== undefined && !routeKeys.has(roles[key])) {
        throw new Error(`dshModelPool roleOverrides.${key} references an unavailable route`)
      }
    }
    if (roles.workers?.some(entry => !routeKeys.has(entry))) {
      throw new Error('dshModelPool roleOverrides.workers references an unavailable route')
    }
  }
  if (Buffer.byteLength(JSON.stringify(value)) > 100000) throw new Error('dshModelPool is too large')
}

/** 显式迁移旧模型池；旧的质量和时延声明不会成为 v2 的运行证据。 */
export function migrateDshModelPool(value: DshModelPool): DshModelPool {
  if (value.schemaVersion === 'refractagent-dsh-model-pool-v2') return structuredClone(value)
  return {
    ...structuredClone(value),
    schemaVersion: 'refractagent-dsh-model-pool-v2',
    routes: value.routes.map(route => {
      if (route.overrides === undefined) return structuredClone(route)
      const { quality: _quality, latencyMs: _latency, ...overrides } = route.overrides
      return { ...route, ...(overrides === undefined ? {} : { overrides }) }
    }),
  }
}

export function isRecordValue(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

export function freezeConfiguration<T>(value: T): T {
  if (value !== null && typeof value === 'object') {
    Object.values(value).forEach(freezeConfiguration)
    Object.freeze(value)
  }
  return value
}

export function validateProviderConfiguration(value: unknown): asserts value is ProviderConfiguration {
  const config = value
  const schemas = ['refractagent-providers-v1','refractagent-providers-v2','refractagent-providers-v3','refractagent-providers-v4']
  if (!isRecordValue(config) || !schemas.includes(String(config.schemaVersion))
    || typeof config.billingUnit !== 'string' || !Array.isArray(config.providers) || !Array.isArray(config.models)
    || Object.keys(config).some(k => !['schemaVersion','billingUnit','allowSharedJudge','qualityMin','objective','defaultReasoningEffort','plannerThinking','strategies','providers','models','privacy','security','trustPolicies'].includes(k))) {
    throw new Error('invalid providerConfig; use refractagent config-example')
  }
  const v3 = config.schemaVersion === 'refractagent-providers-v3'
  const v4 = config.schemaVersion === 'refractagent-providers-v4'
  if ((v3 || v4) && config.privacy !== undefined) throw new Error('providerConfig v3/v4 uses security instead of privacy')
  if (!v3 && !v4 && (config.security !== undefined || config.trustPolicies !== undefined)) throw new Error('security requires providerConfig v3 or v4')
  if (v4) {
    if (config.qualityMin !== undefined || config.strategies !== undefined || !isRecordValue(config.objective)
      || typeof config.objective.qualityMin !== 'number' || !Number.isFinite(config.objective.qualityMin)
      || config.objective.qualityMin < 0 || config.objective.qualityMin > 100
      || config.objective.primary !== 'cost' || config.objective.secondary !== 'latency'
      || !['auto','never','force'].includes(String(config.objective.dagMode))) {
      throw new Error('providerConfig v4 requires a cost-first objective and no legacy strategies')
    }
    if (config.allowSharedJudge !== undefined && typeof config.allowSharedJudge !== 'boolean') {
      throw new Error('invalid allowSharedJudge')
    }
  } else if (config.objective !== undefined) throw new Error('objective requires providerConfig v4')
  else if (config.allowSharedJudge !== undefined) throw new Error('allowSharedJudge requires providerConfig v4')
  if (config.plannerThinking !== undefined && (typeof config.plannerThinking !== 'string' || !['inherit','enabled','disabled'].includes(config.plannerThinking))) {
    throw new Error('invalid plannerThinking')
  }
  if (config.defaultReasoningEffort !== undefined
    && (typeof config.defaultReasoningEffort !== 'string' || !config.defaultReasoningEffort.trim())) {
    throw new Error('invalid defaultReasoningEffort')
  }
  for (const p of config.providers) {
    if (!isRecordValue(p) || typeof p.id !== 'string' || !['openai-compatible','openai-responses','ark-agent-plan','dsh'].includes(String(p.type))
      || Object.keys(p).some(k=>!['id','type','baseUrl','credentialEnv','dshProvider','maxTokensParameter','deployment','trustPolicy'].includes(k))) {
      throw new Error('invalid provider configuration fields')
    }
    if ((v3 || v4) && p.deployment === undefined) throw new Error('providerConfig v3/v4 requires explicit deployment')
    if (p.credentialEnv !== undefined && (typeof p.credentialEnv !== 'string' || !/^[A-Z][A-Z0-9_]*$/.test(p.credentialEnv))) {
      throw new Error('provider credentialEnv must be a reference, never a secret value')
    }
    if (p.type === 'dsh' && (p.credentialEnv !== undefined || p.baseUrl !== undefined)) throw new Error('DSH providers use host credentials')
    if (p.type === 'dsh' && (p.dshProvider ?? p.id) === 'refractagent') throw new Error('recursive RefractAgent routing is forbidden')
  }
  if (v3 || v4) {
    if (config.security !== undefined && !isRecordValue(config.security)) throw new Error('invalid security configuration')
    if (config.trustPolicies !== undefined && !Array.isArray(config.trustPolicies)) throw new Error('invalid trustPolicies')
    const policyIds = new Set((config.trustPolicies ?? []).filter(isRecordValue).map(row => row.id))
    for (const p of config.providers) {
      if (p.deployment === 'trusted-cloud' && (typeof p.trustPolicy !== 'string' || !policyIds.has(p.trustPolicy))) {
        throw new Error('trusted-cloud requires a configured trustPolicy')
      }
      if (p.deployment === 'simulated-local' && v4 && isRecordValue(config.security)
        && (config.security.dataMode ?? 'live') === 'live'
        && (typeof p.trustPolicy !== 'string' || !policyIds.has(p.trustPolicy))) {
        throw new Error('live simulated-local requires a configured trustPolicy')
      }
      if (p.deployment !== 'trusted-cloud' && !(v4 && p.deployment === 'simulated-local') && p.trustPolicy !== undefined) {
        throw new Error('trustPolicy requires trusted-cloud or v4 simulated-local')
      }
    }
  }
  for (const m of config.models) {
    if (!isRecordValue(m) || typeof m.id !== 'string' || typeof m.provider !== 'string' || typeof m.model !== 'string'
      || !config.providers.some(p => isRecordValue(p) && p.id === m.provider)) throw new Error('invalid configured model reference')
    if (v4) {
      const roles = m.roles
      if (m.role !== undefined || !Array.isArray(roles) || roles.length === 0 || new Set(roles).size !== roles.length
        || roles.some(role => !['planner','worker','judge','classifier'].includes(String(role)))) {
        throw new Error('providerConfig v4 models require unique roles')
      }
    } else if (m.roles !== undefined) throw new Error('model roles require providerConfig v4')
  }
  if (v4) for (const role of ['planner','worker','judge']) {
    if (!config.models.some(model => model.roles?.includes(role as 'planner' | 'worker' | 'judge'))) {
      throw new Error(`providerConfig v4 requires a ${role} model`)
    }
  }
  if (config.strategies !== undefined) {
    const strategies = config.strategies
    if (!isRecordValue(strategies) || Object.keys(strategies).some(k => !['economy', 'balanced', 'quality'].includes(k))) {
      throw new Error('strategies may only configure economy, balanced and quality')
    }
    const modelIds = new Set(config.models.filter(m => isRecordValue(m) && typeof m.id === 'string').map(m => String(m.id)))
    for (const [name, entry] of Object.entries(strategies)) {
      if (!isRecordValue(entry) || Object.keys(entry).some(k => !['reasoningEffort', 'models', 'maxAfpCoefficient'].includes(k))) {
        throw new Error('invalid ' + name + ' strategy fields')
      }
      if (entry.maxAfpCoefficient !== undefined && (config.billingUnit !== 'AFP'
        || typeof entry.maxAfpCoefficient !== 'number' || !Number.isFinite(entry.maxAfpCoefficient) || entry.maxAfpCoefficient <= 0)) {
        throw new Error('maxAfpCoefficient must be positive and use AFP billingUnit')
      }
      if (entry.reasoningEffort !== undefined
        && (typeof entry.reasoningEffort !== 'string' || !entry.reasoningEffort.trim())) {
        throw new Error('invalid ' + name + ' reasoningEffort')
      }
      if (entry.models !== undefined) {
        if (!Array.isArray(entry.models) || entry.models.length === 0
          || entry.models.some(id => typeof id !== 'string' || !modelIds.has(id))) {
          throw new Error(name + ' models must reference configured model ids')
        }
      }
    }
  }
  if (Buffer.byteLength(JSON.stringify(config)) > 100000) throw new Error('providerConfig is too large')
}
