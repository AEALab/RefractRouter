import { decodeTaskSummary, registerTaskTool, TASK_SUMMARY_SCHEMA, type TaskArguments } from './task-tool.js'
import type { Writable } from 'node:stream'
import type {
  BillingUnit, BridgeResponse, BridgeResponseBase, CapturedOutput, DshContext,
  EvidenceFallback, FinishChunk, JsonSchema, LlmOptions, ModelRoute, Phase,
  PluginConfig, ProcessHandle, TokenUsage, ToolExecution, ValidationRequest, ValidationResult,
} from './contracts.js'
import { decodeEvidence, type RunnerEvidence } from './evidence.js'

export type { DshContext, PluginConfig, ToolArguments, ValidationResult } from './contracts.js'

import { mkdtemp, readFile, stat, writeFile } from 'node:fs/promises'
import { randomUUID } from 'node:crypto'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { createInterface } from 'node:readline'

export const name = 'refractrouter-validation'
export const inject = ['tools', 'subprocess', 'sandbox', 'sandboxPolicy', 'credentials', 'llm']

const DEFAULT_TIMEOUT_MS = 7_200_000
const DEFAULT_OUTPUT_CAPTURE_BYTES = 262_144
const DEFAULT_EVIDENCE_BYTES = 2_097_152
const MAX_MODEL_TIMEOUT_MS = 300_000
const REDACTED = '[REDACTED]'
const DSH_BRIDGE_PROTOCOL = 'refractrouter-dsh-llm/v1'
const AGENT_PLAN_BASE_URL = 'https://ark.cn-beijing.volces.com/api/plan/v3'

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function billingUnit(value: string): BillingUnit {
  if (value !== 'USD' && value !== 'AFP') throw new Error('billingUnit must be USD or AFP')
  return value
}

function phase(value: unknown): Phase {
  if (value !== 'dry-run' && value !== 'pilot' && value !== 'final' && value !== 'contract-replay') {
    throw new Error('phase must be dry-run, pilot, final, or contract-replay')
  }
  return value
}

function positiveFinite(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) {
    throw new Error(`${field} must be a positive finite number`)
  }
  return value
}

function positiveInteger(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value <= 0) {
    throw new Error(`${field} must be a positive safe integer`)
  }
  return value
}

function nonNegativeInteger(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) {
    throw new Error(`${field} must be a non-negative safe integer`)
  }
  return value
}

function configuredString(value: unknown, fallback: string, field: string): string {
  const resolved = value ?? fallback
  if (typeof resolved !== 'string' || resolved.trim().length === 0) {
    throw new Error(`${field} must be a non-empty string`)
  }
  return resolved
}

function redactSensitiveText(value: unknown, secrets: readonly string[]): string {
  let redacted = typeof value === 'string' ? value : String(value ?? '')
  for (const secret of secrets) {
    if (typeof secret === 'string' && secret.length > 0) {
      redacted = redacted.split(secret).join(REDACTED)
    }
  }
  return redacted
}

/** Resolve every deployment choice once, before a tool definition closes over it. */
export function resolveConfig(config: unknown = {}): Readonly<PluginConfig> {
  if (!isRecord(config)) {
    throw new Error('config must be an object')
  }
  const allowed = new Set([
    'allowPaidRuns',
    'maxProductionCost',
    'maxEvaluationCost',
    'billingUnit',
    'maxRetries',
    'uvExecutable',
    'uvCacheDir',
    'runnerPath',
    'taskProfilePath',
    'datasetPath',
    'manifestPath',
    'credentialEnv',
    'timeoutMs',
    'processGraceMs',
    'outputCaptureBytes',
    'maxEvidenceBytes',
  ])
  const unknown = Object.keys(config).filter(key => !allowed.has(key))
  if (unknown.length > 0) throw new Error(`unknown config fields: ${unknown.join(', ')}`)
  const resolved = {
    allowPaidRuns: config.allowPaidRuns ?? false,
    maxProductionCost: positiveFinite(config.maxProductionCost ?? 2, 'maxProductionCost'),
    maxEvaluationCost: positiveFinite(config.maxEvaluationCost ?? 1, 'maxEvaluationCost'),
    billingUnit: billingUnit(configuredString(config.billingUnit, 'USD', 'billingUnit').toUpperCase()),
    maxRetries: nonNegativeInteger(config.maxRetries ?? 0, 'maxRetries'),
    uvExecutable: configuredString(config.uvExecutable, 'uv', 'uvExecutable'),
    uvCacheDir: configuredString(
      config.uvCacheDir,
      join(tmpdir(), 'refractrouter-uv-cache'),
      'uvCacheDir',
    ),
    runnerPath: configuredString(
      config.runnerPath,
      'validation/dsh/real_runner.py',
      'runnerPath',
    ),
    taskProfilePath: configuredString(config.taskProfilePath, 'data/routing/demo-usd-v1.json', 'taskProfilePath'),
    datasetPath: configuredString(
      config.datasetPath,
      'data/benchmarks/v0.1.json',
      'datasetPath',
    ),
    manifestPath: configuredString(
      config.manifestPath,
      'data/model-manifests/openai-gpt-5.4.json',
      'manifestPath',
    ),
    credentialEnv: configuredString(
      config.credentialEnv,
      'OPENAI_API_KEY',
      'credentialEnv',
    ),
    timeoutMs: positiveInteger(config.timeoutMs ?? DEFAULT_TIMEOUT_MS, 'timeoutMs'),
    processGraceMs: positiveInteger(config.processGraceMs ?? 5_000, 'processGraceMs'),
    outputCaptureBytes: positiveInteger(
      config.outputCaptureBytes ?? DEFAULT_OUTPUT_CAPTURE_BYTES, 'outputCaptureBytes',
    ),
    maxEvidenceBytes: positiveInteger(
      config.maxEvidenceBytes ?? DEFAULT_EVIDENCE_BYTES, 'maxEvidenceBytes',
    ),
  }
  if (typeof resolved.allowPaidRuns !== 'boolean') {
    throw new Error('allowPaidRuns must be a boolean')
  }
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(resolved.credentialEnv)) {
    throw new Error('credentialEnv must be a POSIX environment variable name')
  }
  return Object.freeze({ ...resolved, allowPaidRuns: resolved.allowPaidRuns })
}

async function readExecutionManifest(path: string) {
  const raw: unknown = JSON.parse(await readFile(path, 'utf8'))
  if (!isRecord(raw) || raw.schema_version !== 'v0.2' || !Array.isArray(raw.models)) {
    throw new Error('plugin requires a v0.2 model manifest')
  }
  const defaults = isRecord(raw.defaults) ? raw.defaults : {}
  const models = raw.models.map((model: unknown) => {
    if (!isRecord(model)) throw new Error('invalid model manifest entry')
    return { ...defaults, ...model }
  })
  if (models.length === 0) throw new Error('model manifest has no models')
  const billingUnits = new Set(models.map(model => String(model.billing_unit).toUpperCase()))
  const wireApis = new Set(models.map(model => String(model.wire_api)))
  const credentialEnvs = new Set(models.map(model => String(model.api_key_env)))
  const providers = new Set(models.map(model => String(model.provider)))
  const baseURLs = new Set(models.map(model => String(model.base_url ?? '').replace(/\/+$/, '')))
  if (billingUnits.size !== 1 || wireApis.size !== 1 || credentialEnvs.size !== 1) {
    throw new Error('plugin requires one billing unit, wire API, and credential reference')
  }
  const wireApi = [...wireApis][0]
  if (!['chat-completions', 'dsh-llm'].includes(wireApi)) {
    throw new Error(`unsupported manifest wire API: ${wireApi}`)
  }
  const unit = billingUnit([...billingUnits][0])
  const baseURL = baseURLs.size === 1 ? [...baseURLs][0] : undefined
  if (wireApi === 'chat-completions' && (baseURL === undefined || baseURL.length === 0)) {
    throw new Error('chat-completions manifest requires one base URL')
  }
  if (
    unit === 'AFP'
    && (
      wireApi !== 'chat-completions'
      || baseURL !== AGENT_PLAN_BASE_URL
      || providers.size !== 1
      || !providers.has('ark-plan')
    )
  ) {
    throw new Error(`AFP validation requires ark-plan at ${AGENT_PLAN_BASE_URL}`)
  }
  const routes = models.map(model => ({
    provider: String(model.provider),
    model: String(model.api_model),
  }))
  return {
    billingUnit: unit,
    wireApi,
    baseURL,
    credentialEnv: [...credentialEnvs][0],
    routes,
  }
}

/** Dependency-free Standard Schema keeps linked checkout bundles self-contained. */
export const Config = {
  '~standard': {
    version: 1 as const,
    vendor: 'dsh-refractrouter-validation',
    validate(value: unknown) {
      try {
        return { value: resolveConfig(value ?? {}) }
      } catch (error) {
        return {
          issues: [{ message: error instanceof Error ? error.message : String(error) }],
        }
      }
    },
  },
}

function resolveRequest(args: unknown, config: Readonly<PluginConfig>): ValidationRequest {
  if (!isRecord(args)) {
    throw new Error('tool arguments must be an object')
  }
  const allowed = new Set([
    'phase',
    'repeats',
    'executePaidRun',
    'maxProductionCost',
    'maxEvaluationCost',
  ])
  const unknown = Object.keys(args).filter(key => !allowed.has(key))
  if (unknown.length > 0) throw new Error(`unknown tool arguments: ${unknown.join(', ')}`)
  const requestedPhase = phase(args.phase)
  if (args.executePaidRun !== undefined && typeof args.executePaidRun !== 'boolean') {
    throw new Error('executePaidRun must be a boolean')
  }
  const repeats = args.repeats ?? 1
  if (typeof repeats !== 'number' || !Number.isInteger(repeats) || repeats <= 0) {
    throw new Error('repeats must be a positive integer')
  }
  if (args.phase === 'contract-replay' && (repeats > 3 || config.maxRetries !== 0)) {
    throw new Error('contract-replay requires repeats <= 3 and configured maxRetries = 0')
  }
  const paid = args.executePaidRun ?? false
  if (!paid) {
    if (args.maxProductionCost !== undefined || args.maxEvaluationCost !== undefined) {
      throw new Error('cost limits are valid only when executePaidRun is true')
    }
    return { phase: requestedPhase, repeats, paid: false }
  }
  if (!config.allowPaidRuns) {
    throw new Error('paid validation is disabled by plugin config (allowPaidRuns: false)')
  }
  const productionLimit = positiveFinite(
    args.maxProductionCost,
    'maxProductionCost',
  )
  const evaluationLimit = positiveFinite(
    args.maxEvaluationCost,
    'maxEvaluationCost',
  )
  if (productionLimit > config.maxProductionCost) {
    throw new Error(
      `maxProductionCost exceeds configured ceiling ${String(config.maxProductionCost)}`,
    )
  }
  if (evaluationLimit > config.maxEvaluationCost) {
    throw new Error(
      `maxEvaluationCost exceeds configured ceiling ${String(config.maxEvaluationCost)}`,
    )
  }
  return {
    phase: requestedPhase,
    repeats,
    paid: true,
    productionLimit,
    evaluationLimit,
  }
}

function workspaceOf(exec: ToolExecution): string {
  const cwd = exec.agent?.session?.header?.cwd
  return resolve(typeof cwd === 'string' && cwd.length > 0 ? cwd : process.cwd())
}

function artifactHashes(evidence: RunnerEvidence, secrets: readonly string[]) {
  if (evidence === null || typeof evidence !== 'object') return []
  const artifacts = evidence.artifacts
  if (artifacts === null || typeof artifacts !== 'object') return []
  return Object.entries(artifacts)
    .filter((entry): entry is [string, string] => typeof entry[1] === 'string')
    .map(([artifact, sha256]) => ({
      artifact: redactSensitiveText(artifact, secrets),
      sha256,
    }))
}

function summarizeEvidence(
  evidence: RunnerEvidence, fallback: EvidenceFallback, secrets: readonly string[],
): ValidationResult {
  const preflight = evidence?.preflight
  const plan = preflight?.call_plan
  const costs = preflight?.cost_estimates
  const inputs = evidence?.inputs
  const evidenceIssues = Array.isArray(evidence?.issues)
    ? evidence.issues
      .filter(issue => typeof issue === 'string')
      .map(issue => redactSensitiveText(issue, secrets))
    : []
  const issues = [...new Set([...evidenceIssues, ...fallback.issues])]
  return {
    status: evidence?.status === 'pass' && issues.length === 0 ? 'pass' : 'fail',
    mode: evidence?.mode === 'paid' ? 'paid' : 'preflight',
    phase: fallback.phase,
    exitCode: fallback.exitCode,
    signal: fallback.signal,
    timedOut: fallback.timedOut,
    aborted: fallback.aborted,
    evidencePath: fallback.evidencePath,
    outputDir: fallback.outputDir,
    credentialConfigured: fallback.credentialConfigured,
    modelProviderConfigured: fallback.modelProviderConfigured,
    billingUnit: preflight?.billing_unit ?? fallback.billingUnit,
    sandboxMode: fallback.sandboxMode,
    ...fallback.sandboxEnforcement === undefined
      ? {}
      : { sandboxEnforcement: fallback.sandboxEnforcement },
    issues,
    ...plan === null || typeof plan !== 'object'
      ? {}
      : {
          callPlan: {
            trainingModelCalls: plan.training_model_calls,
            productionModelCalls: plan.production_model_calls,
            judgeModelCalls: plan.judge_model_calls,
            totalModelCalls: plan.total_model_calls,
          },
        },
    ...costs === null || typeof costs !== 'object'
      ? {}
      : {
          costEstimate: {
            billingUnit: costs.billing_unit,
            production: costs.production_upper_estimate,
            evaluation: costs.evaluation_upper_estimate,
            total: costs.total_upper_estimate,
          },
        },
    inputHashes: {
      dataset: inputs?.dataset?.sha256 ?? '',
      manifest: inputs?.model_manifest?.sha256 ?? '',
      corpus: inputs?.corpus?.sha256 ?? '',
      code: inputs?.code?.sha256 ?? '',
    },
    artifactHashes: artifactHashes(evidence, secrets),
    ...evidence.task === undefined ? {} : { task: decodeTaskSummary(
      JSON.parse(redactSensitiveText(JSON.stringify(evidence.task), secrets)) as unknown,
    ) },
    ...fallback.stdoutTail.length === 0 ? {} : { stdoutTail: fallback.stdoutTail },
    ...fallback.stderrTail.length === 0 ? {} : { stderrTail: fallback.stderrTail },
  }
}

async function readEvidence(path: string, maxBytes: number): Promise<RunnerEvidence | undefined> {
  let info
  try {
    info = await stat(path)
  } catch (error) {
    if (isRecord(error) && error.code === 'ENOENT') return undefined
    throw error
  }
  if (!info.isFile()) throw new Error(`evidence path is not a file: ${path}`)
  if (info.size > maxBytes) {
    throw new Error(`evidence exceeds configured ${String(maxBytes)} byte limit`)
  }
  return decodeEvidence(JSON.parse(await readFile(path, 'utf8')) as unknown)
}

function capturedTail(captured: CapturedOutput | undefined, secrets: readonly string[]): string {
  if (captured?.lossy === true) return '[captured output omitted after truncation]'
  return redactSensitiveText(captured?.text ?? '', secrets)
}

function bridgeFailureType(code: unknown): string {
  const normalized = String(code ?? '').toUpperCase()
  if (normalized.includes('AUTH') || normalized.includes('CREDENTIAL')) return 'authentication'
  if (normalized.includes('RATE_LIMIT')) return 'rate-limit'
  if (normalized.includes('QUOTA')) return 'quota-exhausted'
  if (normalized.includes('TIMEOUT')) return 'timeout'
  if (normalized.includes('ABORT')) return 'aborted'
  if (normalized.includes('CONTEXT')) return 'context-window-exceeded'
  return 'provider-error'
}

function replayRequestId(replayState: FinishChunk['replayState']) {
  const response = replayState?.response
  if (!isRecord(response)) return undefined
  const value = response.requestId ?? response.responseId ?? response.id
  return typeof value === 'string' && value.length > 0 ? value : undefined
}

export async function callDshLlm(
  ctx: { llm: Pick<DshContext['llm'], 'stream'> }, rawRequest: unknown, signal?: AbortSignal,
): Promise<BridgeResponse> {
  const request = isRecord(rawRequest) ? rawRequest : {}
  const id = String(request.id ?? '')
  const base: BridgeResponseBase = { protocol: DSH_BRIDGE_PROTOCOL, type: 'response', id }
  let timeoutSignal: AbortSignal | undefined
  try {
    if (
      request?.protocol !== DSH_BRIDGE_PROTOCOL
      || request?.type !== 'request'
      || id.length === 0
      || typeof request.provider !== 'string'
      || typeof request.model !== 'string'
      || !Array.isArray(request.messages)
    ) {
      throw new Error('invalid DSH bridge request')
    }
    const timeoutMs = positiveInteger(request.timeout_ms, 'timeout_ms')
    if (timeoutMs > MAX_MODEL_TIMEOUT_MS) {
      throw new Error(`timeout_ms must be no greater than ${String(MAX_MODEL_TIMEOUT_MS)}`)
    }
    timeoutSignal = AbortSignal.timeout(timeoutMs)
    const callSignal = AbortSignal.any(signal === undefined
      ? [timeoutSignal]
      : [signal, timeoutSignal])
    const system: string[] = []
    const messages: LlmOptions['messages'] = []
    for (const message of request.messages as unknown[]) {
      if (!isRecord(message) || typeof message.content !== 'string') {
        throw new Error('invalid DSH bridge message')
      }
      if (message.role === 'system') {
        system.push(message.content)
      } else if (message.role === 'user') {
        messages.push(Object.freeze({
          id: randomUUID(),
          role: 'user',
          content: Object.freeze([Object.freeze({ type: 'text', text: message.content })]),
          source: Object.freeze({ kind: 'plugin', plugin: name }),
        }))
      } else {
        throw new Error(`unsupported DSH bridge role: ${String(message.role)}`)
      }
    }
    const options: LlmOptions = {
      provider: request.provider,
      model: request.model,
      messages,
      system: system.length === 0 ? undefined : system.join('\n\n'),
      temperature: Number(request.temperature ?? 0),
      maxTokens: Number(request.max_tokens),
      signal: callSignal,
    }
    const reasoningEffort = isRecord(request.request_options)
      ? request.request_options.reasoning_effort : undefined
    if (typeof reasoningEffort === 'string' && reasoningEffort.length > 0) {
      options.reasoningEffort = reasoningEffort
    }
    let content = ''
    let usage: TokenUsage = {}
    let finish: FinishChunk | undefined
    const stream = ctx.llm.stream(options)
    const iterator = stream[Symbol.asyncIterator]()
    try {
      while (true) {
        const step = await nextWithSignal(iterator, callSignal)
        if (step.done) break
        const chunk = step.value
        if (chunk.type === 'text-delta') content += chunk.text
        if (chunk.type === 'usage') usage = chunk.usage ?? {}
        if (chunk.type === 'finish') finish = chunk
      }
    } finally {
      if (callSignal.aborted && typeof iterator.return === 'function') {
        void Promise.resolve(iterator.return()).catch(() => {})
      }
    }
    if (finish === undefined) throw new Error('DSH LLM stream ended without finish')
    if (finish.reason?.kind === 'error' || finish.reason?.kind === 'aborted') {
      const failure = finish.reason.failure ?? {}
      const timedOut = timeoutSignal.aborted === true && signal?.aborted !== true
      return {
        ...base,
        ok: false,
        failure_type: timedOut ? 'timeout' : bridgeFailureType(failure.code),
        message: String(failure.message ?? 'DSH LLM request failed').slice(0, 300),
        request_id: failure.requestId,
      }
    }
    const cachedInput = Number(usage.cacheReadTokens ?? 0)
    const cacheWrite = Number(usage.cacheWriteTokens ?? 0)
    return {
      ...base,
      ok: true,
      content,
      usage: {
        input_tokens: Number(usage.inputTokens ?? 0) + cachedInput + cacheWrite,
        output_tokens: Number(usage.outputTokens ?? 0),
        cached_input_tokens: cachedInput,
        reasoning_tokens: Number(usage.reasoningTokens ?? 0),
      },
      finish_reason: finish.reason?.kind,
      request_id: replayRequestId(finish.replayState),
    }
  } catch (error) {
    const timedOut = timeoutSignal?.aborted === true && signal?.aborted !== true
    return {
      ...base,
      ok: false,
      failure_type: timedOut ? 'timeout' : signal?.aborted ? 'aborted' : 'provider-error',
      message: String(error instanceof Error ? error.message : error).slice(0, 300),
    }
  }
}

function nextWithSignal<T>(iterator: AsyncIterator<T>, signal: AbortSignal): Promise<IteratorResult<T>> {
  if (signal.aborted) return Promise.reject(signal.reason ?? new Error('aborted'))
  return new Promise((resolveNext, rejectNext) => {
    const onAbort = () => {
      signal.removeEventListener('abort', onAbort)
      rejectNext(signal.reason ?? new Error('aborted'))
    }
    signal.addEventListener('abort', onAbort, { once: true })
    Promise.resolve(iterator.next()).then(
      value => {
        signal.removeEventListener('abort', onAbort)
        resolveNext(value)
      },
      error => {
        signal.removeEventListener('abort', onAbort)
        rejectNext(error)
      },
    )
  })
}

function tailCapture(maxBytes: number) {
  let buffer = Buffer.alloc(0)
  let lossy = false
  return {
    append(text: string) {
      buffer = Buffer.concat([buffer, Buffer.from(text)])
      if (buffer.length > maxBytes) {
        buffer = buffer.subarray(buffer.length - maxBytes)
        lossy = true
      }
    },
    read() { return { text: buffer.toString('utf8'), lossy } },
  }
}

async function writeLine(stream: Writable, value: BridgeResponse) {
  const line = `${JSON.stringify(value)}\n`
  if (stream.write(line)) return
  await new Promise<void>(resolveDrain => stream.once('drain', resolveDrain))
}

async function pumpDshBridge(
  ctx: DshContext, handle: ProcessHandle, signal: AbortSignal, routes: ModelRoute[], maxBytes: number,
) {
  if (handle.stdout === undefined || handle.stdin === undefined) {
    throw new Error('DSH bridge requires piped child stdin and stdout')
  }
  const allowed = new Set(routes.map(route => `${route.provider}\u0000${route.model}`))
  const capture = tailCapture(maxBytes)
  const lines = createInterface({ input: handle.stdout, crlfDelay: Infinity })
  try {
    for await (const line of lines) {
      if (Buffer.byteLength(line) > maxBytes) {
        throw new Error('DSH bridge request exceeds configured capture limit')
      }
      let request: unknown
      try {
        request = JSON.parse(line)
      } catch {
        capture.append(`${line}\n`)
        continue
      }
      if (!isRecord(request) || request.protocol !== DSH_BRIDGE_PROTOCOL || request.type !== 'request') {
        capture.append(`${line}\n`)
        continue
      }
      const route = `${String(request.provider)}\u0000${String(request.model)}`
      const response: BridgeResponse = allowed.has(route)
        ? await callDshLlm(ctx, request, signal)
        : {
            protocol: DSH_BRIDGE_PROTOCOL,
            type: 'response',
            id: String(request.id ?? ''),
            ok: false,
            failure_type: 'invalid-model-config',
            message: 'model route is not frozen in the manifest',
          }
      await writeLine(handle.stdin, response)
    }
  } finally {
    handle.stdin.end()
  }
  return capture.read()
}

async function dshProviderIssues(ctx: DshContext, routes: ModelRoute[]): Promise<string[]> {
  const providers = new Set(ctx.llm.listProviders().map(provider => provider.id))
  const issues = []
  const checkedPolicies = new Set()
  for (const route of routes) {
    if (!providers.has(route.provider)) {
      issues.push(`missing-llm-provider:${route.provider}`)
      continue
    }
    if (!checkedPolicies.has(route.provider)) {
      checkedPolicies.add(route.provider)
      try {
        const policy = ctx.llm.providerRetryPolicy(route.provider)
        if (policy?.mode !== 'normal' || policy.maxRetries !== 0) {
          issues.push(`llm-provider-retry-policy-not-zero:${route.provider}`)
        }
      } catch {
        issues.push(`unresolved-llm-retry-policy:${route.provider}`)
      }
    }
    try {
      await ctx.llm.resolveModelInfo(route.provider, route.model)
    } catch {
      issues.push(`unresolved-llm-model:${route.provider}/${route.model}`)
    }
  }
  return [...new Set(issues)]
}

async function executeValidation(
  ctx: DshContext, args: unknown, exec: ToolExecution, config: Readonly<PluginConfig>, taskInput?: TaskArguments,
): Promise<ValidationResult> {
  const request = resolveRequest(args, config)
  if (taskInput && config.maxRetries !== 0) throw new Error('text tasks require zero retries')
  const workspace = workspaceOf(exec)
  const manifestPath = resolve(workspace, config.manifestPath)
  const manifest = await readExecutionManifest(manifestPath)
  if (manifest.billingUnit !== config.billingUnit) {
    throw new Error(
      `manifest billing unit ${manifest.billingUnit} does not match plugin billingUnit ${config.billingUnit}`,
    )
  }
  if (manifest.credentialEnv !== config.credentialEnv) {
    throw new Error(
      `manifest credential ${manifest.credentialEnv} does not match plugin credentialEnv ${config.credentialEnv}`,
    )
  }
  const providerIssues = manifest.wireApi === 'dsh-llm'
    ? await dshProviderIssues(ctx, manifest.routes)
    : []
  if (request.paid && providerIssues.length > 0) {
    throw new Error(`paid validation requires safe DSH routes: ${providerIssues.join(', ')}`)
  }
  const runRoot = await mkdtemp(join(tmpdir(), 'refractrouter-dsh-plugin-'))
  const outputDir = join(runRoot, 'output')
  const evidencePath = join(runRoot, 'evidence.json')
  const requestPath = join(runRoot, 'task-request.json')
  if (taskInput) await writeFile(requestPath, JSON.stringify(taskInput), 'utf8')
  const reference = config.credentialEnv
  let credentialInfo
  try {
    credentialInfo = await ctx.credentials.describe(reference)
  } catch {
    throw new Error(`failed to describe credential ${reference}`)
  }
  const credentialConfigured = credentialInfo.configured === true
  const env: Record<string, string> = { UV_CACHE_DIR: config.uvCacheDir }
  const secrets: string[] = []
  if (request.paid) {
    if (!credentialConfigured) {
      throw new Error(`paid validation requires configured credential ${config.credentialEnv}`)
    }
    env.REFRACTROUTER_MODEL_PROGRESS = join(outputDir, 'model-progress.ndjson')
    if (manifest.wireApi === 'dsh-llm') {
      env.REFRACTROUTER_DSH_BRIDGE = 'stdio'
      env.REFRACTROUTER_DSH_PROGRESS = join(outputDir, 'bridge-progress.ndjson')
    } else {
      let credential
      try {
        credential = await ctx.credentials.resolve(reference)
      } catch {
        throw new Error(`failed to resolve credential ${reference}`)
      }
      if (credential === undefined) {
        throw new Error(`paid validation requires configured credential ${config.credentialEnv}`)
      }
      if (typeof credential.value !== 'string' || credential.value.length === 0) {
        throw new Error(`paid validation requires non-empty credential ${config.credentialEnv}`)
      }
      secrets.push(credential.value)
      env[config.credentialEnv] = credential.value
    }
  }
  exec.signal.throwIfAborted()
  let executable
  try {
    executable = await ctx.subprocess.resolveExecutable(
      config.uvExecutable,
      env,
      exec.signal,
    )
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    throw new Error(`failed to resolve validation executable: ${redactSensitiveText(detail, secrets)}`)
  }
  const argv = [
    executable,
    'run',
    '--extra',
    'dev',
    '--extra',
    'deepagents',
    'python',
    resolve(workspace, taskInput ? 'validation/dsh/task_runner.py' : config.runnerPath),
    ...taskInput
      ? ['--request-file', requestPath, '--profile', resolve(workspace, config.taskProfilePath)]
      : ['--dataset', resolve(workspace, config.datasetPath), '--phase', request.phase,
          '--repeats', String(request.repeats)],
    '--manifest',
    manifestPath,
    '--max-retries',
    String(config.maxRetries),
    '--output-dir',
    outputDir,
    '--evidence',
    evidencePath,
    '--invoked-by',
    'dsh-plugin',
  ]
  if (request.paid) {
    argv.push(
      '--execute-paid-run',
      '--max-production-cost',
      String(request.productionLimit),
      '--max-evaluation-cost',
      String(request.evaluationLimit),
    )
  }
  const policy = ctx.sandboxPolicy.resolve(
    exec.agent === undefined ? {} : { session: exec.agent.session },
  )
  const confined = policy.mode === 'danger-full-access'
    ? undefined
    : ctx.sandbox.confine(argv, policy)
  const timeoutSignal = AbortSignal.timeout(taskInput && request.paid
    ? Math.max(1, Math.ceil(Math.min(config.timeoutMs, taskInput.latencyMaxMs))) : config.timeoutMs)
  const signal = AbortSignal.any([exec.signal, timeoutSignal])
  let handle
  let outcome
  let bridgedStdout
  const useBridge = request.paid && manifest.wireApi === 'dsh-llm'
  try {
    handle = ctx.subprocess.spawn({
      argv: confined?.argv ?? argv,
      cwd: workspace,
      env,
      stdio: {
        stdin: useBridge ? 'pipe' : 'ignore',
        stdout: useBridge ? 'pipe' : { maxBytes: config.outputCaptureBytes },
        stderr: { maxBytes: config.outputCaptureBytes },
      },
      graceMs: config.processGraceMs,
      signal,
    })
    if (useBridge) {
      ;[outcome, bridgedStdout] = await Promise.all([
        handle.done,
        pumpDshBridge(ctx, handle, signal, manifest.routes, config.outputCaptureBytes),
      ])
    } else {
      outcome = await handle.done
    }
    await handle.waitForExit()
  } catch (error) {
    handle?.terminate?.()
    await handle?.waitForExit?.()
    const detail = error instanceof Error ? error.message : String(error)
    throw new Error(`validation subprocess failed: ${redactSensitiveText(detail, secrets)}`)
  }
  const stdout = useBridge ? bridgedStdout : handle.collected.stdout?.readFrom(0)
  const stderr = handle.collected.stderr?.readFrom(0)
  const stdoutTail = capturedTail(stdout, secrets)
  const stderrTail = capturedTail(stderr, secrets)
  const timedOut = timeoutSignal.aborted && !exec.signal.aborted
  const aborted = exec.signal.aborted
  let evidence
  const fallbackIssues = [...providerIssues]
  try {
    evidence = await readEvidence(evidencePath, config.maxEvidenceBytes)
  } catch (error) {
    fallbackIssues.push(`invalid-evidence:${error instanceof Error ? error.message : String(error)}`)
  }
  if (outcome.exitCode !== 0) fallbackIssues.push(`plugin-runner-exit:${String(outcome.exitCode)}`)
  if (evidence === undefined) fallbackIssues.push('missing-evidence')
  if (taskInput && !evidence?.task) fallbackIssues.push('missing-task-result')
  if (timedOut) fallbackIssues.push('plugin-runner-timeout')
  if (aborted) fallbackIssues.push('plugin-runner-aborted')
  if (stdout?.lossy === true) fallbackIssues.push('plugin-runner-stdout-truncated')
  if (stderr?.lossy === true) fallbackIssues.push('plugin-runner-stderr-truncated')
  const fallback: EvidenceFallback = {
    phase: request.phase,
    exitCode: outcome.exitCode,
    signal: outcome.signal,
    timedOut,
    aborted,
    evidencePath,
    outputDir,
    credentialConfigured,
    modelProviderConfigured: providerIssues.length === 0,
    billingUnit: manifest.billingUnit,
    sandboxMode: policy.mode,
    sandboxEnforcement: confined?.enforcement,
    issues: fallbackIssues,
    stdoutTail,
    stderrTail,
  }
  if (evidence === undefined) {
    return {
      status: 'fail',
      mode: request.paid ? 'paid' : 'preflight',
      phase: request.phase,
      exitCode: outcome.exitCode,
      signal: outcome.signal,
      timedOut,
      aborted,
      evidencePath,
      outputDir,
      credentialConfigured,
      modelProviderConfigured: providerIssues.length === 0,
      billingUnit: manifest.billingUnit,
      sandboxMode: policy.mode,
      ...confined === undefined ? {} : { sandboxEnforcement: confined.enforcement },
      issues: fallbackIssues,
      inputHashes: { dataset: '', manifest: '', corpus: '', code: '' },
      artifactHashes: [],
      ...stdoutTail.length === 0 ? {} : { stdoutTail },
      ...stderrTail.length === 0 ? {} : { stderrTail },
    }
  }
  return summarizeEvidence(evidence, fallback, secrets)
}

const OUTPUT_SCHEMA: JsonSchema = {
  type: 'object',
  additionalProperties: false,
  required: [
    'status',
    'mode',
    'phase',
    'exitCode',
    'signal',
    'timedOut',
    'aborted',
    'evidencePath',
    'outputDir',
    'credentialConfigured',
    'modelProviderConfigured',
    'billingUnit',
    'sandboxMode',
    'issues',
    'inputHashes',
    'artifactHashes',
  ],
  properties: {
    status: { type: 'string', enum: ['pass', 'fail'] },
    mode: { type: 'string', enum: ['preflight', 'paid'] },
    phase: { type: 'string', enum: ['dry-run', 'pilot', 'final', 'contract-replay'] },
    exitCode: { oneOf: [{ type: 'integer' }, { type: 'null' }] },
    signal: { oneOf: [{ type: 'string' }, { type: 'null' }] },
    timedOut: { type: 'boolean' },
    aborted: { type: 'boolean' },
    evidencePath: { type: 'string' },
    outputDir: { type: 'string' },
    credentialConfigured: { type: 'boolean' },
    modelProviderConfigured: { type: 'boolean' },
    billingUnit: { type: 'string', enum: ['USD', 'AFP'] },
    sandboxMode: {
      type: 'string',
      enum: ['read-only', 'workspace-write', 'danger-full-access'],
    },
    sandboxEnforcement: { type: 'string', enum: ['full', 'partial'] },
    issues: { type: 'array', items: { type: 'string' } },
    callPlan: {
      type: 'object',
      additionalProperties: false,
      required: [
        'trainingModelCalls',
        'productionModelCalls',
        'judgeModelCalls',
        'totalModelCalls',
      ],
      properties: {
        trainingModelCalls: { type: 'integer' },
        productionModelCalls: { type: 'integer' },
        judgeModelCalls: { type: 'integer' },
        totalModelCalls: { type: 'integer' },
      },
    },
    costEstimate: {
      type: 'object',
      additionalProperties: false,
      required: ['billingUnit', 'production', 'evaluation', 'total'],
      properties: {
        billingUnit: { type: 'string', enum: ['USD', 'AFP'] },
        production: { type: 'number' },
        evaluation: { type: 'number' },
        total: { type: 'number' },
      },
    },
    inputHashes: {
      type: 'object',
      additionalProperties: false,
      required: ['dataset', 'manifest', 'corpus', 'code'],
      properties: {
        dataset: { type: 'string' },
        manifest: { type: 'string' },
        corpus: { type: 'string' },
        code: { type: 'string' },
      },
    },
    artifactHashes: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['artifact', 'sha256'],
        properties: {
          artifact: { type: 'string' },
          sha256: { type: 'string' },
        },
      },
    },
    task: TASK_SUMMARY_SCHEMA,
    stdoutTail: { type: 'string' },
    stderrTail: { type: 'string' },
  },
}

export function apply(ctx: DshContext, rawConfig: unknown = {}): void {
  const config = resolveConfig(rawConfig)
  ctx.tools.register({
    name: 'refractrouter_validate',
    description: 'Run the fixed RefractRouter validation pipeline and return structured evidence. '
      + 'Preflight is zero-cost. Paid execution is unavailable unless the installed bundle explicitly '
      + 'enables it and the call supplies both cost limits within the configured ceilings.',
    parameters: {
      type: 'object',
      additionalProperties: false,
      required: ['phase'],
      properties: {
        phase: {
          type: 'string',
          enum: ['dry-run', 'pilot', 'final', 'contract-replay'],
          description: 'Benchmark phase or bounded replay of the seven frozen issue #25 contract failures.',
        },
        repeats: {
          type: 'integer',
          description: 'Positive integer repeat count; defaults to 1.',
        },
        executePaidRun: {
          type: 'boolean',
          description: 'Actually invoke candidate and judge models. Defaults to false.',
        },
        maxProductionCost: {
          type: 'number',
          description: 'Required paid-run production ceiling in the configured billing unit.',
        },
        maxEvaluationCost: {
          type: 'number',
          description: 'Required paid-run judge ceiling in the configured billing unit.',
        },
      },
    },
    output: {
      schema: OUTPUT_SCHEMA,
      render: (_args, value) => [{
        type: 'text',
        text: JSON.stringify({
          status: value.status,
          mode: value.mode,
          phase: value.phase,
          billingUnit: value.billingUnit,
          issues: value.issues,
          callPlan: value.callPlan,
          costEstimate: value.costEstimate,
          evidencePath: value.evidencePath,
        }),
      }],
    },
    execute: (args, exec) => executeValidation(ctx, args, exec, config),
  })
  registerTaskTool(ctx, OUTPUT_SCHEMA, (input, exec) => executeValidation(ctx, {
    phase: 'dry-run', executePaidRun: input.mode === 'plan' || input.mode === 'run',
    maxProductionCost: input.maxProductionCost, maxEvaluationCost: input.maxEvaluationCost,
  }, exec, config, input))
}
