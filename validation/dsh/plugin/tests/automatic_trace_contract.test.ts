import {test} from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {runInNewContext} from 'node:vm'

function client(){let api:any
  const element=(type:any,props:any,...children:any[])=>typeof type==='function'?type({...props,children:children.length?children:props?.children}):{type,props,children:children.length?children:props?.children}
  const react={createElement:element,jsx:(t:any,p:any)=>element(t,p),jsxs:(t:any,p:any)=>element(t,p)}
  runInNewContext(readFileSync(new URL('../dist/client.js',import.meta.url),'utf8'),{
    window:{__ModuleLoader__:{load:({factory}:any)=>{api=factory(()=>react)}}},Intl})
  return api
}
const rid='20261007T064045Z-118980e3a74b'
const text=`正在预检并执行真实自动路由。\n完成；记录：/safe/runs/${rid}/result.json`

test('自动轨迹只读取当前会话的受控助手记录引用，兼容旧版路径标记',()=>{
  const api=client(),snapshot={legacy:{nodes:[
    {kind:'user',blocks:[{kind:'reasoning',text}]},
    {kind:'assistant',provenance:{provider:'other'},blocks:[{kind:'reasoning',text}]},
    {kind:'assistant',turn:3,provenance:{provider:'refractagent'},blocks:[{kind:'reasoning',text}]},
  ],partial:null}}
  const refs=api.automaticRefs(snapshot)
  assert.equal(refs.length,1);assert.equal(refs[0].id,rid);assert.equal(refs[0].turn,3)
  assert.equal(api.automaticRefs({legacy:{nodes:[{kind:'assistant',blocks:[{kind:'text',text}]}],partial:null}}).length,0)
})

test('自动轨迹识别运行、中断和重复引用，不把终止记录当作正常完成',()=>{
  const api=client(),prefix=`正在预检并执行真实自动路由。\n【自动路由记录】${rid}`
  const result=api.automaticRefs({legacy:{nodes:[
    {kind:'assistant',turn:2,blocks:[{kind:'reasoning',text:prefix}]},
    {kind:'turn-error',turn:2,message:'调用失败'},
  ],partial:null}})
  assert.equal(result.length,1);assert.equal(result[0].state,'interrupted');assert.equal(result[0].error,'调用失败')
  assert.equal(api.automaticRefs({legacy:{nodes:[],partial:{turn:4,blocks:[{kind:'reasoning',text:prefix}]}}})[0].state,'running')
})

test('自动轨迹不接受自由文本路径、穿越或无限数量引用',()=>{
  const api=client()
  const refs=api.automaticRefs({legacy:{nodes:Array.from({length:25},(_,i)=>({kind:'assistant',
    blocks:[{kind:'reasoning',text:`正在预检并执行真实自动路由。\n【自动路由记录】20261007T064045Z-${i.toString(16).padStart(12,'0')}`}]})),partial:null}})
  assert.equal(refs.length,20)
  assert.equal(api.automaticRefs({legacy:{nodes:[{kind:'assistant',blocks:[{kind:'reasoning',text:`记录：/safe/${rid}/result.json`}]}],partial:null}}).length,0)
})

function record(){return {run_id:rid,status:'completed',wall_time_ms:20000,simulated:false,
  structure:{rule_decision:'dag',decision:'direct',combination:'coupled-sequential-work',judge:{
    provider:'openrouter',model:'jev',rawVerdict:'COUPLED',verdict:'COUPLED',rawAnswers:{requires_previous_output:{type:'noul',noul:.8}},probabilityBasis:'derived-not-model'}},
  comparison:{route:'direct',direct:{total_estimated_cost:.7},dag:{total_estimated_cost:1.4},complete_task_cost_bound:null},
  candidates:Array.from({length:5},(_,i)=>({id:`m${i}`,provider:'ark',model:`model${i}`,selected_nodes:i===0?['answer']:[],
    admission:[{path:'execution',node:'answer',reason:'eligible'}],assignment_checks:{}})),
  accounting_basis:'public-reference-valuation',ledger:[{category:'production',cash_limit_cny:2,remaining_cash_cny:2,reference_occupied_cny:.3,billed_cash_cny:0,pending_cash_cny:0,pending_count:0}],
  calls:[{label:'answer',category:'production',route:{provider:'ark',model:'flash'},status:'unknown-usage',charged:.3,billing_unit:'CNY',billing_mode:'subscription'}],
  tools:{records:[{tool:'bash',call_id:'t1',outcome:'completed'}]},review:{required:true,status:'completed',score:100,passed:true},
  issues:[] as string[],limitations:[],missing_evidence:['per-candidate-budget-check']}}

test('浏览器与旧宿主进程组合时明确提示合同不匹配，不因缺字段显示空白',()=>{
  const api=client()
  assert.throws(()=>api.parseAutomaticHistory({records:[]}),/请重新加载 DSH 服务/)
  assert.equal(api.parseAutomaticHistory({schema_version:'automatic-routing-trace-v1',records:[],errors:[]}).records.length,0)
})

test('轨迹展示五款模型、原始答案和历史预算，明确预测与现金的边界',()=>{
  const api=client(),tree=JSON.stringify(api.AutomaticRecord({record:record(),reference:{id:rid,state:'settled',turn:1}}))
  assert.ok(tree.includes('宿主轮次 '));assert.ok(!tree.includes('第 2 轮'))
  for(const expected of ['model0','model1','model2','model3','model4','原始答案','不是模型直接给出的 Choice','订阅实际扣费','未经提供方账单确认','未选择的候选路线没有被执行','当时现金预算','旧记录未保存逐模型预算检查','completed 表示回执已返回'])assert.ok(tree.includes(expected),expected)
  assert.ok(!tree.includes('尚无规划路由记录'))
})

test('缺失金额不显示零费用，小额 Jev 费用保留有效精度',()=>{
  const api=client()
  assert.equal(api.traceNumber(null),'未记录');assert.equal(api.traceNumber(undefined),'未记录')
  assert.equal(api.traceNumber(.0002501784474),'0.0002501784')
  const data=record();data.status='failed';data.issues=['missing or unconfirmed model usage; reservation retained']
  const tree=JSON.stringify(api.AutomaticRecord({record:data,reference:{id:rid,state:'interrupted',error:'宿主取消'}}))
  assert.ok(tree.includes('宿主已中断'));assert.ok(tree.includes('不自动重发待核对调用'));assert.ok(tree.includes(data.issues[0]))
})

test('轨迹显示独立评审包络、固定事实阻断和已记录的格式兼容转换',()=>{
  const api=client(),data:any=record()
  data.status='quality-failed'
  data.review={required:true,status:'blocked-deterministic-check',passed:false,
    time_reserve_ms:30000,output_cap:8192,limits_version:'automatic-review-envelope-v1'}
  data.deterministic_validation={passed:false}
  data.planning_budget={version:'automatic-planning-time-envelope-v1',execution_after_planner_ms:150000,max_nodes:2}
  data.planner_normalizations=[{type_normalization:{version:'compact-type-alias-v1',
    changes:[{node_id:'facts',from:'analysis',to:'synthesis'}]}}]
  const tree=JSON.stringify(api.AutomaticRecord({record:data,reference:{id:rid,state:'settled'}}))
  for(const expected of ['固定事实检查未通过，未派发评审','评审预留时间',api.traceNumber(8192),
    '独立于执行模型输出容量','模型高分不能覆盖','compact-type-alias-v1','synthesis',
    '已扣评审预留与规划额度','时延先验不是速度保证','本次最多','个节点（含最终交付）'])assert.ok(tree.includes(expected),expected)
})


test('新版审核轨迹明确包含修正建议和关键约束，旧记录仍可读取',()=>{
  const api=client(),data:any=record()
  data.review.contract_version='proposal-constraints-v2'
  const tree=JSON.stringify(api.AutomaticRecord({record:data,reference:{id:rid,state:'settled'}}))
  assert.ok(tree.includes('审核同时检查答案、修正建议与恢复步骤'))
  assert.ok(tree.includes('数字正确或高分也不能放行'))
})
