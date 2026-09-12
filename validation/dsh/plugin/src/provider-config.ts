/** RefractAgent provider/model 配置契约与校验。
 * 被 configure() 与设置命名空间集成共用；仅宿主侧使用（依赖 Buffer）。
 */
export interface StrategyConfiguration {
  reasoningEffort?: string
  models?: string[]
}

export interface ProviderConfiguration {
  schemaVersion: 'refractagent-providers-v1'
  billingUnit: string
  qualityMin?: number
  defaultReasoningEffort?: string
  strategies?: Partial<Record<'economy' | 'balanced' | 'quality', StrategyConfiguration>>
  providers: Array<{ id: string; type: 'openai-compatible' | 'openai-responses' | 'ark-agent-plan' | 'dsh';
    baseUrl?: string; credentialEnv?: string; dshProvider?: string; maxTokensParameter?: string }>
  models: Array<{ id: string; provider: string; model: string; role?: 'candidate' | 'judge';
    contextWindow: number; maxOutputTokens?: number; pricing: Record<string, unknown>;
    reasoningEffort?: string; routing?: Record<string, unknown>; requestOptions?: Record<string, unknown>; jsonMode?: string }>
}

export interface LimitsConfiguration {
  relaxBudget?: boolean
  relaxContext?: boolean
}

/** DSH 设置命名空间承载的用户可调子集。 */
export interface SettingsSection {
  providerConfig?: ProviderConfiguration
  limits?: LimitsConfiguration
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
  if (!isRecordValue(config) || config.schemaVersion !== 'refractagent-providers-v1'
    || typeof config.billingUnit !== 'string' || !Array.isArray(config.providers) || !Array.isArray(config.models)
    || Object.keys(config).some(k => !['schemaVersion','billingUnit','qualityMin','defaultReasoningEffort','strategies','providers','models'].includes(k))) {
    throw new Error('invalid providerConfig; use refractagent config-example')
  }
  if (config.defaultReasoningEffort !== undefined
    && (typeof config.defaultReasoningEffort !== 'string' || !config.defaultReasoningEffort.trim())) {
    throw new Error('invalid defaultReasoningEffort')
  }
  for (const p of config.providers) {
    if (!isRecordValue(p) || typeof p.id !== 'string' || !['openai-compatible','openai-responses','ark-agent-plan','dsh'].includes(String(p.type))
      || Object.keys(p).some(k=>!['id','type','baseUrl','credentialEnv','dshProvider','maxTokensParameter'].includes(k))) {
      throw new Error('invalid provider configuration fields')
    }
    if (p.credentialEnv !== undefined && (typeof p.credentialEnv !== 'string' || !/^[A-Z][A-Z0-9_]*$/.test(p.credentialEnv))) {
      throw new Error('provider credentialEnv must be a reference, never a secret value')
    }
    if (p.type === 'dsh' && (p.credentialEnv !== undefined || p.baseUrl !== undefined)) throw new Error('DSH providers use host credentials')
    if (p.type === 'dsh' && (p.dshProvider ?? p.id) === 'refractagent') throw new Error('recursive RefractAgent routing is forbidden')
  }
  for (const m of config.models) {
    if (!isRecordValue(m) || typeof m.id !== 'string' || typeof m.provider !== 'string' || typeof m.model !== 'string'
      || !config.providers.some(p => isRecordValue(p) && p.id === m.provider)) throw new Error('invalid configured model reference')
  }
  if (config.strategies !== undefined) {
    const strategies = config.strategies
    if (!isRecordValue(strategies) || Object.keys(strategies).some(k => !['economy', 'balanced', 'quality'].includes(k))) {
      throw new Error('strategies may only configure economy, balanced and quality')
    }
    const modelIds = new Set(config.models.filter(m => isRecordValue(m) && typeof m.id === 'string').map(m => String(m.id)))
    for (const [name, entry] of Object.entries(strategies)) {
      if (!isRecordValue(entry) || Object.keys(entry).some(k => !['reasoningEffort', 'models'].includes(k))) {
        throw new Error('invalid ' + name + ' strategy fields')
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
