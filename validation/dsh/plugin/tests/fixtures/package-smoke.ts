import assert from 'node:assert/strict'
import { apply, Config, name } from 'dsh-refractrouter-validation'

// Compiled and copied into an isolated consumer with only the installed tarball.
// A bare import tests the published export map without falling back to checkout source.
assert.equal(name, 'refractrouter-validation')
assert.equal(typeof apply, 'function')
const parsed = Config['~standard'].validate({})
assert.ok(parsed.value)
assert.equal(parsed.value.allowPaidRuns, false)
assert.equal(parsed.value.maxRetries, 0)
