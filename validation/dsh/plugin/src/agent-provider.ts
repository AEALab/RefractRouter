/** Native DSH virtual models. Python owns presets, routing and all cost accounting. */
import { resolve } from 'node:path'
import type { DshContext, LlmService, ModelRoute, ProcessHandle } from './contracts.js'
import { dshProviderIssues, pumpDshBridge } from './index.js'

export const name = 'refractagent'
export const inject = ['llm', 'subprocess', 'sandbox', 'sandboxPolicy', 'credentials']

const MODELS = [
  { id: 'economy', name: 'RefractAgent · 省成本' },
  { id: 'balanced', name: 'RefractAgent · 均衡' },
  { id: 'quality', name: 'RefractAgent · 质量优先' },
] as const

interface ProviderConfiguration {
  schemaVersion: 'refractagent-providers-v1'
  billingUnit: string
  qualityMin?: number
  providers: Array<{ id: string; type: 'openai-compatible' | 'ark-agent-plan' | 'dsh';
    baseUrl?: string; credentialEnv?: string; dshProvider?: string; maxTokensParameter?: string }>
  models: Array<{ id: string; provider: string; model: string; role?: 'candidate' | 'judge';
    contextWindow: number; maxOutputTokens?: number; pricing: Record<string, unknown>;
    routing?: Record<string, unknown>; requestOptions?: Record<string, unknown>; jsonMode?: string }>
}
interface Configuration {
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
  template: 'single' | 'compare'
}
interface ModelOptions {
  provider: string
  model: string
  messages: Array<{ role: string; source?: { kind: string; [key: string]: unknown };
    content: Array<{ type: string; text?: string; [key: string]: unknown }> }>
  system?: string
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
export type AgentContext = Pick<DshContext, 'subprocess' | 'sandbox' | 'sandboxPolicy' | 'credentials'> & {
  llm: Partial<LlmService> & { registerAdapter(providers: string[], adapter: AgentAdapter): unknown }
}

function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}
function freezeConfiguration<T>(value: T): T {
  if (value !== null && typeof value === 'object') {
    Object.values(value).forEach(freezeConfiguration)
    Object.freeze(value)
  }
  return value
}

function positive(value: unknown, key: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) throw new Error(`invalid ${key}`)
  return value
}
export function configure(raw: unknown = {}): Readonly<Configuration> {
  if (!object(raw)) throw new Error('RefractAgent configuration must be an object')
  const result = { pythonExecutable: 'python3', runsDir: '.refractagent/runs', executionMode: 'demo',
    allowPaidRuns: false, maxProductionCost: 40, maxEvaluationCost: 80,
    timeoutMs: 300000, maxOutputTokens: 2048, credentialEnv: 'CODEX_ARK_API_KEY', template: 'single',
    preset: undefined as unknown, providerConfig: undefined as unknown, ...raw }
  const allowed = new Set(['pythonExecutable', 'runsDir', 'executionMode', 'allowPaidRuns', 'maxProductionCost',
    'maxEvaluationCost', 'timeoutMs', 'maxOutputTokens', 'credentialEnv', 'template', 'preset', 'providerConfig'])
  if (Object.keys(raw).some(key => !allowed.has(key))) throw new Error('unknown RefractAgent configuration field')
  for (const key of ['pythonExecutable', 'runsDir', 'credentialEnv'] as const) {
    if (typeof result[key] !== 'string' || !result[key].trim()) throw new Error(`invalid ${key}`)
  }
  if (result.executionMode !== 'demo' && result.executionMode !== 'live') throw new Error('invalid executionMode')
  if (result.template !== 'single' && result.template !== 'compare') throw new Error('invalid template')
  if (typeof result.allowPaidRuns !== 'boolean') throw new Error('allowPaidRuns must be boolean')
  for (const key of ['maxProductionCost', 'maxEvaluationCost', 'timeoutMs', 'maxOutputTokens'] as const) positive(result[key], key)
  if (!Number.isInteger(result.maxOutputTokens) || result.maxOutputTokens < 1000 || result.maxOutputTokens > 8192) {
    throw new Error('maxOutputTokens must be an integer in 1000..8192')
  }
  if (!Number.isInteger(result.timeoutMs) || result.timeoutMs > 7200000) throw new Error('invalid timeoutMs')
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(result.credentialEnv)) throw new Error('invalid credentialEnv')
  if (result.preset !== undefined && result.preset !== 'ark-agent-plan') throw new Error('unknown provider preset')
  if (result.providerConfig !== undefined) {
    if (result.preset !== undefined) throw new Error('providerConfig and preset are mutually exclusive')
    const config = result.providerConfig
    if (!object(config) || config.schemaVersion !== 'refractagent-providers-v1'
      || typeof config.billingUnit !== 'string' || !Array.isArray(config.providers) || !Array.isArray(config.models)
      || Object.keys(config).some(k => !['schemaVersion','billingUnit','qualityMin','providers','models'].includes(k))) {
      throw new Error('invalid providerConfig; use refractagent config-example')
    }
    for (const p of config.providers) {
      if (!object(p) || typeof p.id !== 'string' || !['openai-compatible','ark-agent-plan','dsh'].includes(String(p.type))
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
      if (!object(m) || typeof m.id !== 'string' || typeof m.provider !== 'string' || typeof m.model !== 'string'
        || !config.providers.some(p => object(p) && p.id === m.provider)) throw new Error('invalid configured model reference')
    }
    if (Buffer.byteLength(JSON.stringify(config)) > 100000) throw new Error('providerConfig is too large')
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

function conversation(options: ModelOptions): { task: string; context: string } {
  if (!Array.isArray(options.messages) || !options.messages.length) throw new Error('RefractAgent requires conversation messages')
  // DSH also encodes injected instructions and skill catalogs as user messages.
  // Producer attribution, rather than text heuristics, identifies the user's task.
  const latest = [...options.messages].reverse().find(m => m.role === 'user'
    && (m.source === undefined || m.source.kind === 'user')
    && m.content.some(b => b.type === 'text' && b.text?.trim()))
  if (!latest) throw new Error('RefractAgent requires a text user task')
  const task = latest.content.filter(b => b.type === 'text').map(b => b.text ?? '').join('\n')
  const context = JSON.stringify({ system: options.system ?? '', messages: options.messages })
  if (Buffer.byteLength(context) > 120000) throw new Error('RefractAgent conversation is too large; start a shorter text task')
  return { task, context }
}

async function invoke(ctx: AgentContext, config: Readonly<Configuration>, options: ModelOptions): Promise<Record<string, unknown>> {
  if (options.signal?.aborted) throw new Error('RefractAgent task cancelled before dispatch')
  const live = config.executionMode === 'live'
  if (live && !config.allowPaidRuns) throw new Error('RefractAgent paid execution is disabled; enable it with scoped production/evaluation budgets')
  if (options.stop?.length) throw new Error('RefractAgent task models do not support stop sequences')
  if (live && !config.providerConfig && !config.preset) throw new Error('configure providerConfig or explicitly choose preset: ark-agent-plan')
  const payload = { ...conversation(options), strategy: options.model, template: config.template,
    temperature: options.temperature ?? 0, ...(config.providerConfig ? { providerConfig: config.providerConfig } : {}) }
  const routes: ModelRoute[] = []
  for (const model of config.providerConfig?.models ?? []) {
    const provider = config.providerConfig!.providers.find(p=>p.id===model.provider)!
    if (provider.type === 'dsh') routes.push({provider: provider.dshProvider ?? provider.id, model: model.model})
  }
  const useBridge = live && routes.length > 0
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
  const signal = AbortSignal.any([failed.signal, ...(options.signal ? [options.signal] : []), AbortSignal.timeout(config.timeoutMs + 5000)])
  let python: string
  try { python = await ctx.subprocess.resolveExecutable(config.pythonExecutable, env, signal) }
  catch { throw new Error('RefractAgent Python not found; install the core and generate a dsh-config overlay') }
  const outputCap = Math.min(config.maxOutputTokens, options.maxTokens ?? config.maxOutputTokens)
  if (!Number.isInteger(outputCap) || outputCap < 1000) throw new Error('RefractAgent requires maxTokens >= 1000')
  const argv = [python, '-m', 'refractrouter.agent_cli', 'run', useBridge ? '--host-stdio' : '--request-stdin', '--mode', config.executionMode,
    '--runs-dir', runsDir, '--production-budget', String(config.maxProductionCost),
    '--evaluation-budget', String(config.maxEvaluationCost), '--timeout-ms', String(config.timeoutMs),
    '--max-output-tokens', String(outputCap), ...(live ? ['--execute-paid-run'] : []),
    ...(config.preset ? ['--preset', config.preset] : [])]
  const confined = ctx.sandbox.confine(argv, policy)
  let handle: ProcessHandle | undefined
  try {
    handle = ctx.subprocess.spawn({ argv: confined.argv, cwd: policy.workspaceRoot, env,
      stdio: { stdin: 'pipe', stdout: useBridge ? 'pipe' : { maxBytes: 2097152 }, stderr: { maxBytes: 16384 } },
      signal, graceMs: 2000 })
    if (!handle.stdin) throw new Error('RefractAgent process has no input channel')
    await new Promise<void>((done, reject) => {
      handle!.stdin!.on('error', reject)
      if (useBridge) handle!.stdin!.write(JSON.stringify(payload)+'\n', error => error ? reject(error) : done())
      else handle!.stdin!.end(JSON.stringify(payload), done)
    })
    const [outcome, bridged] = await Promise.all([handle.done,
      useBridge ? pumpDshBridge(host!, handle, signal, routes, 2097152) : Promise.resolve(undefined)])
    await handle.waitForExit()
    if (signal.aborted) throw new Error('RefractAgent task cancelled or timed out; check the saved ledger before resubmitting')
    const stdout = useBridge ? bridged : handle.collected.stdout?.readFrom(0)
    if (!stdout || stdout.lossy) throw new Error('RefractAgent result is missing or exceeds the output limit')
    let result: unknown
    try { result = JSON.parse(stdout.text) }
    catch { throw new Error('RefractAgent returned no structured result; verify the installed Python core') }
    if (!object(result) || result.schema_version !== 'refractagent-result-v1') {
      const detail = object(result) && typeof result.error === 'string' ? result.error : 'invalid application result'
      throw new Error(detail)
    }
    if (outcome.exitCode !== 0 && !result.answer) throw new Error(`RefractAgent ${String(result.status)}: ${JSON.stringify(result.issues)}`)
    if (typeof result.answer !== 'string' || !result.answer || !object(result.costs) || !object(result.models)
      || !object(result.usage) || typeof result.result_path !== 'string') throw new Error('invalid RefractAgent result fields')
    if (typeof result.billing_unit !== 'string' || (config.providerConfig && result.billing_unit !== config.providerConfig.billingUnit)) {
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
    return result
  } catch (error) {
    const message = error instanceof Error ? error.message : 'RefractAgent execution failed'
    failed.abort()
    handle?.terminate?.()
    throw new Error(secrets.reduce((text, secret)=>text.split(secret).join('[REDACTED]'), message))
  }
}

export function createAdapter(ctx: AgentContext, config: Readonly<Configuration>): AgentAdapter {
  const metadata = (provider: string, model: string): ModelMetadata => {
    const entry = MODELS.find(m => m.id === model)
    if (provider !== 'refractagent' || !entry) throw new Error('Unknown RefractAgent strategy model')
    return { ...entry, provider, name: entry.name + (config.executionMode === 'demo' ? '（模拟）' : ''),
      description: '文本分析与生成；可选整任务或预设 DAG，工具执行暂不支持。',
      inputModalities: ['text'], context: { contextWindow: 24000 }, defaultMaxTokens: config.maxOutputTokens }
  }
  const adapter: AgentAdapter = {
    providerInfo: provider => ({ id: provider, name: 'RefractAgent 本地路由' }),
    providerRetryPolicy: () => ({ mode: 'normal', maxRetries: 0, retryableCodes: [] }),
    listModels: async provider => MODELS.map(m => metadata(provider, m.id)),
    resolveModel: async (provider, model) => metadata(provider, model),
    prepareCall: async (provider, model) => ({ model: metadata(provider, model), stream: options => adapter.stream(options) }),
    async *stream(options) {
      metadata(options.provider, options.model)
      const result = await invoke(ctx, config, options)
      const info = `${result.simulated ? '【模拟演示，无真实模型调用】' : ''}策略：${String(result.strategy_name)}；`
        + `模型：${JSON.stringify(result.model_routes ?? result.models)}；状态：${String(result.status)}；`
        + `费用：${JSON.stringify(result.costs)} ${String(result.billing_unit)}；记录：${String(result.result_path)}`
      // Operational metadata is separate from the answer, preserving requested JSON/text output.
      yield { type: 'block-start', index: 0, blockType: 'reasoning' }
      yield { type: 'reasoning-delta', index: 0, text: info }
      yield { type: 'block-end', index: 0, block: { type: 'reasoning', text: info } }
      yield { type: 'block-start', index: 1, blockType: 'text' }
      yield { type: 'text-delta', index: 1, text: result.answer }
      yield { type: 'block-end', index: 1, block: { type: 'text', text: result.answer } }
      const usage = result.usage as Record<string, number>
      yield { type: 'usage', usage: { inputTokens: usage.input_tokens, outputTokens: usage.output_tokens,
        cacheReadTokens: usage.cache_read_tokens ?? 0, reasoningTokens: usage.reasoning_tokens ?? 0 } }
      yield { type: 'finish', reason: { kind: 'stop' }, replayState: { response: {
        refractagent: { runId: result.run_id, strategy: result.strategy, models: result.models,
          status: result.status, costs: result.costs, simulated: result.simulated, resultPath: result.result_path },
      } } }
    },
  }
  return adapter
}

export function apply(ctx: AgentContext, raw: unknown = {}): void {
  ctx.llm.registerAdapter(['refractagent'], createAdapter(ctx, configure(raw)))
}
