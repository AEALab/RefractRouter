import { mkdtemp, readFile, stat } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'

export const name = 'refractrouter-validation'
export const inject = ['tools', 'subprocess', 'sandbox', 'sandboxPolicy', 'credentials']

const DEFAULT_TIMEOUT_MS = 7_200_000
const DEFAULT_OUTPUT_CAPTURE_BYTES = 262_144
const DEFAULT_EVIDENCE_BYTES = 2_097_152

function positiveFinite(value, field) {
  if (!Number.isFinite(value) || value <= 0) {
    throw new Error(`${field} must be a positive finite number`)
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

/** Resolve every deployment choice once, before a tool definition closes over it. */
export function resolveConfig(config = {}) {
  if (config === null || typeof config !== 'object' || Array.isArray(config)) {
    throw new Error('config must be an object')
  }
  const allowed = new Set([
    'allowPaidRuns',
    'maxProductionCostUsd',
    'maxEvaluationCostUsd',
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
    maxProductionCostUsd: config.maxProductionCostUsd ?? 2,
    maxEvaluationCostUsd: config.maxEvaluationCostUsd ?? 1,
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
  positiveFinite(resolved.maxProductionCostUsd, 'maxProductionCostUsd')
  positiveFinite(resolved.maxEvaluationCostUsd, 'maxEvaluationCostUsd')
  positiveFinite(resolved.timeoutMs, 'timeoutMs')
  positiveFinite(resolved.processGraceMs, 'processGraceMs')
  positiveFinite(resolved.outputCaptureBytes, 'outputCaptureBytes')
  positiveFinite(resolved.maxEvidenceBytes, 'maxEvidenceBytes')
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(resolved.credentialEnv)) {
    throw new Error('credentialEnv must be a POSIX environment variable name')
  }
  return Object.freeze(resolved)
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
    'maxProductionCostUsd',
    'maxEvaluationCostUsd',
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
    if (args.maxProductionCostUsd !== undefined || args.maxEvaluationCostUsd !== undefined) {
      throw new Error('cost limits are valid only when executePaidRun is true')
    }
    return { phase: args.phase, repeats, paid: false }
  }
  if (!config.allowPaidRuns) {
    throw new Error('paid validation is disabled by plugin config (allowPaidRuns: false)')
  }
  const productionLimit = positiveFinite(
    args.maxProductionCostUsd,
    'maxProductionCostUsd',
  )
  const evaluationLimit = positiveFinite(
    args.maxEvaluationCostUsd,
    'maxEvaluationCostUsd',
  )
  if (productionLimit > config.maxProductionCostUsd) {
    throw new Error(
      `maxProductionCostUsd exceeds configured ceiling ${String(config.maxProductionCostUsd)}`,
    )
  }
  if (evaluationLimit > config.maxEvaluationCostUsd) {
    throw new Error(
      `maxEvaluationCostUsd exceeds configured ceiling ${String(config.maxEvaluationCostUsd)}`,
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

function artifactHashes(evidence) {
  if (evidence === null || typeof evidence !== 'object') return []
  const artifacts = evidence.artifacts
  if (artifacts === null || typeof artifacts !== 'object') return []
  return Object.entries(artifacts)
    .filter(([, sha256]) => typeof sha256 === 'string')
    .map(([artifact, sha256]) => ({ artifact, sha256 }))
}

function summarizeEvidence(evidence, fallback) {
  const preflight = evidence?.preflight
  const plan = preflight?.call_plan
  const costs = preflight?.cost_estimates
  const inputs = evidence?.inputs
  const evidenceIssues = Array.isArray(evidence?.issues)
    ? evidence.issues.filter(issue => typeof issue === 'string')
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
          costEstimateUsd: {
            production: costs.production_upper_estimate_usd,
            evaluation: costs.evaluation_upper_estimate_usd,
            total: costs.total_upper_estimate_usd,
          },
        },
    inputHashes: {
      dataset: inputs?.dataset?.sha256 ?? '',
      manifest: inputs?.model_manifest?.sha256 ?? '',
      corpus: inputs?.corpus?.sha256 ?? '',
      code: inputs?.code?.sha256 ?? '',
    },
    artifactHashes: artifactHashes(evidence),
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

async function executeValidation(ctx, args, exec, config) {
  const request = resolveRequest(args, config)
  const workspace = workspaceOf(exec)
  const runRoot = await mkdtemp(join(tmpdir(), 'refractrouter-dsh-plugin-'))
  const outputDir = join(runRoot, 'output')
  const evidencePath = join(runRoot, 'evidence.json')
  const reference = config.credentialEnv
  const credentialInfo = await ctx.credentials.describe(reference)
  const credentialConfigured = credentialInfo.configured === true
  const env = { UV_CACHE_DIR: config.uvCacheDir }
  if (request.paid) {
    const credential = await ctx.credentials.resolve(reference)
    if (credential === undefined) {
      throw new Error(`paid validation requires configured credential ${config.credentialEnv}`)
    }
    env[config.credentialEnv] = credential.value
  }
  exec.signal.throwIfAborted()
  const executable = await ctx.subprocess.resolveExecutable(
    config.uvExecutable,
    env,
    exec.signal,
  )
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
    resolve(workspace, config.manifestPath),
    '--phase',
    request.phase,
    '--repeats',
    String(request.repeats),
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
      '--max-production-cost-usd',
      String(request.productionLimit),
      '--max-evaluation-cost-usd',
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
  const handle = ctx.subprocess.spawn({
    argv: confined?.argv ?? argv,
    cwd: workspace,
    env,
    stdio: {
      stdin: 'ignore',
      stdout: { maxBytes: config.outputCaptureBytes },
      stderr: { maxBytes: config.outputCaptureBytes },
    },
    graceMs: config.processGraceMs,
    signal,
  })
  const outcome = await handle.done
  await handle.waitForExit()
  const stdout = handle.collected.stdout?.readFrom(0)
  const stderr = handle.collected.stderr?.readFrom(0)
  const stdoutTail = stdout?.text ?? ''
  const stderrTail = stderr?.text ?? ''
  const timedOut = timeoutSignal.aborted && !exec.signal.aborted
  const aborted = exec.signal.aborted
  let evidence
  const fallbackIssues = []
  try {
    evidence = await readEvidence(evidencePath, config.maxEvidenceBytes)
  } catch (error) {
    fallbackIssues.push(`invalid-evidence:${error instanceof Error ? error.message : String(error)}`)
  }
  if (outcome.exitCode !== 0) fallbackIssues.push(`plugin-runner-exit:${String(outcome.exitCode)}`)
  if (evidence === undefined) fallbackIssues.push('missing-evidence')
  if (timedOut) fallbackIssues.push('plugin-runner-timeout')
  if (aborted) fallbackIssues.push('plugin-runner-aborted')
  const fallback = {
    phase: request.phase,
    exitCode: outcome.exitCode,
    signal: outcome.signal,
    timedOut,
    aborted,
    evidencePath,
    outputDir,
    credentialConfigured,
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
      sandboxMode: policy.mode,
      ...confined === undefined ? {} : { sandboxEnforcement: confined.enforcement },
      issues: fallbackIssues,
      inputHashes: { dataset: '', manifest: '', corpus: '', code: '' },
      artifactHashes: [],
      ...stdoutTail.length === 0 ? {} : { stdoutTail },
      ...stderrTail.length === 0 ? {} : { stderrTail },
    }
  }
  return summarizeEvidence(evidence, fallback)
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
    costEstimateUsd: {
      type: 'object',
      additionalProperties: false,
      required: ['production', 'evaluation', 'total'],
      properties: {
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
          type: 'number',
          description: 'Positive integer repeat count; defaults to 1.',
        },
        executePaidRun: {
          type: 'boolean',
          description: 'Actually invoke candidate and judge models. Defaults to false.',
        },
        maxProductionCostUsd: {
          type: 'number',
          description: 'Required paid-run production ceiling; rejected above the bundle ceiling.',
        },
        maxEvaluationCostUsd: {
          type: 'number',
          description: 'Required paid-run judge ceiling; rejected above the bundle ceiling.',
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
          issues: value.issues,
          callPlan: value.callPlan,
          costEstimateUsd: value.costEstimateUsd,
          evidencePath: value.evidencePath,
        }),
      }],
    },
    execute: (args, exec) => executeValidation(ctx, args, exec, config),
  })
}
