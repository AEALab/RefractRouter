import assert from 'node:assert/strict'
import { spawn as spawnChild } from 'node:child_process'
import { rm, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import test from 'node:test'

import { apply } from '../validation/dsh/plugin/index.js'

const ROOT = resolve(import.meta.dirname, '..')

function evidence({ mode = 'preflight', issues = [], artifact = 'preflight.json' } = {}) {
  return {
    status: issues.length === 0 ? 'pass' : 'fail',
    mode,
    issues,
    preflight: {
      call_plan: {
        training_model_calls: 0,
        production_model_calls: 56,
        judge_model_calls: 5,
        total_model_calls: 61,
      },
      cost_estimates: {
        production_upper_estimate_usd: 1.5,
        evaluation_upper_estimate_usd: 0.45,
        total_upper_estimate_usd: 1.95,
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
} = {}) {
  const calls = {
    describe: 0,
    resolve: 0,
    confine: 0,
    spawn: 0,
    spawnSpec: undefined,
  }
  let tool
  const ctx = {
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
          ? new Promise(resolveOutcome => {
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
  return { calls, get tool() { return tool } }
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
  assert.equal(fixture.calls.spawnSpec.env.OPENAI_API_KEY, undefined)
  assert.equal(fixture.calls.spawnSpec.stdio.stdout.maxBytes, 262_144)
  assert.equal(fixture.calls.spawnSpec.stdio.stderr.maxBytes, 262_144)
  assert.equal(fixture.calls.spawnSpec.graceMs, 5_000)
  assert.equal(fixture.calls.spawnSpec.argv.includes('--execute-paid-run'), false)
})

test('danger-full-access bypasses sandbox wrapping', async () => {
  const fixture = fakeContext({ mode: 'danger-full-access' })
  const result = await fixture.tool.execute({ phase: 'final' }, execution())

  assert.equal(result.status, 'pass')
  assert.equal(result.sandboxMode, 'danger-full-access')
  assert.equal(result.sandboxEnforcement, undefined)
  assert.equal(fixture.calls.confine, 0)
})

test('paid execution requires deployment enablement, two budgets, and a credential', async () => {
  const disabled = fakeContext({ credential: 'test-secret' })
  await assert.rejects(
    disabled.tool.execute({
      phase: 'dry-run',
      executePaidRun: true,
      maxProductionCostUsd: 2,
      maxEvaluationCostUsd: 1,
    }, execution()),
    /paid validation is disabled/,
  )
  assert.equal(disabled.calls.describe, 0)
  assert.equal(disabled.calls.resolve, 0)

  const enabled = fakeContext({ config: { allowPaidRuns: true } })
  await assert.rejects(
    enabled.tool.execute({ phase: 'dry-run', executePaidRun: true }, execution()),
    /maxProductionCostUsd must be a positive finite number/,
  )
  await assert.rejects(
    enabled.tool.execute({
      phase: 'dry-run',
      executePaidRun: true,
      maxProductionCostUsd: 2,
      maxEvaluationCostUsd: 1,
    }, execution()),
    /requires configured credential OPENAI_API_KEY/,
  )
  assert.equal(enabled.calls.resolve, 1)
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
    maxProductionCostUsd: 2,
    maxEvaluationCostUsd: 1,
  }, execution())

  assert.equal(fixture.calls.resolve, 1)
  assert.equal(fixture.calls.spawnSpec.env.OPENAI_API_KEY, secret)
  assert.equal(fixture.calls.spawnSpec.argv.includes('--execute-paid-run'), true)
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
      maxProductionCostUsd: 2,
      maxEvaluationCostUsd: 1,
    }, execution()),
    error => {
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
    error => error?.name === 'AbortError',
  )
  assert.equal(aborted.calls.spawn, 0)
})

function boundedCollector(stream, maxBytes) {
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
  let tool
  const ctx = {
    tools: { register(spec) { tool = spec } },
    credentials: {
      async describe() { return { configured: false } },
      async resolve() { throw new Error('preflight must not resolve credentials') },
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
        const childEnv = {}
        for (const [key, value] of Object.entries(process.env)) {
          if (!/KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL/i.test(key) && !key.startsWith('DSH_')) {
            childEnv[key] = value
          }
        }
        Object.assign(childEnv, spec.env)
        const child = spawnChild(spec.argv[0], spec.argv.slice(1), {
          cwd: spec.cwd,
          env: childEnv,
          stdio: ['ignore', 'pipe', 'pipe'],
        })
        const stdout = boundedCollector(child.stdout, spec.stdio.stdout.maxBytes)
        const stderr = boundedCollector(child.stderr, spec.stdio.stderr.maxBytes)
        const done = new Promise((resolveOutcome, reject) => {
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
  return { get tool() { return tool } }
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
    assert.equal(result.credentialConfigured, false)
    assert.equal(result.callPlan.totalModelCalls, 61)
    assert.equal(result.costEstimateUsd.total, 1.95)
    assert.equal(result.artifactHashes.length, 1)
  } finally {
    await rm(dirname(result.evidencePath), { recursive: true, force: true })
  }
})
