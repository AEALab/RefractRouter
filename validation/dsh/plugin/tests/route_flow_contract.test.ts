import {test} from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {runInNewContext} from 'node:vm'

function client(){let api:any
  const element=(type:any,props:any,...children:any[]):any=>typeof type==='function'
    ?type({...props,children:children.length?children:props?.children}):{type,props,children:children.length?children:props?.children}
  const react={createElement:element,jsx:(t:any,p:any)=>element(t,p),jsxs:(t:any,p:any)=>element(t,p)}
  runInNewContext(readFileSync(new URL('../dist/client.js',import.meta.url),'utf8'),{
    window:{__ModuleLoader__:{load:({factory}:any)=>{api=factory(()=>react)}}},Intl})
  return api
}
const call=(id:string,purpose='execute')=>({call_id:id,model_id:'m-'+id,provider:'fixture',actual_model:'real-'+id,
  purpose,disposition:'pending',status:'unknown-usage',charged:.01,billing_unit:'CNY',reasoning_effort:'low'})
test('六类策略的流程图只展示已记录模型，运行、缓冲、丢弃与接管随结果更新',()=>{
  const api=client()
  for(const strategy of ['static','stage','task','advisor','escalation','composite']){
    const r:any={strategy,status:'running',calls:[call('one')],decisions:[]}
    let nodes=api.planningFlowNodes(r)
    assert.equal(nodes[0].model,'fixture / real-one');assert.equal(nodes[0].tone,'active')
    assert.match(nodes[0].status,/等待结果与用量/)
    r.calls[0].status='billed';r.calls[0].disposition='buffered'
    assert.equal(api.planningFlowNodes(r)[0].tone,'waiting')
    r.calls[0].disposition='discarded';r.calls.push({...call('two','takeover'),status:'billed',disposition:'accepted',review_status:'takeover-unreviewed'})
    r.decisions.push({candidateCallId:'one',reason:'escalation-defect',reviewVerdict:'DEFECT'})
    r.status='completed';nodes=api.planningFlowNodes(r)
    assert.equal(nodes.length,2);assert.equal(nodes[0].tone,'discarded');assert.match(nodes[0].details[0],/明确缺陷/)
    assert.equal(nodes[1].title,'强模型接管');assert.equal(nodes[1].tone,'ok');assert.match(nodes[1].status,/接管后未追加审核/)
    assert.ok(nodes[1].details[1].includes('low'))
  }
})
test('待核对用量与未派发预留不标成成功，不把本地 Judge 伪造为付费调用',()=>{
  const api=client(),r:any={status:'call-failed',calls:[call('one')],decisions:[]}
  let nodes=api.planningFlowNodes(r);assert.equal(nodes[0].tone,'failed');assert.match(nodes[0].status,/待核对/)
  r.calls[0].status='reserved';r.calls[0].disposition='reserved'
  assert.equal(api.planningFlowNodes(r)[0].tone,'waiting')
  r.calls.push({...call('local','advisor'),status:'billed',disposition:'consult',usage_type:'local-decision'})
  assert.match(api.planningFlowNodes(r)[1].details[1],/本地推论，无 API 费用/)
  r.calls[1].disposition='accepted';assert.equal(api.planningFlowNodes(r)[1].status,'判别回执已接受')
  r.calls=[];assert.equal(api.planningFlowNodes(r).length,0)
})
test('自动路由图保持账本顺序，保留并发与未知用量语义，不新增假调用',()=>{
  const api=client(),record={calls:[{label:'answer',category:'production',route:{provider:'ark',model:'flash'},status:'unknown-usage'},
    {label:'review',category:'evaluation',route:{provider:'ark',model:'judge',reasoning_effort:'low'},status:'reserved'}]}
  let nodes=api.automaticFlowNodes(record,true)
  assert.equal(nodes[0].model,'ark / flash');assert.equal(nodes[0].tone,'active');assert.equal(nodes[1].tone,'waiting')
  assert.equal(api.automaticFlowNodes(record,false)[0].tone,'failed')
  assert.equal(api.automaticFlowNodes({calls:[]},false).length,0)
  const render=(id:string)=>JSON.stringify(api.RouteFlow({identity:id,nodes,state:'运行中',running:true,orderLabel:'账本预留顺序'}))
  const first=render('one'),second=render('two')
  for(const text of ['路由调用流程图','不表示 DAG 依赖','每 2.5 秒刷新','账本预留顺序','markerEnd'])assert.ok(first.includes(text),text)
  assert.ok(first.includes('refract-route-arrow-one'));assert.ok(second.includes('refract-route-arrow-two'))
  const withJudge=api.automaticFlowNodes({...record,external_judge_called:true,external_judge_cost_cny:.001,
    structure:{judge:{model:'typesafe/jev-1.13',provider:'openrouter',rawVerdict:'SEPARABLE',verdict:'SEPARABLE',latencyMs:30}}},false)
  assert.equal(withJudge.length,3);assert.equal(withJudge[0].independent,true)
  const tree=api.RouteFlow({identity:'independent',nodes:withJudge,state:'完成'})
  assert.ok(JSON.stringify(tree).includes('独立结构判别'))
  const edges=(node:any):number=>Array.isArray(node)?node.reduce((n,c)=>n+edges(c),0):
    node&&typeof node==='object'?(node.type==='path'&&node.props.markerEnd?1:0)+edges(node.children):0
  assert.equal(edges(tree),1)
})
