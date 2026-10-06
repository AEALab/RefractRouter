import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { progressText, runSummary, type ProgressEvent } from '../dist/dag-progress.js'

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

test('自动路由摘要解释规则、本地判别和最终路线',()=>{
  const summary=runSummary({strategy_name:'自动路由',status:'completed',billing_unit:'CNY',
    costs:{evaluation:0,unconfirmed:0},cost_breakdown:{planning:0,dynamic_planning:0,execution:.1},
    result_path:'/tmp/result.json',complexity_gate:{rule_decision:'direct',decision:'dag',
      combination:'local-separable',reasons:['local-separable'],local_decision:{verdict:'SEPARABLE',
        rawVerdict:'SEPARABLE',confidence:.91,model:'laya-local',latencyMs:12,queueMs:2}}})
  assert.match(summary,/规则 direct → 最终 dag/)
  assert.match(summary,/本地结构判别：SEPARABLE/)
  assert.match(summary,/实验能力/)
})

test('自动路由摘要保留规划后 direct 与 DAG 的估算和选择依据',()=>{
  const summary=runSummary({strategy_name:'自动路由',status:'completed',billing_unit:'CNY',
    costs:{evaluation:0,unconfirmed:0},cost_breakdown:{planning:.01,execution:.1},
    result_path:'/tmp/result.json',route_comparison:{status:'selected',route:'direct',
      reason:'direct-estimated-cost-not-worse',direct:{total_estimated_cost:.12},
      dag:{total_estimated_cost:.18},decision_factors:{qualified_execution_model_count:1,
        quality_basis:'declared-model-profile-prior',task_specific_dag_quality_gain_verified:false,
        dag_extra_worker_cost:.06}}})
  assert.match(summary,/选中 direct/)
  assert.match(summary,/direct 预计 0.1200，DAG 预计 0.1800 CNY/)
  assert.match(summary,/尚无本任务拆分质量增益的验证/)
  assert.match(summary,/两路线合格执行模型共 1 款/)
  assert.match(summary,/DAG 预计执行费用相差 0.0600 CNY/)
})

test('自动路由摘要把规划器单节点结果标为未拆分',()=>{
  const summary=runSummary({strategy_name:'自动路由',status:'completed',billing_unit:'CNY',
    costs:{evaluation:0,unconfirmed:0},cost_breakdown:{planning:.01,execution:.1},
    result_path:'/tmp/result.json',route_comparison:{status:'selected',route:'direct',
      reason:'generated-single-node',selected_candidate:'generated-plan',
      generated_node_count:1,selected_node_count:1,multi_node_selected:false,
      direct:null,dag:{total_estimated_cost:.11}}})
  assert.match(summary,/选中计划 1 个节点；未形成多节点拆分/)
  assert.match(summary,/选中 direct（规划器单节点）/)
  assert.match(summary,/规划器单节点候选 预计 0.1100 CNY/)
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


test('拆分摘要说明顺序执行、时延拒绝和匹配样本',()=>{
  const summary=runSummary({complexity_gate:{rule_decision:'dag',decision:'direct',combination:'coupled-sequential-work',reasons:['local-coupled']},route_comparison:{route:'direct',candidate_diagnostics:{dag:{rejected_combinations:{latency:2},minimum_scheduled_latency_ms:300000,remaining_latency_ms:292000,minimum_cost:.03,remaining_cost:1,empty_candidate_nodes:[]}},latency_evidence:{dag:{work:{model:{source:'sparse-or-unmatched-bootstrap',samples:2,input_bucket_max:4096,output_bucket_max:4096}}}}}})
  assert.match(summary,/顺序依赖工作保持单路线执行/)
  assert.match(summary,/预计时延不满足 2 种分配/)
  assert.match(summary,/预计最短 300000.0000 ms，剩余期限 292000.0000 ms/)
  assert.match(summary,/匹配样本 2/)
  assert.match(summary,/非 SLA 保证/)
})

test('混合计费摘要区分主账与外部 Jev，并展示已知合计',()=>{
  const summary=runSummary({strategy_name:'自动路由',status:'completed',billing_unit:'MIXED',
    costs:{by_unit:{AFP:{production:7.49295,evaluation:4.05045,unconfirmed:0},
      CNY:{production:0,evaluation:0,unconfirmed:0}},
      out_of_band_judge:{unit:'CNY',cost:.0001580969124,call_id:'jev-1'},
      all_in_known_by_unit:{AFP:11.5434,CNY:.0001580969124}},
    complexity_gate:{local_decision:{backend:'jev',model:'typesafe/jev',verdict:'UNKNOWN',
      rawVerdict:'UNKNOWN',costCny:.0001580969124,provider:'openrouter'}}})
  assert.match(summary,/费用分账：AFP：生产 7\.4930、评审 4\.0504/)
  assert.match(summary,/已知合计（含外部拆分 Judge）：AFP 11\.5434、CNY 0\.0002/)
  assert.match(summary,/外部判别调用 jev-1/)
})

test('自动路由摘要分清选路预计、调用预留、结算与最终评审保护',()=>{
  const summary=runSummary({strategy_name:'自动路由',status:'completed',billing_unit:'MIXED',
    cost_trace:{schema_version:'automatic-cost-trace-v1',selected_nodes:[{node_id:'answer',
      model_id:'ark-flash',unit:'AFP',expected_cost:.12,expected_input_tokens:300,
      conservative_input_bound:1200,expected_output_tokens:100,input_source:'observed-byte-ratio-v1',
      output_source:'planned-node-output'}],review_protection:{amount:.7,unit:'CNY',
      output_tokens:1024,status:'converted-to-call'},calls:[{label:'answer',model_id:'ark-flash',
      unit:'AFP',reserved:1.2,charged:.14,status:'billed'}]}})
  assert.match(summary,/预计值用于选路；预留上界用于准入；实际结算以调用账本为准/)
  assert.match(summary,/输入预计 300 tokens（保守上界 1200）/)
  assert.match(summary,/最终评审保护额度：0\.7000 CNY/)
  assert.match(summary,/预留上界 1\.2000 AFP，实际结算 0\.1400 AFP/)
})

test('自动路由摘要区分规划前净节省预测与本路线被动结算',()=>{
  const summary=runSummary({strategy_name:'自动路由',status:'completed',billing_unit:'AFP',
    route_comparison:{status:'selected',route:'dag',reason:'lower-estimated-total-cost',
      direct:{total_estimated_cost:.3},dag:{total_estimated_cost:.2},
      dag_net_estimated_savings_vs_unprobed_direct:.06},
    route_observations:{value:{route:'dag',actual_costs_by_unit:{AFP:.22},
      unconfirmed_costs_by_unit:{AFP:0},judge_passed:true}}})
  assert.match(summary,/规划前基线净节省预测：0\.0600 AFP（已计规划探测费）/)
  assert.match(summary,/被动观测：dag 路线实际结算 0\.2200 AFP/)
  assert.match(summary,/非独立质量证明/)
  assert.match(summary,/未执行路线没有实测费用/)
})

test('未进入 DAG 比较的直接路线也展示现金准入原因',()=>{
  const summary=runSummary({accounting_basis:'public-reference-valuation',routing:{
    status:'no-feasible-route',diagnostics:{rejected_combinations:{cash:2},
      remaining_cash:0,minimum_cash:.1,minimum_cost:.1,remaining_cost:10,
      empty_candidate_nodes:[]}}})
  assert.match(summary,/现金费用不满足 2 种分配/)
  assert.match(summary,/剩余现金 0/)
  assert.match(summary,/最低预计现金 0.1000/)
})
