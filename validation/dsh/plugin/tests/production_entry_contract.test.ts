import assert from 'node:assert/strict'
import test from 'node:test'
import { apply, Config, inject } from '../dist/entry.js'
import { inject as routingInject } from '../dist/agent-provider.js'

test('生产主入口与旧 profile 路由覆盖只登记模型及媒体工具，不发起调用', () => {
  for (const config of [{ entryMode: 'routing', allowPaidRuns: false },
    { pythonExecutable: 'refractagent', executionMode: 'demo', allowPaidRuns: false }]) {
  const models: string[][] = [], tools: string[] = []
  const host = {
    llm: { registerAdapter(providers: string[]) { models.push(providers) } },
    tools: { register(tool: { name: string }) { tools.push(tool.name) } },
  }
  const checked = Config['~standard'].validate(config)
  assert.ok('value' in checked)
  apply(host as never, checked.value)
  assert.deepEqual(models, [['refractagent']])
  assert.ok(tools.includes('refract_generate_image'))
  assert.ok(!tools.includes('refractrouter_validate'))
  assert.ok(!tools.includes('refractagent_text_task'))
  for (const dependency of routingInject) assert.ok(inject.includes(dependency))
  }
})

test('旧主入口与独立验收入口保留验收合同，拒绝未知入口', () => {
  for (const config of [{ allowPaidRuns: false }, { entryMode: 'validation-tools', allowPaidRuns: false }]) {
    const tools: string[] = []
    const checked = Config['~standard'].validate(config)
    assert.ok('value' in checked)
    apply({ tools: { register(tool: { name: string }) { tools.push(tool.name) } } } as never, checked.value)
    assert.ok(tools.includes('refractrouter_validate'))
  }
  assert.ok('issues' in Config['~standard'].validate({ entryMode: 'unknown' }))
  assert.ok('issues' in Config['~standard'].validate({ entryMode: 'routing', notASetting: true }))
})
