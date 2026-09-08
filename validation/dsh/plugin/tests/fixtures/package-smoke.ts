import assert from 'node:assert/strict'
import { apply, Config, name } from 'dsh-refractrouter-validation'
import { apply as applyAgent, configure, name as agentName } from 'dsh-refractrouter-validation/agent'

// Compiled and copied into an isolated consumer with only the installed tarball.
// A bare import tests the published export map without falling back to checkout source.
assert.equal(name, 'refractrouter-validation')
assert.equal(typeof apply, 'function')
const parsed = Config['~standard'].validate({})
assert.ok(parsed.value)
assert.equal(parsed.value.allowPaidRuns, false)
assert.equal(parsed.value.maxRetries, 0)
assert.equal(agentName, 'refractagent')
assert.equal(typeof applyAgent, 'function')
assert.equal(configure().executionMode, 'demo')
assert.equal(configure().allowPaidRuns, false)
