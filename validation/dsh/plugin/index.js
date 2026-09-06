import { mkdtemp, readFile, stat } from 'node:fs/promises'
import { randomUUID } from 'node:crypto'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { createInterface } from 'node:readline'

export const name = 'refractrouter-validation'
export const inject = ['tools', 'subprocess', 'sandbox', 'sandboxPolicy', 'credentials', 'llm']

const DEFAULT_TIMEOUT_MS = 7_200_000
const DEFAULT_OUTPUT_CAPTURE_BYTES = 262_144
const DEFAULT_EVIDENCE_BYTES = 2_097_152
const REDACTED = '[REDACTED]'
const DSH_BRIDGE_PROTOCOL = 'refractrouter-dsh-llm/v1'

function positiveFinite(value, field) {
  if (!Number.isFinite(value) || value <= 0) {
    throw new Error(`${field} must be a positive finite number`)
  }
  return value
}

function positiveInteger(value, field) {
  if (!Number.isSafeInteger(value) || value <= 0) {
    throw new Error(`${field} must be a positive safe integer`)
  }
  return value
}

function nonNegativeInteger(value, field) {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new Error(`${field} must be a non-negative safe integer`)
  }
  return value
}

function configuredString(value, fallback, field) {
  const resolved = value ?? fallback
  if (typeof resolved !== 'string' || resolved.trim().length === 0) {
    throw new Error(`${field} must be a non-empty string`)
  }
  return resolved
}

function redactSensitiveText(value, secrets) {
  let redacted = typeof value === 'string' ? value : String(value ?? '')
  for (const secret of secrets) {
    if (typeof secret === 'string' && secret.length > 0) {
      redacted = redacted.split(secret).join(REDACTED)
    }
  }
  return redacted
}

/** Resolve every deployment choice once, before a tool definition closes over it. */
export function resolveConfig(config = {}) {
  if (config === null || typeof config !== 'object' || Array.isArray(config)) {
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
    maxProductionCost: config.maxProductionCost ?? 2,
    maxEvaluationCost: config.maxEvaluationCost ?? 1,
    billingUnit: configuredString(config.billingUnit, 'USD', 'billingUnit').toUpperCase(),
    maxRetries: config.maxRetries ?? 0,
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
    timeoutMs: config.timeoutMs ?? DEFAULT_TIMEOUT_MS,
    processGraceMs: config.processGraceMs ?? 5_000,
    outputCaptureBytes: config.outputCaptureBytes ?? DEFAULT_OUTPUT_CAPTURE_BYTES,
    maxEvidenceBytes: config.maxEvidenceBytes ?? DEFAULT_EVIDENCE_BYTES,
  }
  if (typeof resolved.allowPaidRuns !== 'boolean') {
    throw new Error('allowPaidRuns must be a boolean')
  }
  if (!['USD', 'AFP'].includes(resolved.billingUnit)) {
    throw new Error('billingUnit must be USD or AFP')
  }
  positiveFinite(resolved.maxProductionCost, 'maxProductionCost')
  positiveFinite(resolved.maxEvaluationCost, 'maxEvaluationCost')
  nonNegativeInteger(resolved.maxRetries, 'maxRetries')
  positiveInteger(resolved.timeoutMs, 'timeoutMs')
  positiveInteger(resolved.processGraceMs, 'processGraceMs')
  positiveInteger(resolved.outputCaptureBytes, 'outputCaptureBytes')
  positiveInteger(resolved.maxEvidenceBytes, 'maxEvidenceBytes')
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(resolved.credentialEnv)) {
    throw new Error('credentialEnv must be a POSIX environment variable name')
  }
  return Object.freeze(resolved)
}

async function readExecutionManifest(path) {
  const raw = JSON.parse(await readFile(path, 'utf8'))
  if (raw?.schema_version !== 'v0.2' || !Array.isArray(raw.models)) {
    throw new Error('plugin requires a v0.2 model manifest')
  }
  const defaults = raw.defaults ?? {}
  const models = raw.models.map(model => ({ ...defaults, ...model }))
  if (models.length === 0) throw new Error('model manifest has no models')
  const billingUnits = new Set(models.map(model => String(model.billing_unit).toUpperCase()))
  const wireApis = new Set(models.map(model => String(model.wire_api)))
  const credentialEnvs = new Set(models.map(model => String(model.api_key_env)))
  if (billingUnits.size !== 1 || wireApis.size !== 1 || credentialEnvs.size !== 1) {
    throw new Error('plugin requires one billing unit, wire API, and credential reference')
  }
  const wireApi = [...wireApis][0]
  if (!['chat-completions', 'dsh-llm'].includes(wireApi)) {
    throw new Error(`unsupported manifest wire API: ${wireApi}`)
  }
  const routes = models.map(model => ({
    provider: String(model.provider),
    model: String(model.api_model),
  }))
  return {
    billingUnit: [...billingUnits][0],
    wireApi,
    credentialEnv: [...credentialEnvs][0],
    routes,
  }
}

/** Dependency-free Standard Schema keeps linked checkout bundles self-contained. */
export const Config = {
  '~standard': {
    version: 1,
    vendor: 'dsh-refractrouter-validation',
    validate(value) {
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

function resolveRequest(args, config) {
  if (args === null || typeof args !== 'object' || Array.isArray(args)) {
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
  if (!['dry-run', 'pilot', 'final'].includes(args.phase)) {
    throw new Error('phase must be dry-run, pilot, or final')
  }
  if (args.executePaidRun !== undefined && typeof args.executePaidRun !== 'boolean') {
    throw new Error('executePaidRun must be a boolean')
  }
  const repeats = args.repeats ?? 1
  if (!Number.isInteger(repeats) || repeats <= 0) {
    throw new Error('repeats must be a positive integer')
  }
  const paid = args.executePaidRun ?? false
  if (!paid) {
    if (args.maxProductionCost !== undefined || args.maxEvaluationCost !== undefined) {
      throw new Error('cost limits are valid only when executePaidRun is true')
    }
    return { phase: args.phase, repeats, paid: false }
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
    phase: args.phase,
    repeats,
    paid: true,
    productionLimit,
    evaluationLimit,
  }
}

function workspaceOf(exec) {
  const cwd = exec.agent?.session?.header?.cwd
  return resolve(typeof cwd === 'string' && cwd.length > 0 ? cwd : process.cwd())
}

function artifactHashes(evidence, secrets) {
  if (evidence === null || typeof evidence !== 'object') return []
  const artifacts = evidence.artifacts
  if (artifacts === null || typeof artifacts !== 'object') return []
  return Object.entries(artifacts)
    .filter(([, sha256]) => typeof sha256 === 'string')
    .map(([artifact, sha256]) => ({
      artifact: redactSensitiveText(artifact, secrets),
      sha256,
    }))
}

function summarizeEvidence(evidence, fallback, secrets) {
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
    billingUnit: String(preflight?.billing_unit ?? fallback.billingUnit),
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
    ...fallback.stdoutTail.length === 0 ? {} : { stdoutTail: fallback.stdoutTail },
    ...fallback.stderrTail.length === 0 ? {} : { stderrTail: fallback.stderrTail },
  }
}

async function readEvidence(path, maxBytes) {
  let info
  try {
    info = await stat(path)
  } catch (error) {
    if (error?.code === 'ENOENT') return undefined
    throw error
  }
  if (!info.isFile()) throw new Error(`evidence path is not a file: ${path}`)
  if (info.size > maxBytes) {
    throw new Error(`evidence exceeds configured ${String(maxBytes)} byte limit`)
  }
  return JSON.parse(await readFile(path, 'utf8'))
}

function capturedTail(captured, secrets) {
  if (captured?.lossy === true) return '[captured output omitted after truncation]'
  return redactSensitiveText(captured?.text ?? '', secrets)
}

function bridgeFailureType(code) {
  const normalized = String(code ?? '').toUpperCase()
  if (normalized.includes('AUTH') || normalized.includes('CREDENTIAL')) return 'authentication'
  if (normalized.includes('RATE_LIMIT')) return 'rate-limit'
  if (normalized.includes('QUOTA')) return 'quota-exhausted'
  if (normalized.includes('TIMEOUT')) return 'timeout'
  if (normalized.includes('ABORT')) return 'aborted'
  if (normalized.includes('CONTEXT')) return 'context-window-exceeded'
  return 'provider-error'
}

function replayRequestId(replayState) {
  const response = replayState?.response
  if (response === null || typeof response !== 'object') return undefined
  const value = response.requestId ?? response.responseId ?? response.id
  return typeof value === 'string' && value.length > 0 ? value : undefined
}

export async function callDshLlm(ctx, request, signal) {
  const id = String(request?.id ?? '')
  const base = { protocol: DSH_BRIDGE_PROTOCOL, type: 'response', id }
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
    const system = []
    const messages = []
    for (const message of request.messages) {
      if (message === null || typeof message !== 'object' || typeof message.content !== 'string') {
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
    const options = {
      provider: request.provider,
      model: request.model,
      messages,
      system: system.length === 0 ? undefined : system.join('\n\n'),
      temperature: Number(request.temperature ?? 0),
      maxTokens: Number(request.max_tokens),
      signal,
    }
    const reasoningEffort = request.request_options?.reasoning_effort
    if (typeof reasoningEffort === 'string' && reasoningEffort.length > 0) {
      options.reasoningEffort = reasoningEffort
    }
    let content = ''
    let usage = {}
    let finish
    for await (const chunk of ctx.llm.stream(options)) {
      if (chunk.type === 'text-delta') content += chunk.text
      if (chunk.type === 'usage') usage = chunk.usage ?? {}
      if (chunk.type === 'finish') finish = chunk
    }
    if (finish === undefined) throw new Error('DSH LLM stream ended without finish')
    if (finish.reason?.kind === 'error' || finish.reason?.kind === 'aborted') {
      const failure = finish.reason.failure ?? {}
      return {
        ...base,
        ok: false,
        failure_type: bridgeFailureType(failure.code),
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
    return {
      ...base,
      ok: false,
      failure_type: signal?.aborted ? 'aborted' : 'provider-error',
      message: String(error instanceof Error ? error.message : error).slice(0, 300),
    }
  }
}

function tailCapture(maxBytes) {
  let buffer = Buffer.alloc(0)
  let lossy = false
  return {
    append(text) {
      buffer = Buffer.concat([buffer, Buffer.from(text)])
      if (buffer.length > maxBytes) {
        buffer = buffer.subarray(buffer.length - maxBytes)
        lossy = true
      }
    },
    read() { return { text: buffer.toString('utf8'), lossy } },
  }
}

async function writeLine(stream, value) {
  const line = `${JSON.stringify(value)}\n`
  if (stream.write(line)) return
  await new Promise(resolveDrain => stream.once('drain', resolveDrain))
}

async function pumpDshBridge(ctx, handle, signal, routes, maxBytes) {
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
      let request
      try {
        request = JSON.parse(line)
      } catch {
        capture.append(`${line}\n`)
        continue
      }
      if (request?.protocol !== DSH_BRIDGE_PROTOCOL || request?.type !== 'request') {
        capture.append(`${line}\n`)
        continue
      }
      const route = `${String(request.provider)}\u0000${String(request.model)}`
      const response = allowed.has(route)
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

async function dshProviderIssues(ctx, routes) {
  const providers = new Set(ctx.llm.listProviders().map(provider => provider.id))
  const issues = []
  for (const route of routes) {
    if (!providers.has(route.provider)) {
      issues.push(`missing-llm-provider:${route.provider}`)
      continue
    }
    try {
      await ctx.llm.resolveModelInfo(route.provider, route.model)
    } catch {
      issues.push(`unresolved-llm-model:${route.provider}/${route.model}`)
    }
  }
  return [...new Set(issues)]
}

async function executeValidation(ctx, args, exec, config) {
  const request = resolveRequest(args, config)
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
    throw new Error(`paid validation requires resolved DSH models: ${providerIssues.join(', ')}`)
  }
  const runRoot = await mkdtemp(join(tmpdir(), 'refractrouter-dsh-plugin-'))
  const outputDir = join(runRoot, 'output')
  const evidencePath = join(runRoot, 'evidence.json')
  const reference = config.credentialEnv
  let credentialInfo
  try {
    credentialInfo = await ctx.credentials.describe(reference)
  } catch {
    throw new Error(`failed to describe credential ${reference}`)
  }
  const credentialConfigured = credentialInfo.configured === true
  const env = { UV_CACHE_DIR: config.uvCacheDir }
  const secrets = []
  if (request.paid) {
    if (!credentialConfigured) {
      throw new Error(`paid validation requires configured credential ${config.credentialEnv}`)
    }
    if (manifest.wireApi === 'dsh-llm') {
      env.REFRACTROUTER_DSH_BRIDGE = 'stdio'
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
    resolve(workspace, config.runnerPath),
    '--dataset',
    resolve(workspace, config.datasetPath),
    '--manifest',
    manifestPath,
    '--phase',
    request.phase,
    '--repeats',
    String(request.repeats),
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
  const timeoutSignal = AbortSignal.timeout(config.timeoutMs)
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
  if (timedOut) fallbackIssues.push('plugin-runner-timeout')
  if (aborted) fallbackIssues.push('plugin-runner-aborted')
  if (stdout?.lossy === true) fallbackIssues.push('plugin-runner-stdout-truncated')
  if (stderr?.lossy === true) fallbackIssues.push('plugin-runner-stderr-truncated')
  const fallback = {
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

const OUTPUT_SCHEMA = {
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
    phase: { type: 'string', enum: ['dry-run', 'pilot', 'final'] },
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
    stdoutTail: { type: 'string' },
    stderrTail: { type: 'string' },
  },
}

export function apply(ctx, rawConfig = {}) {
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
          enum: ['dry-run', 'pilot', 'final'],
          description: 'Benchmark phase whose fixed task split and call plan should be validated.',
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
}
