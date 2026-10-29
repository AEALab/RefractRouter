import assert from 'node:assert/strict'
import test from 'node:test'
import { registerExperimentalNodeTools } from '../dist/node-tools.js'
import { PlanningController } from '../dist/planning-routing.js'

const schema={name:'refract_expert',description:'核心定义',parameters:{type:'object'}}

test('节点工具保持 Python 定义且原样传递宿主身份、callId 和参数，卸载会注销',async()=>{
  let tool:any,disposed=false
  const controller:any={activateNodeTools(p:any){assert.equal(p.maxTools,2)},async enableNodeTools(p:any){assert.equal(p.enabled,true);return {tools:[schema],limits:{maxTools:2}}},
    async executeNodeTool(...args:any[]){assert.deepEqual(args,[agent,'call-1',schema.name,input,signal]);return {artifact:'结果'}}}
  const ctx:any={tools:{register(t:any){tool=t;return ()=>{disposed=true}}}}
  const agent:any={id:'a'},input={intent:'analyze',task:'任务',context:'材料'},signal=new AbortController().signal
  const dispose=await registerExperimentalNodeTools(ctx,controller,{enabled:true},()=>[])
  assert.equal(tool.name,schema.name)
  assert.deepEqual(tool.parameters,schema.parameters)
  assert.deepEqual(await tool.execute(input,{agent,callId:'call-1',signal}),{artifact:'结果'})
  await assert.rejects(()=>tool.execute(input,{callId:'c',signal}),/Agent/)
  dispose();assert.equal(disposed,true)
})

test('工具冲突和合计数量限制发生在宿主注册之前',async()=>{
  for(const existing of [[schema],[{...schema,name:'read'},{...schema,name:'bash'}]]){
    const ctx:any={tools:{register(){assert.fail('不应注册工具')}}}
    const controller:any={async enableNodeTools(){return {tools:[schema],limits:{maxTools:2}}}}
    await assert.rejects(()=>registerExperimentalNodeTools(ctx,controller,{enabled:true},()=>existing),/冲突|上限/)
  }
})

test('未启用实验时不能执行节点，也不会产生模型调用',async()=>{
  let calls=0
  const ctx:any={llm:{async *stream(){calls++;throw new Error('禁止调用')}},tools:{},
    effect(){},agents:{},credentials:{},subprocess:{},sandbox:{},sandboxPolicy:{}}
  const rpc:any={async request(){assert.fail('未启用时不应访问核心')},dispose(){}}
  const controller=new PlanningController(ctx,()=>({} as any),rpc)
  await assert.rejects(()=>controller.executeNodeTool({} as any,'c','refract_expert',{},new AbortController().signal),/未启用/)
  assert.equal(calls,0)
})
