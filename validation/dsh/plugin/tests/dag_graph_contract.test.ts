import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { progressText, type ProgressEvent } from '../dist/dag-progress.js'

function client() {
  let api: any
  runInNewContext(readFileSync(new URL('../dist/client.js', import.meta.url), 'utf8'), {
    window: { __ModuleLoader__: { load: ({ factory }: any) => { api = factory(() => ({ createElement: () => null })) } } },
  })
  return api
}
const event = (id: string, parents: string[] = [], state = 'pending'): ProgressEvent => ({
  protocol: 'refractagent-progress/v1', run_id: 'fixture', sequence: 1, elapsed_ms: 0,
  phase: 'executing', status: 'started', simulated: true, reason: '独立分析再汇总',
  nodes: [{ id, parents, state, objective: '<分析>', attempt: 1, recovery: null,
    node_type: 'synthesis', difficulty: 'medium', risk: 'high', model: { id: 'm', provider: 'fixture', model: 'model' } }],
})
const prefix = '正在快速拆分任务，随后执行可并行的步骤。\n'

test('DSH 图使用同一进度文本实时更新，支持历史回放和类型展示', () => {
  const api = client()
  const first = event('trend'); first.nodes.push(event('drivers').nodes[0], event('answer', ['trend','drivers']).nodes[0])
  const transcript = prefix + progressText(first)
  const graph = api.parse(transcript)
  assert.equal(graph.nodes.length, 3)
  assert.equal(graph.nodes[0].type, 'synthesis')
  assert.deepEqual(Array.from(graph.nodes[2].parents), ['trend','drivers'])
  const positions = api.layout(graph.nodes)
  assert.equal(positions.get('trend').y, positions.get('drivers').y)
  assert.ok(positions.get('answer').y > positions.get('drivers').y)
  const next = structuredClone(first); next.nodes[0].state = 'running'
  assert.equal(api.parse(transcript + progressText(next, first)).nodes[0].state, '运行中')
  assert.equal(api.parse(transcript + '\n执行已中断；以上为最后收到的节点状态。').interrupted, true)
})

test('动态图替换旧拓扑，流式截断不生成虚构节点，拒绝环和未知边', () => {
  const api = client(), old = event('old'), next = event('new')
  const transcript = prefix + progressText(old)
  assert.equal(api.parse(transcript + progressText(next, old)).nodes[0].id, 'new')
  assert.equal(api.parse(prefix + progressText(old).slice(0, -2)).nodes.length, 0)
  assert.equal(api.parse('普通模型的回答\n' + progressText(old)), null)
  assert.equal(api.parse(prefix + progressText(event('child', ['missing']))), null)
  assert.equal(api.parse(prefix + progressText(event('cycle', ['cycle']))), null)
})

test('真实自动路由的进度文本也能在 DAG 页签回放', () => {
  const api = client(), livePrefix = '正在预检并执行真实自动路由。\n'
  assert.equal(api.parse(livePrefix + progressText(event('answer'))).nodes[0].id, 'answer')
})

test('客户端只贡献独立页签，不发起请求或改动原会话渲染器', () => {
  const api = client(); let config: any, View: any
  api.applyGraph({ slots: { inject: (_: string, cb: () => void) => [...(cb() as any)], register: (value: any, component: any) => { config = value; View = component } } })
  assert.equal(config.name, 'conversation.view')
  assert.equal(config.id, 'refractagent-dag')
  assert.equal(config.label(), '任务 DAG')
  let selected = false
  assert.doesNotThrow(() => View({ useChat: (select: any) => {
    selected = true
    return select({ legacy: { nodes: [], partial: null } })
  } }))
  assert.equal(selected, true)
})


test('设置卡片、DAG 与路由轨迹共同注册，输入区不增加策略控件', () => {
  const api = client(), registered: string[] = []
  api.apply({
    slots: { inject: (_: string, declaration: () => Iterable<unknown>) => [...declaration()],
      register: (options: any) => { registered.push(options.name) } },
    locale: { register() {} }, effect: (setup: () => unknown) => setup(),
    settingsScope: { bind: () => ({ getSnapshot: () => ({ status: 'ready', value: {} }),
      subscribe: () => () => {} }) },
  })
  assert.deepEqual(registered.sort(), ['conversation.view', 'conversation.view', 'settings.plugin.item', 'settings.plugin.item'])
})
