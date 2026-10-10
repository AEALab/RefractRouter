import {test} from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {runInNewContext} from 'node:vm'
import {setImmediate as flush} from 'node:timers/promises'

function client(){let api:any
  const element=(type:any,props:any,...children:any[])=>typeof type==='function'?type({...props,children:children.length?children:props?.children}):{type,props,children:children.length?children:props?.children}
  const react={createElement:element,jsx:(t:any,p:any)=>element(t,p),jsxs:(t:any,p:any)=>element(t,p)}
  runInNewContext(readFileSync(new URL('../dist/client.js',import.meta.url),'utf8'),{
    window:{__ModuleLoader__:{load:({factory}:any)=>{api=factory(()=>react)}}},Intl})
  return api
}
const rid='20261007T064045Z-118980e3a74b'
const text=`正在预检并执行真实自动路由。\n完成；记录：/safe/runs/${rid}/result.json`

test('工具容量显示完整审核计数与实际容量，旧记录保留旧包络而不冒充重新审核',()=>{
  const api=client()
  for(const tools of [
    {evidence_bytes:65759,capacity_basis:'complete-review-request-v1',review_input_bound:210000,review_input_limit:1040384},
    {evidence_bytes:65759,evidence_limit_bytes:16384},
  ]){
    const rendered=JSON.stringify(api.AutomaticRecord({record:{...record(),tools},reference:{id:rid,state:'settled'}}))
    assert.ok(rendered.includes('65,759'))
    if('capacity_basis' in tools){assert.ok(rendered.includes('210,000'));assert.ok(rendered.includes('1,040,384'))}
    else{assert.ok(rendered.includes('旧合同证据上限'));assert.ok(rendered.includes('16,384'))}
  }
})

test('每条轨迹默认收合，标题仍显示执行时间、耗时和轮次，正文留在展开内容内',()=>{
  const api=client(),tree=api.AutomaticRecord({record:record(),reference:{id:rid,state:'settled',turn:3}})
  assert.equal(tree.type,'details')
  assert.equal(tree.props.open,undefined)
  assert.equal(tree.children[0].type,'summary')
  const title=JSON.stringify(tree.children[0])
  for(const value of ['自动路由','已完成','2026-10-07','总耗时','20.0 秒','宿主轮次 3'])assert.ok(title.includes(value),value)
  assert.ok(!title.includes('任务判别与最终执行路线'))
  assert.ok(JSON.stringify(tree.children[1]).includes('任务判别与最终执行路线'))
  const planning=api.TraceRecord({title:'任务 · 已完成',identity:'记录 task-1',
    startedAt:'2026-10-09T10:23:01Z',elapsedMs:62685,children:'规划路由明细'})
  assert.equal(planning.type,'details');assert.equal(planning.props.open,undefined)
  assert.ok(JSON.stringify(planning.children[0]).includes('1 分 2 秒'))
})

test('轨迹转换 UTC 为本地时间，旧记录缺失耗时不伪造零值',()=>{
  const api=client()
  assert.equal(api.traceTimestamp(api.automaticStartedAt(rid),'Asia/Shanghai'),'2026-10-07 14:40:45')
  assert.equal(api.automaticStartedAt('20260230T064045Z-118980e3a74b'),undefined)
  assert.equal(api.traceTimestamp('not-a-date'),'未记录')
  assert.equal(api.traceDuration(undefined),'未记录')
  assert.equal(api.traceDuration(null),'未记录')
  assert.equal(api.traceDuration(-1),'未记录')
  assert.equal(api.traceDuration(0),'0 毫秒')
  assert.equal(api.traceDuration(3662000),'1 小时 1 分 2 秒')
  const tree=api.TraceRecord({title:'静态 · 已完成',identity:'历史记录',children:'原始证据'})
  assert.ok(JSON.stringify(tree.children[0]).includes('未记录'))
})

test('运行中的轨迹定时刷新，慢响应不并发覆盖；卸载后迟到结果不更新',async()=>{
  let api:any,tick:()=>Promise<void>|void,cleanup:()=>void,loads=0,cleared=false
  const updates:any[]=[],pending:Array<(value:any)=>void>=[]
  const react={useState:(value:any)=>[value,(next:any)=>updates.push(next)],useEffect:(effect:any)=>{cleanup=effect()}}
  runInNewContext(readFileSync(new URL('../dist/client.js',import.meta.url),'utf8'),{
    window:{__ModuleLoader__:{load:({factory}:any)=>{api=factory(()=>react)}}},Intl,
    setInterval:(fn:any,ms:number)=>{tick=fn;assert.equal(ms,2500);return 1},clearInterval:()=>{cleared=true}})
  const load=()=>{loads++;return new Promise(resolve=>pending.push(resolve))}
  api.useAutomaticHistory([{id:rid,state:'running'}],load)
  assert.equal(loads,1);tick!();assert.equal(loads,1)
  const first={records:[{run_id:rid,status:'started'}],errors:[]}
  pending.shift()!(first);await flush()
  assert.ok(updates.includes(first));tick!();assert.equal(loads,2)
  cleanup!();assert.equal(cleared,true)
  const late={records:[{run_id:rid,status:'completed'}],errors:[]}
  pending.shift()!(late);await flush()
  assert.ok(!updates.includes(late))
})

test('节点实测超出任务适用范围时明确显示未匹配，不能显示为实测成绩',()=>{
  const api=client(),data:any=record()
  data.node_forecasts=[{node_id:'answer',model_id:'m0',quality_prior:85,
    quality_source:'global-prior-outside-node-evidence-task-scope',
    evidence_scope:{description:'冻结技术发布检查',matched:false}}]
  const tree=JSON.stringify(api.AutomaticRecord({record:data,reference:{id:rid,state:'settled'}}))
  for(const text of ['本任务不在节点实测适用范围','使用未验证先验','冻结技术发布检查','本任务未匹配'])assert.ok(tree.includes(text),text)
})

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

test('刷新后的失败 attempt 从本会话 Location 引用读取，不依赖正常助手正文',()=>{
  const api=client(),reference={id:rid,turn:2,state:'interrupted',error:'质量未通过'}
  const snapshot={legacy:{nodes:[{kind:'turn-error',turn:2,message:'核心停止'}],partial:null},
    timeline:{turns:new Map([[2,{steps:[{data:{get:(key:string)=>key==='refractagent-automatic-attempt'
      ? {refs:[reference,{...reference,id:'../../private'},{...reference,turn:3}]}:undefined}}]}]])}}
  const result=api.automaticRefs(snapshot)
  assert.equal(result.length,1)
  assert.equal(result[0].id,rid)
  assert.equal(result[0].state,'interrupted')
  assert.equal(result[0].error,'核心停止')
})

test('历史失败从 timeline 补入时，最新运行与完成记录仍置顶',()=>{
  const api=client(),old='20261009T080344Z-f47e7a13a3bc',done='20261009T101959Z-f90b211b1e63',latest='20261009T102301Z-0b401d001507'
  const blocks=(id:string)=>[{kind:'reasoning',text:`正在预检并执行真实自动路由。\n【自动路由记录】${id}`}]
  const snapshot:any={legacy:{nodes:[{kind:'assistant',turn:3,blocks:blocks(done)},
    {kind:'turn-error',turn:1,message:'最终审核失败'}],partial:{turn:4,blocks:blocks(latest)}},
    timeline:{turns:new Map([[1,{steps:[{data:{get:()=>({refs:[{id:old,turn:1,state:'interrupted'}]})}}]}]])}}
  let result=api.automaticRefs(snapshot)
  assert.deepEqual(Array.from(result,(r:any)=>r.id),[latest,done,old])
  assert.equal(result[0].state,'running');assert.equal(result[2].error,'最终审核失败')
  snapshot.legacy.nodes.push({kind:'assistant',turn:4,blocks:blocks(latest)})
  snapshot.legacy.partial=null
  result=api.automaticRefs(snapshot)
  assert.equal(result[0].id,latest);assert.equal(result[0].state,'settled')
})

test('最近二十条按运行时间截取，补入的旧失败不挤掉新记录',()=>{
  const api=client(),ids=Array.from({length:21},(_,i)=>`20261009T10${i.toString().padStart(2,'0')}00Z-000000000001`)
  const snapshot={legacy:{nodes:ids.map((id,i)=>({kind:'assistant',turn:i+2,
    blocks:[{kind:'reasoning',text:`正在预检并执行真实自动路由。\n【自动路由记录】${id}`}]})),partial:null},
    timeline:{turns:new Map([[1,{steps:[{data:{get:()=>({refs:[{id:rid,turn:1,state:'interrupted'}]})}}]}]])}}
  assert.deepEqual(Array.from(api.automaticRefs(snapshot),(r:any)=>r.id),ids.slice(1).reverse())
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

test('最终纠正轨迹同时显示初次拒绝和复审结果，旧记录仍可显示',()=>{
  const api=client(),data:any=record()
  data.final_correction={version:'bounded-final-correction-v1',maximum:1,attempt:1,status:'accepted',
    accepted:true,initial_evaluation:{passed:false,score:55,rationale:'初次发现材料外断言'},
    evaluation:{passed:true,score:95,rationale:'修正版复审通过'}}
  const tree=JSON.stringify(api.AutomaticRecord({record:data,reference:{id:rid,state:'settled'}}))
  for(const text of ['最终答复纠正','初次发现材料外断言','修正版复审通过','复审通过'])assert.ok(tree.includes(text),text)
  delete data.final_correction
  assert.ok(!JSON.stringify(api.AutomaticRecord({record:data,reference:{id:rid,state:'settled'}})).includes('最终答复纠正记录'))
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
  for(const expected of ['固定事实检查未通过，未派发评审','执行阶段给评审预留',api.traceNumber(8192),
    '独立于执行模型输出容量','模型高分不能覆盖','compact-type-alias-v1','synthesis',
    '已扣评审预留与规划额度','时延先验不是速度保证','本次最多','个节点（含最终交付）'])assert.ok(tree.includes(expected),expected)
})

test('时间用途阻断明确显示，预留不再被描述为审核中的计时器',()=>{
  const api=client(),data:any=record()
  data.time_contract_validation={applicable:true,passed:false,reason:'预留不是审核到期计时器'}
  const tree=JSON.stringify(api.AutomaticRecord({record:data,reference:{id:rid,state:'settled'}}))
  for(const text of ['时间用途检查','未通过','预留不是审核到期计时器','不代替整份回复审核'])assert.ok(tree.includes(text),text)
})

test('材料状态检查说明保守阻断与事实已证伪的区别',()=>{
  const api=client(),data:any=record()
  data.source_state_validation={applicable:true,passed:false,reason:'归属不清'}
  const tree=JSON.stringify(api.AutomaticRecord({record:data,reference:{id:rid,state:'settled'}}))
  for(const text of ['材料状态归属检查','需澄清，暂不交付','不等于证明系统实际未验证'])assert.ok(tree.includes(text),text)
})


test('新版审核轨迹明确包含修正建议和关键约束，旧记录仍可读取',()=>{
  const api=client(),data:any=record()
  data.review.contract_version='proposal-constraints-v2'
  const tree=JSON.stringify(api.AutomaticRecord({record:data,reference:{id:rid,state:'settled'}}))
  assert.ok(tree.includes('审核同时检查答案、修正建议与恢复步骤'))
  assert.ok(tree.includes('数字正确或高分也不能放行'))
})
test('轨迹解释独立审核参数和最终实际可等待时间',()=>{
  const api=client(),data:any=record()
  data.review={...data.review,model:{provider:'ark',model:'flash'},reasoning_effort:'high',
    limits_version:'automatic-review-envelope-v2',timeout_ms:180000,task_timeout_ms:300000,
    effective_wait_ms:90000}
  const tree=JSON.stringify(api.AutomaticRecord({record:data,reference:{id:rid,state:'settled'}}))
  for(const text of ['ark / flash','high','180,000','300,000','90,000'])assert.ok(tree.includes(text),text)
})
test('同一次审核逐项展示事实来源与时间因果，不用高分替代核对',()=>{
  const api=client(),data:any=record()
  data.review.contract_version='proposal-constraints-v4'
  data.quality={score:95,passed:false,grounding_checks:[{check_id:'source-state',status:'FAIL',
    answer_quote:'未经实测',source_quote:null,rationale:'材料未说明验证情况'},
    {check_id:'time-causality',status:'UNCERTAIN',answer_quote:'挤压执行时间',source_quote:null,rationale:'时间关系无法确认'}]}
  const tree=JSON.stringify(api.AutomaticRecord({record:data,reference:{id:rid,state:'settled'}}))
  for(const text of ['来源与因果核对（同一次审核）','事实状态来源','时间与因果','未通过','无法判断',
    '未经实测','材料未说明验证情况','引用是否存在由 Python 核对'])assert.ok(tree.includes(text),text)
})
test('逐句核对显示独立事实句及语义类别，不替审核器判断真假',()=>{
  const api=client(),data:any=record()
  data.review.contract_version='proposal-constraints-v5'
  data.quality={score:95,passed:false,grounding_checks:[{check_id:'source-claim-c1',status:'FAIL',
    answer_quote:'回滚未经验证',source_quote:null,claim_kind:'FACT',rationale:'没有验证状态来源'}]}
  const tree=JSON.stringify(api.AutomaticRecord({record:data,reference:{id:rid,state:'settled'}}))
  for(const text of ['事实句 ','c1','系统状态断言','回滚未经验证','没有验证状态来源'])assert.ok(tree.includes(text),text)
})

test('格式规范化与缺省补充说明如实展示，旧记录没有该项时继续显示',()=>{
  const api=client(),data:any=record()
  data.review.contract_version='proposal-constraints-v6'
  data.quality={score:55,passed:false,response_normalization:{version:'review-field-spelling-v1',model_calls_added:0,
    changes:[{check_id:'source-claim-c3',from:'rationalale',to:'rationale'}]},
    grounding_checks:[{check_id:'source-claim-c3',status:'FAIL',answer_quote:'未校验',source_quote:null,
      claim_kind:'FACT',rationale:null}]}
  const tree=JSON.stringify(api.AutomaticRecord({record:data,reference:{id:rid,state:'settled'}}))
  for(const text of ['审核返回格式规范化','review-field-spelling-v1','rationalale',
    '判定、分数和引用不变','没有增加审核调用','审核器未提供本项补充说明'])assert.ok(tree.includes(text),text)
  delete data.quality.response_normalization
  assert.ok(!JSON.stringify(api.AutomaticRecord({record:data,reference:{id:rid,state:'settled'}})).includes('审核返回格式规范化'))
})
