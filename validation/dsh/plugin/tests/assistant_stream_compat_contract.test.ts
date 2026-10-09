import assert from 'node:assert/strict'
import test from 'node:test'
import {automaticAttemptDefinition,retainAutomaticAttemptNode, type AssistantDefinition, type AssistantEventRegistry,
  type AssistantViewNode} from '../dist/assistant-stream-compat.js'

function node(text = '正在预检并执行真实自动路由。\n【自动路由记录】run'):
  AssistantViewNode {
  return {key:'assistant-step:0:0', id:'0:0', kind:'assistant-step', target:'chat',
    visibility:'visible', data:{blocks:[{kind:'reasoning', text}], status:'running'}}
}

function fixture(definitions: AssistantDefinition[]) {
  const listeners = new Set<() => void>()
  const registry: AssistantEventRegistry = {entries:()=>definitions,
    subscribe(listener){listeners.add(listener);return ()=>{listeners.delete(listener)}}}
  return {registry, listeners, update:()=>{for (const listener of listeners) listener()}}
}

test('自动入口失败 attempt 撤回时保留同 key 隐藏节点，允许宿主继续处理失败', () => {
  const definition: AssistantDefinition = {kind:'assistant-step', target:'chat', buildViewNode:()=>null}
  const f=fixture([definition]), dispose=retainAutomaticAttemptNode(f.registry)
  const previous=node(), context={current:new Map([['chat',previous]])}
  const next=definition.buildViewNode!(context)!
  assert.equal(next.key,previous.key)
  assert.equal(next.visibility,'hidden')
  assert.equal(next.data,previous.data)
  assert.equal(previous.visibility,'visible')
  assert.equal(definition.buildViewNode!({current:new Map([['chat',next]])}),next)
  dispose()
})

test('普通模型及未显示的自动入口沿用宿主 null，不扩展兼容范围', () => {
  const definition: AssistantDefinition = {kind:'assistant-step', target:'chat', buildViewNode:()=>null}
  const dispose=retainAutomaticAttemptNode(fixture([definition]).registry)
  assert.equal(definition.buildViewNode!({current:new Map([['chat',node('普通模型推理')]])}),null)
  assert.equal(definition.buildViewNode!({current:new Map()}),null)
  dispose()
})

test('自动入口轮次过程撤回时保留同 key 隐藏节点，普通模型轮次不受影响', () => {
  const definition:AssistantDefinition={kind:'turn-process',target:'chat',buildViewNode:()=>null}
  const dispose=retainAutomaticAttemptNode(fixture([definition]).registry)
  const previous={...node(),kind:'turn-process',key:'turn-process:0',data:{turn:0}}
  const current=new Map([['chat',previous]])
  assert.equal(definition.buildViewNode!({current}),null)
  const next=definition.buildViewNode!({current,matches:[{event:{type:'assistant/live-chunk',
    data:{chunk:{type:'reasoning-delta',text:'正在预检并执行真实自动路由。\n'}}}}]})!
  assert.equal(next.key,previous.key)
  assert.equal(next.visibility,'hidden')
  assert.equal(previous.visibility,'visible')
  dispose()
})

test('失败自动轮次可以通过受控的持久化引用识别，不能使用普通文本冒充', () => {
  const definition:AssistantDefinition={kind:'turn-process',target:'chat',buildViewNode:()=>null}
  const dispose=retainAutomaticAttemptNode(fixture([definition]).registry)
  const previous={...node(),kind:'turn-process',data:{turn:0}},current=new Map([['chat',previous]])
  const steps=[{data:{get:(key:string)=>key==='refractagent-automatic-attempt'?{refs:[{id:'run'}]}:undefined}}]
  assert.equal(definition.buildViewNode!({current,matches:[{location:{turn:{steps}}}]})?.visibility,'hidden')
  assert.equal(definition.buildViewNode!({current,matches:[{event:{type:'assistant/live-chunk',
    data:{chunk:{type:'text-delta',text:'正在预检并执行真实自动路由。'}}}}]}),null)
  dispose()
})

test('宿主正常返回节点时不隐藏或改写成功、失败或历史投影', () => {
  const expected={...node(),data:{status:'settled'}}
  const definition: AssistantDefinition = {kind:'assistant-step', target:'chat', buildViewNode:()=>expected}
  const dispose=retainAutomaticAttemptNode(fixture([definition]).registry)
  assert.equal(definition.buildViewNode!({current:new Map([['chat',node()]])}),expected)
  dispose()
})

test('定义延后注册也有兼容，卸载恢复原函数和订阅', () => {
  const definitions: AssistantDefinition[]=[], f=fixture(definitions)
  const dispose=retainAutomaticAttemptNode(f.registry), original=()=>null
  const definition: AssistantDefinition={kind:'assistant-step', target:'chat',buildViewNode:original}
  definitions.push(definition);f.update()
  assert.notEqual(definition.buildViewNode,original)
  const patched=definition.buildViewNode;f.update()
  assert.equal(definition.buildViewNode,patched)
  dispose()
  assert.equal(definition.buildViewNode,original)
  assert.equal(f.listeners.size,0)
})

test('其他视图和后来替换的宿主函数不被本插件覆盖', () => {
  const original=()=>null, other:AssistantDefinition={kind:'tool', target:'chat',buildViewNode:original}
  const definition:AssistantDefinition={kind:'assistant-step',target:'chat',buildViewNode:original}
  const dispose=retainAutomaticAttemptNode(fixture([definition,other]).registry)
  assert.equal(other.buildViewNode,original)
  const later=()=>node();definition.buildViewNode=later
  dispose()
  assert.equal(definition.buildViewNode,later)
})

test('持久化失败 attempt 发布运行引用，刷新后不用伪造成功助手消息', () => {
  const definition=automaticAttemptDefinition(),id='20261009T050609Z-b237b206aee5'
  const event={type:'assistant/attempt',data:{turn:2,step:1,stream:[
    {type:'reasoning-chunks',texts:['正在预检并执行真实自动路由。\n',`【自动路由记录】${id}\n`]},
    {type:'chunk',chunk:{type:'finish',reason:{kind:'error',failure:{message:'质量未通过'}},
      replayState:{response:{refractagent:{runId:id}}}}},
  ]}}
  assert.equal(definition.match(event)?.role,'update')
  const state=definition.start({}, {event}), projection=definition.buildLocationData({state},'step')!
  assert.equal(projection.kind,'step')
  assert.deepEqual(projection.value.refs,[{id,turn:2,state:'interrupted',error:'质量未通过'}])
  assert.equal(definition.buildLocationData({state},'turn'),null)
  assert.equal('buildViewNode' in definition,false)
  const repeated=definition.update({state},{event})
  assert.equal(repeated.refs.length,1)
})

test('普通模型内容、用户标记和无效运行 ID 不产生失败轨迹引用', () => {
  const definition=automaticAttemptDefinition()
  assert.equal(definition.match({type:'user/message',data:{turn:0,step:0}}),null)
  const event={type:'assistant/attempt',data:{turn:0,step:0,stream:[
    {type:'reasoning-chunks',texts:['普通推理']},
    {type:'chunk',chunk:{type:'finish',replayState:{response:{refractagent:{runId:'../../private'}}}}},
  ]}}
  const state=definition.start({}, {event})
  assert.equal(state.refs.length,0)
  assert.equal(definition.buildLocationData({state},'step'),null)
})
