import type { Readable } from 'node:stream'
import type {
  BillingUnit, DshContext, LlmOptions, PluginConfig, ProcessOutcome, SandboxEnforcement,
  SandboxMode, SpawnSpec, StreamChunk, ValidationTool,
} from '../dist/contracts.js'

import assert from 'node:assert/strict'
import { execFile, spawn as spawnChild } from 'node:child_process'
import { copyFile, mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import test from 'node:test'
import { promisify } from 'node:util'

const execFileAsync = promisify(execFile)

import { apply, callDshLlm, Config, resolveConfig } from '../dist/index.js'

const ROOT = resolve(import.meta.dirname, '../../../..')

function evidence({
  mode = 'preflight',
  issues = [],
  artifact = 'preflight.json',
  billingUnit = 'USD',
}: { mode?: string; issues?: string[]; artifact?: string; billingUnit?: BillingUnit } = {}) {
  return {
    status: issues.length === 0 ? 'pass' : 'fail',
    mode,
    issues,
    preflight: {
      billing_unit: billingUnit,
      call_plan: {
        training_model_calls: 0,
        production_model_calls: 56,
        judge_model_calls: 5,
        total_model_calls: 61,
      },
      cost_estimates: {
        billing_unit: billingUnit,
        production_upper_estimate: 1.5,
        evaluation_upper_estimate: 0.45,
        total_upper_estimate: 1.95,
      },
    },
    inputs: {
      dataset: { sha256: 'dataset-sha' },
      model_manifest: { sha256: 'manifest-sha' },
      corpus: { sha256: 'corpus-sha' },
      code: { sha256: 'code-sha' },
    },
    artifacts: { [artifact]: 'artifact-sha' },
  }
}


interface FixtureOptions {
  config?: Partial<PluginConfig>
  credential?: string
  credentialConfigured?: boolean
  mode?: SandboxMode
  enforcement?: SandboxEnforcement
  resultEvidence?: ReturnType<typeof evidence>
  evidenceText?: string
  stdout?: string
  stderr?: string
  stdoutLossy?: boolean
  stderrLossy?: boolean
  outcome?: ProcessOutcome
  settleOnAbort?: boolean
  spawnError?: Error
  providers?: string[]
  unresolvedModels?: string[]
  providerRetryPolicy?: { mode: string; maxRetries: number }
}

function fakeContext({
  config = {},
  credential,
  credentialConfigured = credential !== undefined,
  mode = 'workspace-write',
  enforcement = 'full',
  resultEvidence = evidence(),
  evidenceText,
  stdout = '',
  stderr = '',
  stdoutLossy = false,
  stderrLossy = false,
  outcome = { exitCode: 0, signal: null },
  settleOnAbort = false,
  spawnError,
  providers = ['deepseek-official'],
  unresolvedModels = [],
  providerRetryPolicy = { mode: 'normal', maxRetries: 0 },
}: FixtureOptions = {}) {
  const calls = {
    describe: 0,
    resolve: 0,
    confine: 0,
    spawn: 0,
    spawnSpec: undefined as SpawnSpec | undefined,
  }
  let tool: ValidationTool | undefined
  const ctx: DshContext = {
    tools: {
      register(spec) {
        tool = spec
      },
    },
    credentials: {
      async describe() {
        calls.describe += 1
        return { configured: credentialConfigured }
      },
      async resolve() {
        calls.resolve += 1
        return credential === undefined ? undefined : { value: credential, source: 'test' }
      },
    },
    llm: {
      stream() { throw new Error('unexpected LLM call') },
      listProviders() { return providers.map(id => ({ id, name: id })) },
      providerRetryPolicy() { return providerRetryPolicy },
      async resolveModelInfo(provider, model) {
        if (unresolvedModels.includes(`${provider}/${model}`)) throw new Error('unresolved')
        return { id: model, name: model }
      },
    },
    sandboxPolicy: {
      resolve() {
        return { mode, workspaceRoot: ROOT }
      },
    },
    sandbox: {
      confine(argv) {
        calls.confine += 1
        return { argv, enforcement }
      },
    },
    subprocess: {
      async resolveExecutable(command) {
        return command
      },
      spawn(spec) {
        calls.spawn += 1
        calls.spawnSpec = spec
        if (spawnError !== undefined) throw spawnError
        const evidenceIndex = spec.argv.indexOf('--evidence')
        assert.notEqual(evidenceIndex, -1)
        const path = spec.argv[evidenceIndex + 1]
        const written = writeFile(
          path,
          evidenceText ?? JSON.stringify(resultEvidence),
          'utf8',
        )
        const done = settleOnAbort
          ? new Promise<ProcessOutcome>(resolveOutcome => {
            const keepAlive = setTimeout(() => {}, 1_000)
            spec.signal.addEventListener(
              'abort',
              () => {
                clearTimeout(keepAlive)
                resolveOutcome({ exitCode: null, signal: 'SIGTERM' })
              },
              { once: true },
            )
          })
          : written.then(() => outcome)
        return {
          done,
          async waitForExit() {
            await done
          },
          collected: {
            stdout: { readFrom: () => ({ text: stdout, lossy: stdoutLossy }) },
            stderr: { readFrom: () => ({ text: stderr, lossy: stderrLossy }) },
          },
        }
      },
    },
  }
  apply(ctx, config)
  return { calls, get tool() { assert.ok(tool); return tool } }
}

function execution(signal = new AbortController().signal) {
  return {
    signal,
    agent: { session: { header: { cwd: ROOT } } },
  }
}

test('preflight registers a discoverable tool and uses DSH service seams', async () => {
  const fixture = fakeContext()
  assert.equal(fixture.tool.name, 'refractrouter_validate')
  assert.deepEqual(fixture.tool.parameters.required, ['phase'])

  const result = await fixture.tool.execute(
    { phase: 'dry-run', executePaidRun: false },
    execution(),
  )

  assert.equal(result.status, 'pass')
  assert.equal(result.mode, 'preflight')
  assert.equal(result.sandboxMode, 'workspace-write')
  assert.equal(result.sandboxEnforcement, 'full')
  assert.equal(fixture.calls.describe, 1)
  assert.equal(fixture.calls.resolve, 0)
  assert.equal(fixture.calls.confine, 1)
  assert.equal(fixture.calls.spawn, 1)
  assert.equal(fixture.calls.spawnSpec!.env.OPENAI_API_KEY, undefined)
  assert.equal((fixture.calls.spawnSpec!.stdio.stdout as { maxBytes: number }).maxBytes, 262_144)
  assert.equal(fixture.calls.spawnSpec!.stdio.stderr.maxBytes, 262_144)
  assert.equal(fixture.calls.spawnSpec!.graceMs, 5_000)
  const retryIndex = fixture.calls.spawnSpec!.argv.indexOf('--max-retries')
  assert.notEqual(retryIndex, -1)
  assert.equal(fixture.calls.spawnSpec!.argv[retryIndex + 1], '0')
  assert.equal(fixture.calls.spawnSpec!.argv.includes('--execute-paid-run'), false)
})

test('danger-full-access bypasses sandbox wrapping', async () => {
  const fixture = fakeContext({ mode: 'danger-full-access' })
  const result = await fixture.tool.execute({ phase: 'final' }, execution())

  assert.equal(result.status, 'pass')
  assert.equal(result.sandboxMode, 'danger-full-access')
  assert.equal(result.sandboxEnforcement, undefined)
  assert.equal(fixture.calls.confine, 0)
})

test('Agent Plan uses only the dedicated direct endpoint and DSH-resolved credential', async () => {
  const config: Partial<PluginConfig> = {
    billingUnit: 'AFP',
    maxProductionCost: 200,
    maxEvaluationCost: 60,
    manifestPath: 'data/model-manifests/volcengine-agent-plan.json',
    credentialEnv: 'CODEX_ARK_API_KEY',
  }
  const ready = fakeContext({
    config,
    credentialConfigured: true,
    providers: [],
    resultEvidence: evidence({ billingUnit: 'AFP' }),
  })
  const result = await ready.tool.execute({ phase: 'dry-run' }, execution())

  assert.equal(result.status, 'pass')
  assert.equal(result.billingUnit, 'AFP')
  assert.equal(result.modelProviderConfigured, true)
  assert.equal(ready.calls.resolve, 0)

  const paid = fakeContext({
    config: { ...config, allowPaidRuns: true },
    credential: 'test-secret',
    providers: [],
    resultEvidence: evidence({ mode: 'paid', billingUnit: 'AFP' }),
  })
  const paidResult = await paid.tool.execute({
    phase: 'dry-run',
    executePaidRun: true,
    maxProductionCost: 200,
    maxEvaluationCost: 60,
  }, execution())
  assert.equal(paidResult.status, 'pass')
  assert.equal(paid.calls.resolve, 1)
  assert.equal(paid.calls.spawnSpec!.env.CODEX_ARK_API_KEY, 'test-secret')
  assert.equal(paid.calls.spawnSpec!.env.REFRACTROUTER_DSH_BRIDGE, undefined)
  assert.match(
    paid.calls.spawnSpec!.env.REFRACTROUTER_MODEL_PROGRESS,
    /\/output\/model-progress\.ndjson$/,
  )
  assert.equal(paid.calls.spawnSpec!.stdio.stdin, 'ignore')
  assert.equal((paid.calls.spawnSpec!.stdio.stdout as { maxBytes: number }).maxBytes, 262_144)
})

test('AFP execution rejects the ordinary Ark pay-as-you-go endpoint', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'refractrouter-afp-manifest-'))
  const manifestPath = join(directory, 'manifest.json')
  await writeFile(manifestPath, JSON.stringify({
    schema_version: 'v0.2',
    defaults: {
      provider: 'ark-plan',
      billing_unit: 'AFP',
      wire_api: 'chat-completions',
      base_url: 'https://ark.cn-beijing.volces.com/api/v3',
      api_key_env: 'CODEX_ARK_API_KEY',
    },
    models: [{ model_id: 'cheap', api_model: 'deepseek-v4-flash' }],
  }), 'utf8')

  try {
    const fixture = fakeContext({
      config: {
        billingUnit: 'AFP',
        manifestPath,
        credentialEnv: 'CODEX_ARK_API_KEY',
      },
      credentialConfigured: true,
      providers: [],
      resultEvidence: evidence({ billingUnit: 'AFP' }),
    })
    await assert.rejects(
      fixture.tool.execute({ phase: 'dry-run' }, execution()),
      /AFP validation requires ark-plan at https:\/\/ark\.cn-beijing\.volces\.com\/api\/plan\/v3/,
    )
    assert.equal(fixture.calls.spawn, 0)
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

test('contract replay is bounded and retains paid deployment controls', async () => {
  const fixture = fakeContext()
  await fixture.tool.execute({ phase: 'contract-replay' }, execution())
  assert.ok(fixture.calls.spawnSpec!.argv.includes('contract-replay'))
  assert.equal(fixture.calls.resolve, 0)
  await assert.rejects(
    fixture.tool.execute({ phase: 'contract-replay', repeats: 4 }, execution()),
    /contract-replay requires/,
  )
  await assert.rejects(
    fixture.tool.execute({ phase: 'contract-replay', executePaidRun: true,
      maxProductionCost: 2, maxEvaluationCost: 1 }, execution()),
    /paid validation is disabled/,
  )
  const retrying = fakeContext({ config: { maxRetries: 1 } })
  await assert.rejects(
    retrying.tool.execute({ phase: 'contract-replay' }, execution()),
    /configured maxRetries = 0/,
  )
  assert.equal(retrying.calls.spawn, 0)
})

test('paid execution requires deployment enablement, two budgets, and a credential', async () => {
  const disabled = fakeContext({ credential: 'test-secret' })
  await assert.rejects(
    disabled.tool.execute({
      phase: 'dry-run',
      executePaidRun: true,
      maxProductionCost: 2,
      maxEvaluationCost: 1,
    }, execution()),
    /paid validation is disabled/,
  )
  assert.equal(disabled.calls.describe, 0)
  assert.equal(disabled.calls.resolve, 0)

  const enabled = fakeContext({ config: { allowPaidRuns: true } })
  await assert.rejects(
    enabled.tool.execute({ phase: 'dry-run', executePaidRun: true }, execution()),
    /maxProductionCost must be a positive finite number/,
  )
  await assert.rejects(
    enabled.tool.execute({
      phase: 'dry-run',
      executePaidRun: true,
      maxProductionCost: 2,
      maxEvaluationCost: 1,
    }, execution()),
    /requires configured credential OPENAI_API_KEY/,
  )
  assert.equal(enabled.calls.resolve, 0)
})

test('paid diagnostics and evidence issues redact the resolved credential', async () => {
  const secret = 'sk-test-never-return-this-value'
  const fixture = fakeContext({
    config: { allowPaidRuns: true },
    credential: secret,
    resultEvidence: evidence({
      mode: 'paid',
      issues: [`provider rejected ${secret}`],
      artifact: `artifact-${secret}.json`,
    }),
    stdout: `stdout contained ${secret}`,
    stderr: `stderr contained ${secret}`,
  })
  const result = await fixture.tool.execute({
    phase: 'dry-run',
    executePaidRun: true,
    maxProductionCost: 2,
    maxEvaluationCost: 1,
  }, execution())

  assert.equal(fixture.calls.resolve, 1)
  assert.equal(fixture.calls.spawnSpec!.env.OPENAI_API_KEY, secret)
  assert.equal(fixture.calls.spawnSpec!.argv.includes('--execute-paid-run'), true)
  assert.doesNotMatch(JSON.stringify(result), new RegExp(secret))
  assert.match(JSON.stringify(result), /\[REDACTED\]/)
})

test('paid subprocess failures redact the resolved credential', async () => {
  const secret = 'sk-test-spawn-failure-secret'
  const fixture = fakeContext({
    config: { allowPaidRuns: true },
    credential: secret,
    spawnError: new Error(`spawn failed with ${secret}`),
  })

  await assert.rejects(
    fixture.tool.execute({
      phase: 'dry-run',
      executePaidRun: true,
      maxProductionCost: 2,
      maxEvaluationCost: 1,
    }, execution()),
    (error: unknown) => {
      assert.ok(error instanceof Error)
      assert.doesNotMatch(error.message, new RegExp(secret))
      assert.match(error.message, /\[REDACTED\]/)
      return true
    },
  )
})

test('output truncation and oversized evidence fail closed', async () => {
  const truncated = fakeContext({
    stdout: 'partial-secret-fragment',
    stderr: 'partial-secret-fragment',
    stdoutLossy: true,
    stderrLossy: true,
  })
  const truncatedResult = await truncated.tool.execute({ phase: 'pilot' }, execution())
  assert.equal(truncatedResult.status, 'fail')
  assert.ok(truncatedResult.issues.includes('plugin-runner-stdout-truncated'))
  assert.ok(truncatedResult.issues.includes('plugin-runner-stderr-truncated'))
  assert.equal(truncatedResult.stdoutTail, '[captured output omitted after truncation]')
  assert.equal(truncatedResult.stderrTail, '[captured output omitted after truncation]')

  const oversized = fakeContext({
    config: { maxEvidenceBytes: 64 },
    evidenceText: 'x'.repeat(65),
  })
  const oversizedResult = await oversized.tool.execute({ phase: 'pilot' }, execution())
  assert.equal(oversizedResult.status, 'fail')
  assert.ok(oversizedResult.issues.some(issue => issue.startsWith('invalid-evidence:')))
  assert.ok(oversizedResult.issues.includes('missing-evidence'))
})

test('timeout returns structured failure and caller abort stops before spawn', async () => {
  const timed = fakeContext({ config: { timeoutMs: 5 }, settleOnAbort: true })
  const timedResult = await timed.tool.execute({ phase: 'final' }, execution())
  assert.equal(timedResult.status, 'fail')
  assert.equal(timedResult.timedOut, true)
  assert.ok(timedResult.issues.includes('plugin-runner-timeout'))

  const aborted = fakeContext()
  const controller = new AbortController()
  controller.abort()
  await assert.rejects(
    aborted.tool.execute({ phase: 'final' }, execution(controller.signal)),
    (error: unknown) => error instanceof Error && error.name === 'AbortError',
  )
  assert.equal(aborted.calls.spawn, 0)
})

function boundedCollector(stream: Readable, maxBytes: number) {
  let buffered = Buffer.alloc(0)
  let totalBytes = 0
  stream.on('data', chunk => {
    const bytes = Buffer.from(chunk)
    totalBytes += bytes.length
    buffered = Buffer.concat([buffered, bytes])
    if (buffered.length > maxBytes) buffered = buffered.subarray(buffered.length - maxBytes)
  })
  return {
    readFrom() {
      return { text: buffered.toString('utf8'), lossy: totalBytes > buffered.length }
    },
  }
}

function localProcessContext() {
  let tool: ValidationTool | undefined
  const ctx: DshContext = {
    tools: { register(spec) { tool = spec } },
    credentials: {
      async describe() { return { configured: false } },
      async resolve() { throw new Error('preflight must not resolve credentials') },
    },
    llm: {
      stream() { throw new Error('unexpected LLM call') },
      listProviders() { return [] },
      providerRetryPolicy() { throw new Error('unexpected retry policy lookup') },
      async resolveModelInfo() { throw new Error('unexpected model lookup') },
    },
    sandboxPolicy: {
      resolve() { return { mode: 'danger-full-access', workspaceRoot: ROOT } },
    },
    sandbox: {
      confine() { throw new Error('danger-full-access must not invoke sandbox.confine') },
    },
    subprocess: {
      async resolveExecutable(command) { return command },
      spawn(spec) {
        const childEnv: Record<string, string> = {}
        for (const [key, value] of Object.entries(process.env)) {
          if (value !== undefined && !/KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL/i.test(key) && !key.startsWith('DSH_')) {
            childEnv[key] = value
          }
        }
        Object.assign(childEnv, spec.env)
        const child = spawnChild(spec.argv[0], spec.argv.slice(1), {
          cwd: spec.cwd,
          env: childEnv,
          stdio: ['ignore', 'pipe', 'pipe'],
        })
        assert.notEqual(spec.stdio.stdout, 'pipe')
        const stdout = boundedCollector(child.stdout, (spec.stdio.stdout as { maxBytes: number }).maxBytes)
        const stderr = boundedCollector(child.stderr, spec.stdio.stderr.maxBytes)
        const done = new Promise<ProcessOutcome>((resolveOutcome, reject) => {
          child.once('error', reject)
          child.once('close', (exitCode, signal) => resolveOutcome({ exitCode, signal }))
          spec.signal.addEventListener('abort', () => child.kill('SIGTERM'), { once: true })
        })
        return {
          done,
          async waitForExit() { await done },
          collected: { stdout, stderr },
        }
      },
    },
  }
  apply(ctx)
  return { get tool() { assert.ok(tool); return tool } }
}

test('the registered tool completes a real zero-cost Python preflight', async () => {
  const fixture = localProcessContext()
  const result = await fixture.tool.execute(
    { phase: 'dry-run', executePaidRun: false },
    execution(),
  )
  try {
    assert.equal(result.status, 'pass', JSON.stringify(result, null, 2))
    assert.equal(result.mode, 'preflight')
    assert.equal(result.billingUnit, 'USD')
    assert.equal(result.credentialConfigured, false)
    assert.equal(result.callPlan!.totalModelCalls, 82)
    assert.equal(result.costEstimate!.billingUnit, 'USD')
    assert.equal(result.costEstimate!.total, 11.86)
    assert.equal(result.artifactHashes.length, 1)
  } finally {
    await rm(dirname(result.evidencePath), { recursive: true, force: true })
  }
})

test('DSH LLM bridge preserves content, disjoint usage, finish reason, and request id', async () => {
  const ctx = {
    llm: {
      async *stream(options: LlmOptions): AsyncGenerator<StreamChunk> {
        assert.equal(options.provider, 'ark-plan')
        assert.equal(options.model, 'deepseek-v4-flash')
        assert.equal(options.system, 'Return JSON.')
        assert.equal(options.messages[0].content[0].text, 'test')
        yield { type: 'text-delta', index: 0, text: '{"ok":' }
        yield { type: 'text-delta', index: 0, text: 'true}' }
        yield {
          type: 'usage',
          usage: {
            inputTokens: 80,
            cacheReadTokens: 20,
            cacheWriteTokens: 5,
            outputTokens: 12,
            reasoningTokens: 3,
          },
        }
        yield {
          type: 'finish',
          reason: { kind: 'stop' },
          replayState: { response: { responseId: 'resp-ark-test' } },
        }
      },
    },
  }
  const response = await callDshLlm(ctx, {
    protocol: 'refractrouter-dsh-llm/v1',
    type: 'request',
    id: '1',
    provider: 'ark-plan',
    model: 'deepseek-v4-flash',
    messages: [
      { role: 'system', content: 'Return JSON.' },
      { role: 'user', content: 'test' },
    ],
    temperature: 0,
    max_tokens: 128,
    timeout_ms: 120_000,
    request_options: {},
  })

  assert.equal(response.ok, true)
  assert.equal(response.content, '{"ok":true}')
  assert.equal(response.usage.input_tokens, 105)
  assert.equal(response.usage.cached_input_tokens, 20)
  assert.equal(response.usage.reasoning_tokens, 3)
  assert.equal(response.finish_reason, 'stop')
  assert.equal(response.request_id, 'resp-ark-test')
})

test('DSH LLM bridge enforces the per-request hard timeout', async () => {
  const keepAlive = setTimeout(() => {}, 100)
  let returnCalled = false
  const ctx = {
    llm: {
      stream() {
        return {
          [Symbol.asyncIterator]() { return this },
          next() { return new Promise<IteratorResult<StreamChunk>>(() => {}) },
          async return() {
            returnCalled = true
            return { done: true as const, value: undefined }
          },
        }
      },
    },
  }
  try {
    const response = await callDshLlm(ctx, {
      protocol: 'refractrouter-dsh-llm/v1',
      type: 'request',
      id: 'timeout-test',
      provider: 'ark-plan',
      model: 'deepseek-v4-flash',
      messages: [{ role: 'user', content: 'test' }],
      temperature: 0,
      max_tokens: 128,
      timeout_ms: 5,
      request_options: {},
    })

    assert.equal(response.ok, false)
    assert.equal(response.failure_type, 'timeout')
    await new Promise(resolveWait => setImmediate(resolveWait))
    assert.equal(returnCalled, true)
  } finally {
    clearTimeout(keepAlive)
  }
})


test('config schema supplies safe defaults and rejects malformed host configuration', () => {
  const valid = Config['~standard'].validate({})
  assert.ok('value' in valid && valid.value)
  assert.equal(valid.value.allowPaidRuns, false)
  assert.equal(valid.value.maxRetries, 0)
  assert.ok(Object.isFrozen(valid.value))
  assert.equal(resolveConfig({ billingUnit: 'afp' }).billingUnit, 'AFP')
  for (const value of [
    { unexpected: true }, { timeoutMs: 1.5 }, { maxRetries: -1 },
    { allowPaidRuns: 'true' }, { maxProductionCost: NaN },
    { maxEvaluationCost: Infinity }, { maxProductionCost: true },
    { credentialEnv: 'INVALID-KEY' }, [], 'config',
  ]) {
    const invalid = Config['~standard'].validate(value)
    assert.ok('issues' in invalid && invalid.issues)
    assert.equal(invalid.issues.length, 1)
  }
})

test('malformed projected evidence fields fail as structured diagnostics', async () => {
  for (const value of [null, [], { status: 'pass', preflight: { call_plan: {
    training_model_calls: 0, production_model_calls: '56', judge_model_calls: 5, total_model_calls: 61,
  } } }]) {
    const fixture = fakeContext({ evidenceText: JSON.stringify(value) })
    const result = await fixture.tool.execute({ phase: 'dry-run' }, execution())
    assert.equal(result.status, 'fail')
    assert.ok(result.issues.some(issue => issue.startsWith('invalid-evidence:')))
  }
})

test('published tarball loads from its compiled export without source or build dependencies', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'refractrouter-package-'))
  const pluginRoot = resolve(import.meta.dirname, '..')
  try {
    // npm test already built this package; the release command runs the same build via prepack.
    const { stdout } = await execFileAsync('npm', [
      'pack', pluginRoot, '--ignore-scripts', '--json', '--pack-destination', directory,
      '--offline', '--cache', join(directory, 'npm-cache'),
    ], { cwd: ROOT })
    const packed: unknown = JSON.parse(stdout)
    assert.ok(Array.isArray(packed) && packed.length === 1)
    const metadata: unknown = packed[0]
    assert.ok(metadata && typeof metadata === 'object' && 'files' in metadata && 'filename' in metadata)
    assert.equal(typeof metadata.filename, 'string')
    assert.ok(Array.isArray(metadata.files))
    const files = metadata.files.map((entry: unknown) => {
      assert.ok(entry && typeof entry === 'object' && 'path' in entry)
      assert.equal(typeof entry.path, 'string')
      return entry.path
    })
    assert.deepEqual(files.sort(), [
      'CHANGELOG.md', 'README.md', 'cordis.patch.yml', 'package.json',
      'dist/contracts.js', 'dist/contracts.d.ts', 'dist/evidence.js', 'dist/evidence.d.ts',
      'dist/index.js', 'dist/index.d.ts',
    ].sort())
    await execFileAsync('npm', [
      'install', '--prefix', directory, join(directory, String(metadata.filename)),
      '--offline', '--ignore-scripts', '--no-audit', '--no-fund',
      '--cache', join(directory, 'npm-cache'),
    ])
    await copyFile(join(import.meta.dirname, 'fixtures/package-smoke.js'), join(directory, 'smoke.mjs'))
    await execFileAsync(process.execPath, [join(directory, 'smoke.mjs')], { cwd: directory })
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

test('both paid budgets are checked before credentials or process launch', async () => {
  for (const limits of [
    { maxProductionCost: 2.01, maxEvaluationCost: 1 },
    { maxProductionCost: 2, maxEvaluationCost: 1.01 },
    { maxProductionCost: 2, maxEvaluationCost: 0 },
  ]) {
    const fixture = fakeContext({ config: { allowPaidRuns: true }, credential: 'test-secret' })
    await assert.rejects(fixture.tool.execute({
      phase: 'dry-run', executePaidRun: true, ...limits,
    }, execution()), /configured ceiling|positive finite number/)
    assert.equal(fixture.calls.describe, 0)
    assert.equal(fixture.calls.resolve, 0)
    assert.equal(fixture.calls.spawn, 0)
  }
})
