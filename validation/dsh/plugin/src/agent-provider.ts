import { decodeDag, decodeProgress, progressText, runSummary, type ProgressEvent } from './dag-progress.js'
/** Native DSH virtual models. Python owns presets, routing and all cost accounting. */
import { resolve } from 'node:path'
import { bindNativeTools, type NativeToolContext, type ToolSchema } from './native-tools.js'
import type { DshContext, LlmService, ModelRoute, ProcessHandle } from './contracts.js'
import { dshProviderIssues, pumpDshBridge } from './index.js'
import { decodeOutputConstraints, decodeFormatValidation, formatValidationSummary, type OutputConstraints } from './output-constraints.js'
import { freezeConfiguration, validateDshModelPool, validateProviderConfiguration, type DshModelPool,
  type LimitsConfiguration, type ProviderConfiguration } from './provider-config.js'
import { installRefractSettings, overlaySettings, type SettingsFiberContext } from './settings-integration.js'

export const name = 'refractagent'
export const inject = ['llm', 'subprocess', 'sandbox', 'sandboxPolicy', 'credentials', 'tools', 'agents']

const MAX_CONTEXT_BYTES = 120_000
const RELAXED_CONTEXT_BYTES = 1_000_000

const LEGACY_MODELS = [
  { id: 'economy', name: 'RefractAgent · 省成本' },
  { id: 'balanced', name: 'RefractAgent · 均衡' },
  { id: 'quality', name: 'RefractAgent · 质量优先' },
] as const
const AUTO_MODELS = [{ id: 'auto', name: 'RefractAgent · 自动路由' }] as const

function configuredModels(config: Readonly<Configuration>): readonly { id: string; name: string }[] {
  return config.dshModelPool !== undefined || config.providerConfig?.schemaVersion === 'refractagent-providers-v4' ? AUTO_MODELS : LEGACY_MODELS
}

/** DSH 会保留新会话上次选择的模型 ID；升级到 v4 后把旧三模式选择收敛到唯一自动入口。 */
function normalizeConfiguredModel(config: Readonly<Configuration>, model: string): string {
  return (config.dshModelPool !== undefined || config.providerConfig?.schemaVersion === 'refractagent-providers-v4')
    && LEGACY_MODELS.some(entry => entry.id === model) ? 'auto' : model
}

export interface Configuration {
  pythonExecutable: string
  runsDir: string
  executionMode: 'demo' | 'live'
  allowPaidRuns: boolean
  maxProductionCost: number
  maxEvaluationCost: number
  timeoutMs: number
  maxOutputTokens: number
  credentialEnv: string
  preset?: 'ark-agent-plan'
  providerConfig?: ProviderConfiguration
  dshModelPool?: DshModelPool
  limits?: LimitsConfiguration
  template: 'single' | 'compare' | 'auto'
  outputConstraints?: OutputConstraints
  plannerModelId?: string
  plannerTimeoutMs?: number
  plannerMaxOutputTokens?: number
  maxDynamicSplits?: number
  maxConcurrency?: number
  verifyDependencies?: boolean
}
interface ModelOptions {
  provider: string
  model: string
  messages: Array<{ role: string; source?: { kind: string; [key: string]: unknown };
    content: Array<{ type: string; text?: string; [key: string]: unknown }> }>
  system?: string
  tools?: ToolSchema[]
  maxTokens?: number
  temperature?: number
  stop?: string[]
  signal?: AbortSignal
  purpose?: string
}
interface ModelMetadata {
  provider: string; id: string; name: string
  inputModalities: readonly string[]
  description: string
  context?: { contextWindow: number }
  defaultMaxTokens?: number
}
export interface AgentAdapter {
  providerInfo(provider: string): { id: string; name: string }
  providerRetryPolicy(provider: string): { mode: 'normal'; maxRetries: number; retryableCodes: string[] }
  listModels(provider: string): Promise<ModelMetadata[]>
  resolveModel(provider: string, model: string): Promise<ModelMetadata>
  prepareCall(provider: string, model: string): Promise<{ model: ModelMetadata; stream(options: ModelOptions): AsyncIterable<Record<string, unknown>> }>
  stream(options: ModelOptions): AsyncIterable<Record<string, unknown>>
}
export type AgentContext = NativeToolContext & Pick<DshContext, 'subprocess' | 'sandbox' | 'sandboxPolicy' | 'credentials'> & {
  llm: Partial<LlmService> & { registerAdapter(providers: string[], adapter: AgentAdapter): unknown }
  inject?: (deps: readonly string[], callback: (sctx: SettingsFiberContext) => void) => unknown
}

function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}
function positive(value: unknown, key: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) throw new Error(`invalid ${key}`)
  return value
}

interface PublicFailure {
  kind: 'error' | 'aborted'
  code: string
  message: string
}

function publicFailure(error: unknown, aborted: boolean): PublicFailure {
  const detail = error instanceof Error ? error.message : String(error)
  if (aborted || /cancelled|canceled|aborted|timed out/i.test(detail)) return {
    kind: 'aborted', code: 'REFRACTAGENT_EXECUTION_ABORTED',
    message: 'RefractAgent 已停止：任务被取消或超时；请核对已保存的运行记录后再重试。',
  }
  if (/node-input-budget-exceeded|automatic-plan-input-capacity-exceeded/.test(detail)) return {
    kind: 'error', code: 'REFRACTAGENT_NODE_INPUT_CAPACITY',
    message: 'RefractAgent 未执行：当前任务所需输入超过节点容量。请缩短会话、新建会话或选择更大上下文模型。',
  }
  if (/conversation (?:context )?is too large|conversation context exceeds/.test(detail)) return {
    kind: 'error', code: 'REFRACTAGENT_CONTEXT_LIMIT',
    message: 'RefractAgent 未执行：当前会话超过应用上下文上限。请新建较短会话，或在高级设置中放开上下文限制。',
  }
  if (/input-or-output-capacity|contextWindow|context window|no assignment satisfies/.test(detail)) return {
    kind: 'error', code: 'REFRACTAGENT_MODEL_CONTEXT_LIMIT',
    message: 'RefractAgent 未执行：当前模型没有足够的输入或输出容量。请选择更大上下文模型。',
  }
  if (/provider|route|model.+(?:missing|unknown|unavailable)|no local candidate/i.test(detail)) return {
    kind: 'error', code: 'REFRACTAGENT_ROUTE_UNAVAILABLE',
    message: 'RefractAgent 未执行：配置的 Provider 或模型路线当前不可用，请检查 DSH 模型设置。',
  }
  return { kind: 'error', code: 'REFRACTAGENT_EXECUTION_FAILED',
    message: 'RefractAgent 未执行：运行失败。请查看运行记录中的诊断信息。' }
}

export function configure(raw: unknown = {}): Readonly<Configuration> {
  if (!object(raw)) throw new Error('RefractAgent configuration must be an object')
  const result = { pythonExecutable: 'python3', runsDir: '.refractagent/runs', executionMode: 'demo',
    allowPaidRuns: false, maxProductionCost: 40, maxEvaluationCost: 80,
    timeoutMs: 300000, maxOutputTokens: 2048, credentialEnv: 'CODEX_ARK_API_KEY', template: 'single',
    preset: undefined as unknown, providerConfig: undefined as unknown, dshModelPool: undefined as unknown, limits: undefined as unknown,
    outputConstraints: undefined as unknown, ...raw }
  const allowed = new Set(['pythonExecutable', 'runsDir', 'executionMode', 'allowPaidRuns', 'maxProductionCost',
    'maxEvaluationCost', 'timeoutMs', 'maxOutputTokens', 'credentialEnv', 'template', 'preset', 'providerConfig', 'dshModelPool', 'outputConstraints',
    'limits', 'plannerModelId', 'plannerTimeoutMs', 'plannerMaxOutputTokens', 'maxDynamicSplits', 'maxConcurrency', 'verifyDependencies'])
  if (Object.keys(raw).some(key => !allowed.has(key))) throw new Error('unknown RefractAgent configuration field')
  for (const key of ['pythonExecutable', 'runsDir', 'credentialEnv'] as const) {
    if (typeof result[key] !== 'string' || !result[key].trim()) throw new Error(`invalid ${key}`)
  }
  if (result.executionMode !== 'demo' && result.executionMode !== 'live') throw new Error('invalid executionMode')
  if (!['single', 'compare', 'auto'].includes(result.template)) throw new Error('invalid template')
  if (typeof result.allowPaidRuns !== 'boolean') throw new Error('allowPaidRuns must be boolean')
  for (const key of ['maxProductionCost', 'maxEvaluationCost', 'timeoutMs', 'maxOutputTokens'] as const) positive(result[key], key)
  if (!Number.isInteger(result.maxOutputTokens) || result.maxOutputTokens < 1000 || result.maxOutputTokens > 128000) {
    throw new Error('maxOutputTokens must be an integer in 1000..128000')
  }
  if (!Number.isInteger(result.timeoutMs) || result.timeoutMs > 7200000) throw new Error('invalid timeoutMs')
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(result.credentialEnv)) throw new Error('invalid credentialEnv')
  if (result.preset !== undefined && result.preset !== 'ark-agent-plan') throw new Error('unknown provider preset')
  if (result.limits !== undefined) {
    if (!object(result.limits) || Object.keys(result.limits).some(k => !['relaxBudget', 'relaxContext', 'unlimitedTime'].includes(k))
      || Object.values(result.limits).some(v => typeof v !== 'boolean')) {
      throw new Error('limits may only contain boolean relaxBudget, relaxContext and unlimitedTime')
    }
  }
  if (raw.outputConstraints !== undefined) result.outputConstraints = decodeOutputConstraints(raw.outputConstraints)
  for (const key of ['plannerTimeoutMs','plannerMaxOutputTokens','maxDynamicSplits','maxConcurrency']) {
    if (raw[key] !== undefined && (typeof raw[key] !== 'number' || !Number.isSafeInteger(raw[key]) || raw[key] < 0)) {
      throw new Error(`invalid ${key}`)
    }
  }
  if (raw.plannerModelId !== undefined && (typeof raw.plannerModelId !== 'string' || !raw.plannerModelId.trim())) throw new Error('invalid plannerModelId')
  if (raw.verifyDependencies !== undefined && typeof raw.verifyDependencies !== 'boolean') throw new Error('invalid verifyDependencies')
  if (result.providerConfig !== undefined) {
    if (result.preset !== undefined || result.dshModelPool !== undefined) throw new Error('providerConfig, dshModelPool and preset are mutually exclusive')
    validateProviderConfiguration(result.providerConfig)
  }
  if (result.dshModelPool !== undefined) {
    if (result.preset !== undefined) throw new Error('providerConfig, dshModelPool and preset are mutually exclusive')
    validateDshModelPool(result.dshModelPool)
  }
  return freezeConfiguration(JSON.parse(JSON.stringify(result)) as Configuration)
}
export const Config = { '~standard': {
  version: 1 as const, vendor: 'refractagent',
  validate(value: unknown) {
    try { return { value: configure(value) } }
    catch (error) { return { issues: [{ message: error instanceof Error ? error.message : 'invalid configuration' }] } }
  },
} }

function conversation(options: ModelOptions, contextLimitBytes: number): { task: string; context: string } {
  if (!Array.isArray(options.messages) || !options.messages.length) throw new Error('RefractAgent requires conversation messages')
  // DSH also encodes injected instructions and skill catalogs as user messages.
  // Producer attribution, rather than text heuristics, identifies the user's task.
  const latest = [...options.messages].reverse().find(m => m.role === 'user'
    && (m.source === undefined || m.source.kind === 'user')
    && m.content.some(b => b.type === 'text' && b.text?.trim()))
  if (!latest) throw new Error('RefractAgent requires a text user task')
  const task = latest.content.filter(b => b.type === 'text').map(b => b.text ?? '').join('\n')
  const context = JSON.stringify({ system: options.system ?? '', messages: options.messages })
  if (Buffer.byteLength(context) > contextLimitBytes) throw new Error('RefractAgent conversation is too large; start a shorter text task')
  return { task, context }
}

async function dshCatalogSnapshot(ctx: AgentContext, pool: DshModelPool): Promise<Record<string, unknown>> {
  if (!ctx.llm.listProviders || !ctx.llm.listModels || !ctx.llm.resolveModelInfo) {
    throw new Error('DSH model catalog requires listProviders, listModels and resolveModelInfo')
  }
  const groups: Array<Record<string, unknown>> = []
  const failures: Array<{provider:string;model?:string;message:string}> = []
  for (const provider of ctx.llm.listProviders().filter(entry=>entry.id!=='refractagent')) {
    try {
      const models=await ctx.llm.listModels(provider.id)
      for (const model of models) {
        try {
          const raw=await ctx.llm.resolveModelInfo(provider.id,model.id)
          if (!object(raw)) throw new Error('invalid resolved model metadata')
          const context=object(raw.context)?raw.context:{}
          const reasoning=object(raw.reasoning)&&Array.isArray(raw.reasoning.efforts)
            ? raw.reasoning.efforts.filter(object).map(row=>String(row.id)) : []
          groups.push({provider:provider.id,model:model.id,name:model.name??model.id,
            contextWindow:context.contextWindow,maxOutputTokens:raw.defaultMaxTokens,
            reasoningEfforts:reasoning})
        } catch(error) {
          failures.push({provider:provider.id,model:model.id,message:error instanceof Error?error.message:String(error)})
        }
      }
    } catch(error) {
      failures.push({provider:provider.id,message:error instanceof Error?error.message:String(error)})
    }
  }
  const available=new Set(groups.map(row=>`${String(row.provider)}\u0000${String(row.model)}`))
  for (const route of pool.routes.filter(row=>row.enabled!==false)) {
    if (!available.has(`${route.provider}\u0000${route.model}`)) {
      throw new Error(`DSH route unavailable: ${route.provider}/${route.model}`)
    }
    const row=groups.find(entry=>entry.provider===route.provider&&entry.model===route.model)!
    if (!Number.isSafeInteger(row.contextWindow)||Number(row.contextWindow)<=0
      ||!Number.isSafeInteger(row.maxOutputTokens)||Number(row.maxOutputTokens)<=0) {
      throw new Error(`DSH model capacity unavailable: ${route.provider}/${route.model}`)
    }
  }
  return {schemaVersion:'refractagent-dsh-catalog-v1',routes:groups,failures}
}

async function invoke(ctx: AgentContext, config: Readonly<Configuration>, options: ModelOptions, onProgress?: (event: ProgressEvent) => void): Promise<Record<string, unknown>> {
  if (options.signal?.aborted) throw new Error('RefractAgent task cancelled before dispatch')
  const automaticRouting = config.dshModelPool !== undefined || config.providerConfig?.schemaVersion === 'refractagent-providers-v4'
  const live = config.executionMode === 'live'
  if (automaticRouting && live) throw new Error('RefractAgent v4 实时自动路由尚未启用；请先使用模拟模式验证配置')
  if (live && !config.allowPaidRuns) throw new Error('RefractAgent paid execution is disabled; enable it with scoped production/evaluation budgets')
  if (options.stop?.length) throw new Error('RefractAgent task models do not support stop sequences')
  if (live && !config.providerConfig && !config.preset) throw new Error('configure providerConfig or explicitly choose preset: ark-agent-plan')
  const nativeTools = live && !options.purpose ? bindNativeTools(ctx, options.tools ?? []) : undefined
  const catalogSnapshot=config.dshModelPool?await dshCatalogSnapshot(ctx,config.dshModelPool):undefined
  const payload = { ...conversation(options, config.limits?.relaxContext ? RELAXED_CONTEXT_BYTES : MAX_CONTEXT_BYTES),
    strategy: options.model, template: automaticRouting ? 'auto' : config.template,
    ...(nativeTools ? { hostTools: nativeTools.schemas } : {}),
    ...Object.fromEntries(['plannerModelId','plannerTimeoutMs','plannerMaxOutputTokens','maxDynamicSplits','maxConcurrency','verifyDependencies']
      .filter(key => config[key as keyof Configuration] !== undefined).map(key => [key, config[key as keyof Configuration]])),
    ...(config.outputConstraints ? { outputConstraints: config.outputConstraints } : {}),
    temperature: options.temperature ?? 0, ...(config.limits ? { limits: config.limits } : {}),
    ...(config.providerConfig ? { providerConfig: config.providerConfig } : {}),
    ...(config.dshModelPool ? {dshModelPool:config.dshModelPool,dshCatalogSnapshot:catalogSnapshot} : {}) }
  const routes: ModelRoute[] = []
  for (const model of config.providerConfig?.models ?? []) {
    const provider = config.providerConfig!.providers.find(p=>p.id===model.provider)!
    if (provider.type === 'dsh') routes.push({provider: provider.dshProvider ?? provider.id, model: model.model})
  }
  const useBridge = live && (routes.length > 0 || !!nativeTools)
  const progressEnabled = automaticRouting || config.template === 'auto'
  const piped = useBridge || progressEnabled
  let host: { llm: LlmService } | undefined
  if (useBridge) {
    if (!ctx.llm.stream || !ctx.llm.listProviders || !ctx.llm.providerRetryPolicy || !ctx.llm.resolveModelInfo) {
      throw new Error('DSH provider routing requires the native LLM service')
    }
    host = {llm: ctx.llm as LlmService}
    const issues = await dshProviderIssues(host, routes)
    if (issues.length) throw new Error(issues.join('; '))
  }
  const policy = ctx.sandboxPolicy.resolve({})
  const runsDir = resolve(policy.workspaceRoot, config.runsDir)
  const env: Record<string, string> = {}
  for (const key of ['PATH', 'HOME', 'LANG', 'LC_ALL', 'TMPDIR', 'SYSTEMROOT']) {
    const value = process.env[key]
    if (value) env[key] = value
  }
  env.PYTHONUNBUFFERED = '1'
  const secrets: string[] = []
  if (live) {
    const references = config.preset ? [config.credentialEnv] :
      (config.providerConfig?.providers.filter(p=>p.type!=='dsh').map(p=>p.credentialEnv).filter((r): r is string=>!!r) ?? [])
    const credentials: Record<string,string> = {}
    for (const reference of new Set(references)) {
      const credential = await ctx.credentials.resolve(reference)
      if (!credential?.value) throw new Error(`Missing RefractAgent credential: ${reference}`)
      secrets.push(credential.value)
      credentials[reference] = credential.value
    }
    if (config.preset) env.CODEX_ARK_API_KEY = credentials[config.credentialEnv]!
    else if (references.length) env.REFRACTROUTER_PROVIDER_CREDENTIALS = JSON.stringify(credentials)
  }
  if (useBridge) env.REFRACTROUTER_DSH_BRIDGE = 'stdio'
  const failed = new AbortController()
  const signal = AbortSignal.any([failed.signal, ...(options.signal ? [options.signal] : []), ...(config.template === 'auto' || config.limits?.unlimitedTime ? [] : [AbortSignal.timeout(config.timeoutMs + 5000)])])
  let python: string
  try { python = await ctx.subprocess.resolveExecutable(config.pythonExecutable, env, signal) }
  catch { throw new Error('RefractAgent Python not found; install the core and generate a dsh-config overlay') }
  const outputCap = Math.min(config.maxOutputTokens, options.maxTokens ?? config.maxOutputTokens)
  if (!Number.isInteger(outputCap) || outputCap < 1000) throw new Error('RefractAgent requires maxTokens >= 1000')
  const argv = [python, '-m', 'refractrouter.agent_cli', 'run', useBridge ? '--host-stdio' : '--request-stdin', '--mode', config.executionMode,
    '--runs-dir', runsDir, '--production-budget', String(config.maxProductionCost),
    '--evaluation-budget', String(config.maxEvaluationCost), '--timeout-ms', String(config.timeoutMs),
    '--max-output-tokens', String(outputCap), ...(live ? ['--execute-paid-run'] : []), ...(progressEnabled ? ['--progress-stdio'] : []),
    ...(config.preset ? ['--preset', config.preset] : [])]
  const confined = ctx.sandbox.confine(argv, policy)
  let handle: ProcessHandle | undefined
  try {
    handle = ctx.subprocess.spawn({ argv: confined.argv, cwd: policy.workspaceRoot, env,
      stdio: { stdin: 'pipe', stdout: piped ? 'pipe' : { maxBytes: 2097152 }, stderr: { maxBytes: 16384 } },
      signal, graceMs: 2000 })
    if (!handle.stdin) throw new Error('RefractAgent process has no input channel')
    await new Promise<void>((done, reject) => {
      handle!.stdin!.on('error', reject)
      if (useBridge) handle!.stdin!.write(JSON.stringify(payload)+'\n', error => error ? reject(error) : done())
      else handle!.stdin!.end(JSON.stringify(payload), done)
    })
    const [outcome, bridged] = await Promise.all([handle.done,
      piped ? pumpDshBridge(host, handle, signal, routes, 2097152, progressEnabled ? record => {
        const clean = JSON.parse(secrets.reduce((text, secret) => text.split(secret).join('[REDACTED]'), JSON.stringify(record)))
        onProgress?.(decodeProgress(clean))
      } : undefined, nativeTools) : Promise.resolve(undefined)])
    await handle.waitForExit()
    if (signal.aborted) throw new Error('RefractAgent task cancelled or timed out; check the saved ledger before resubmitting')
    const stdout = piped ? bridged : handle.collected.stdout?.readFrom(0)
    if (!stdout || stdout.lossy) throw new Error('RefractAgent result is missing or exceeds the output limit')
    let result: unknown
    try { result = JSON.parse(stdout.text) }
    catch { throw new Error('RefractAgent returned no structured result; verify the installed Python core') }
    if (!object(result) || result.schema_version !== 'refractagent-result-v1') {
      const detail = object(result) && typeof result.error === 'string' ? result.error : 'invalid application result'
      throw new Error(detail)
    }
    if (outcome.exitCode !== 0) throw new Error(`RefractAgent ${String(result.status)}: ${JSON.stringify(result.issues)}`)
    if (typeof result.answer !== 'string' || !result.answer || !object(result.costs) || !object(result.models)
      || !object(result.usage) || typeof result.result_path !== 'string') throw new Error('invalid RefractAgent result fields')
    const billingUnit=config.dshModelPool?.billingUnit??config.providerConfig?.billingUnit
    if (typeof result.billing_unit !== 'string' || (billingUnit && result.billing_unit !== billingUnit)) {
      throw new Error('RefractAgent returned a different billing unit')
    }
    for (const key of ['production', 'evaluation', 'unconfirmed']) {
      const value = result.costs[key]
      if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) throw new Error('invalid RefractAgent costs')
    }
    for (const key of ['input_tokens', 'output_tokens', 'cache_read_tokens', 'reasoning_tokens']) {
      const value = result.usage[key] ?? (key === 'cache_read_tokens' || key === 'reasoning_tokens' ? 0 : undefined)
      if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) throw new Error('invalid RefractAgent usage')
    }
    if (result.strategy !== options.model || result.mode !== config.executionMode
      || result.simulated !== !live) throw new Error('RefractAgent returned a different strategy or execution mode')
    if (live && config.template === 'auto' && (result.plan_origin !== 'model'
      || !object(result.plan) || !Array.isArray(result.plan.nodes))) {
      throw new Error('installed core did not return an automatically generated DAG')
    }
    if (progressEnabled) result.dag = decodeDag(result.dag)
    if (result.format_validation !== undefined) {
      const check = decodeFormatValidation(result.format_validation)
      if (config.outputConstraints && JSON.stringify(check.constraints) !== JSON.stringify(config.outputConstraints)) {
        throw new Error('installed core returned different output constraints')
      }
      result.format_validation = check
    }
    else if (config.outputConstraints) throw new Error('installed core did not return output constraint validation')
    return result
  } catch (error) {
    const message = error instanceof Error ? error.message : 'RefractAgent execution failed'
    failed.abort()
    handle?.terminate?.()
    throw new Error(secrets.reduce((text, secret)=>text.split(secret).join('[REDACTED]'), message))
  }
}

export function createAdapter(ctx: AgentContext, source: () => Readonly<Configuration>): AgentAdapter {
  const metadata = (provider: string, model: string): ModelMetadata => {
    const config = source()
    const normalized = normalizeConfiguredModel(config, model)
    const entry = configuredModels(config).find(m => m.id === normalized)
    if (provider !== 'refractagent' || !entry) throw new Error('Unknown RefractAgent strategy model')
    return { ...entry, id: model, provider, name: entry.name + (config.executionMode === 'demo' ? '（模拟）' : ''),
      description: '支持整任务、自动 DAG 和宿主原生工具；执行遵循 DSH 权限与审批。',
      inputModalities: ['text'], context: { contextWindow: 24000 }, defaultMaxTokens: config.maxOutputTokens }
  }
  const adapter: AgentAdapter = {
    providerInfo: provider => ({ id: provider, name: 'RefractAgent 本地路由' }),
    providerRetryPolicy: () => ({ mode: 'normal', maxRetries: 0, retryableCodes: [] }),
    listModels: async provider => configuredModels(source()).map(m => metadata(provider, m.id)),
    resolveModel: async (provider, model) => metadata(provider, model),
    prepareCall: async (provider, model) => ({ model: metadata(provider, model), stream: options => adapter.stream(options) }),
    async *stream(options) {
      metadata(options.provider, options.model)
      const config = source()
      const model = normalizeConfiguredModel(config, options.model)
      const automatic = config.dshModelPool !== undefined || config.providerConfig?.schemaVersion === 'refractagent-providers-v4' || config.template === 'auto'
      const pending = automatic ? (config.executionMode === 'live'
        ? '正在快速拆分任务，随后执行可并行的步骤。\n' : '正在预览自动拆分流程。\n') : ''
      if (pending) {
        yield { type: 'block-start', index: 0, blockType: 'reasoning' }
        yield { type: 'reasoning-delta', index: 0, text: pending }
      }
      const queue: string[] = []
      let wake: (() => void) | undefined
      let ended = false, failure: unknown
      let result: Record<string, unknown> | undefined
      let previous: ProgressEvent | undefined
      let transcript = pending
      const cancelled = new AbortController()
      const work = invoke(ctx, config, { ...options, model,
        signal: AbortSignal.any([cancelled.signal, ...(options.signal ? [options.signal] : [])]) }, event => {
        if (previous && (event.run_id !== previous.run_id || event.sequence <= previous.sequence)) throw new Error('DAG progress sequence mismatch')
        const text = progressText(event, previous)
        previous = event
        if (text) {
          if (queue.length >= 128) throw new Error('DAG progress queue exceeded')
          queue.push(text)
          wake?.()
        }
      }).then(value => { result = value }, error => { failure = error }).finally(() => { ended = true; wake?.() })
      try {
        while (!ended || queue.length) {
          if (queue.length) {
            const text = queue.shift()!
            transcript += text
            yield { type: 'reasoning-delta', index: 0, text }
          } else await new Promise<void>(resolve => { wake = resolve })
        }
        await work
        if (failure) throw failure
        if (!result) throw new Error('missing RefractAgent result')
      } catch (error) {
        if (pending) {
          const failure = publicFailure(error, options.signal?.aborted === true)
          const text = `\n${failure.message}\n以上为最后收到的节点状态，请核对运行记录中的用量。\n`
          yield { type: 'reasoning-delta', index: 0, text }
          yield { type: 'block-end', index: 0, block: { type: 'reasoning', text: transcript + text } }
          yield { type: 'finish', reason: { kind: failure.kind,
            failure: { code: failure.code, message: failure.message } } }
          return
        }
        throw error
      } finally {
        cancelled.abort()
        await work
      }

      const info = pending ? runSummary(result) + `长度检查：${formatValidationSummary(result.format_validation)}\n` : `${result.simulated ? '【模拟演示，无真实模型调用】' : ''}策略：${String(result.strategy_name)}；`
        + `模型：${JSON.stringify(result.model_routes ?? result.models)}；状态：${String(result.status)}；`
        + `生成：${String(result.generation_status ?? '未提供')}；语义评审：${object(result.quality) ? JSON.stringify({ passed: result.quality.passed, score: result.quality.score }) : '未评审'}；`
        + `长度检查：${formatValidationSummary(result.format_validation)}；`
        + (object(result.plan) && Array.isArray(result.plan.nodes) ? `计划：${String(result.plan_origin)}，${result.plan.nodes.length} 个节点；` : '')
        + (typeof result.wall_time_ms === 'number' ? `总耗时：${(result.wall_time_ms / 1000).toFixed(2)} 秒；` : '')
        + (typeof result.plan_ready_ms === 'number' ? `计划就绪：${(result.plan_ready_ms / 1000).toFixed(2)} 秒；` : '')
        + (object(result.content_validation) ? `依赖复核：${JSON.stringify(result.content_validation)}；` : '')
        + (object(result.cost_breakdown) ? `规划／执行／评审：${JSON.stringify(result.cost_breakdown)} ${String(result.billing_unit)}；` : '')
        + `费用：${JSON.stringify(result.costs)} ${String(result.billing_unit)}；记录：${String(result.result_path)}`
      // Operational metadata is separate from the answer, preserving requested JSON/text output.
      if (!pending) yield { type: 'block-start', index: 0, blockType: 'reasoning' }
      yield { type: 'reasoning-delta', index: 0, text: info }
      yield { type: 'block-end', index: 0, block: { type: 'reasoning', text: transcript + info } }
      yield { type: 'block-start', index: 1, blockType: 'text' }
      yield { type: 'text-delta', index: 1, text: result.answer }
      yield { type: 'block-end', index: 1, block: { type: 'text', text: result.answer } }
      const usage = result.usage as Record<string, number>
      yield { type: 'usage', usage: { inputTokens: usage.input_tokens, outputTokens: usage.output_tokens,
        cacheReadTokens: usage.cache_read_tokens ?? 0, reasoningTokens: usage.reasoning_tokens ?? 0 } }
      yield { type: 'finish', reason: { kind: 'stop' }, replayState: { response: {
        refractagent: { runId: result.run_id, strategy: result.strategy, models: result.models,
          modelRoutes: result.model_routes, evaluationModel: result.evaluation_model,
          status: result.status, generationStatus: result.generation_status, quality: result.quality,
          formatValidation: result.format_validation,
          dag: result.dag, plan: result.plan, planOrigin: result.plan_origin, wallTimeMs: result.wall_time_ms,
          planner: result.planner, planReadyMs: result.plan_ready_ms,
          contentValidation: result.content_validation, dynamicDecomposition: result.dynamic_decomposition,
          costBreakdown: result.cost_breakdown,
          costs: result.costs, simulated: result.simulated, resultPath: result.result_path },
      } } }
    },
  }
  return adapter
}

export function apply(ctx: AgentContext, raw: unknown = {}): void {
  const composed = configure(raw)
  let effective: Readonly<Configuration> = composed
  ctx.llm.registerAdapter(['refractagent'], createAdapter(ctx, () => effective))
  installRefractSettings(ctx, composed, section => {
    effective = overlaySettings(composed, section)
  })
}
