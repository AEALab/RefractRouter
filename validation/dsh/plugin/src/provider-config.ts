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
  const schemas = ['refractagent-providers-v1','refractagent-providers-v2','refractagent-providers-v3','refractagent-providers-v4']
  if (!isRecordValue(config) || !schemas.includes(String(config.schemaVersion))
    || typeof config.billingUnit !== 'string' || !Array.isArray(config.providers) || !Array.isArray(config.models)
    || Object.keys(config).some(k => !['schemaVersion','billingUnit','qualityMin','objective','defaultReasoningEffort','plannerThinking','strategies','providers','models','privacy','security','trustPolicies'].includes(k))) {
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
  } else if (config.objective !== undefined) throw new Error('objective requires providerConfig v4')
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
