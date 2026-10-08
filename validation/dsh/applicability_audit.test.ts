import assert from 'node:assert/strict'
import {hostDiagnostic} from './applicability_audit.ts'

const credential = 'fake-private-credential'
const row = hostDiagnostic({id: 'request-1', provider: 'fixture', model: 'fixture',
  messages: [{content: '私有任务正文'}], authorization: credential},
  {ok: false, failure_type: 'provider-error', message:
    `错误 ${credential}; apikey_fakevalue; sk-or-v1-fakevalue; Bearer another-secret; api_key=unknown-secret`,
    request_id: 'provider-request-1', arbitrary: credential}, {test: credential}, 12.6)
const encoded = JSON.stringify(row)
for (const secret of [credential, 'apikey_fakevalue', 'sk-or-v1-fakevalue',
  'another-secret', 'unknown-secret', '私有任务正文']) assert.ok(!encoded.includes(secret))
assert.equal(row.elapsedMs, 13)
assert.equal(row.failureType, 'provider-error')
assert.equal(row.requestId, 'provider-request-1')
assert.equal(row.ok, false)
assert.ok(!('arbitrary' in row) && !('messages' in row) && !('authorization' in row))
const success = hostDiagnostic({id: 'request-2'}, {ok: true, message: credential}, {}, 1)
assert.ok(!('message' in success) && !('failureType' in success))
assert.equal(String(hostDiagnostic({}, {ok: false, message: 'x'.repeat(1000)}, {}, 0).message).length, 300)
const billedFailure = hostDiagnostic({}, {ok:false, usage_confirmed:true,
  usage:{input_tokens:100,output_tokens:10,arbitrary:credential}}, {}, 1)
assert.equal(billedFailure.usageConfirmed,true)
assert.deepEqual(billedFailure.usage,{input_tokens:100,output_tokens:10})
assert.ok(!('usageConfirmed' in hostDiagnostic({}, {ok:false,usage_confirmed:false,usage:{input_tokens:100}}, {}, 1)))
