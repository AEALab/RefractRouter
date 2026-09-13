import assert from 'node:assert/strict'
import { pathToFileURL } from 'node:url'
import { resolve } from 'node:path'
// 指定已安装 DSH 的 node_modules；此脚本仅运行内存模拟工具，不联网。
if (!process.argv[2]) throw new Error('请传入已安装 DSH 的 node_modules 目录')
const base=resolve(process.argv[2], '@deepseek-ai')+'/'
const {Context}=await import(pathToFileURL(base+'cordis/lib/index.js').href)
const {SystemPrompt}=await import(pathToFileURL(base+'dsh-system-prompt/lib/index.js').href)
const {Session}=await import(pathToFileURL(base+'dsh-session/lib/index.js').href)
const {ToolRuntime}=await import(pathToFileURL(base+'dsh-tools/lib/index.js').href)
const {bindNativeTools}=await import(pathToFileURL(resolve(process.argv[3] ?? resolve(import.meta.dirname, '../dist/native-tools.js'))).href)
const ctx=new Context()
new SystemPrompt(ctx,{})
new ToolRuntime(ctx)
let executed=0
ctx.tools.register({name:'fixture',description:'零网络模拟工具',parameters:{type:'object',properties:{},additionalProperties:false},
  output:{schema:{type:'string'},render:(value)=>[{type:'text',text:value}]},
  execute:async(args,exec)=>{executed++;exec.deferContext({id:'context',role:'user',source:{kind:'plugin',plugin:'fixture'},content:[{type:'text',text:'模拟技能说明'}]});return 'fixture-result'} })
const session=Session.create('refractagent-offline-fixture')
session.append('step/start',{turn:1,step:1})
assert.throws(()=>session.append('tool/result',{}),/requires a surfaceOp marker/)
const agent={ctx,session}
const schemas=ctx.tools.schemas()
const bind=()=>bindNativeTools({tools:ctx.tools,agents:{requireInitiator:()=>agent}},schemas)
const request={protocol:'refractrouter-tools/v1',type:'request',id:'1',node:'test',call:{id:'test',type:'function',function:{name:'fixture',arguments:'{}'}}}
const first=await bind().execute(request,new AbortController().signal)
assert.equal(first.result.isError,false)
assert.equal(executed,1)
assert.equal(first.result.additionalContexts[0].content[0].text,'模拟技能说明')
let asked=0
ctx.provide('approval',{async request(input){asked++;assert.equal(input.agent,agent);return 'rejected'}})
ctx.on('tools/pre-execute',async()=>({kind:'ask',reason:'离线审批拒绝测试'}))
const denied=await bind().execute({...request,id:'2',call:{...request.call,id:'second'}},new AbortController().signal)
assert.equal(asked,1)
assert.equal(executed,1)
assert.equal(denied.result.isError,true)
assert.match(JSON.stringify(denied.result.content),/rejected/)

assert.equal(session.events.filter(e=>e.type==='refractagent/tool-result').length,2)
assert.equal(session.events.some(e=>e.type==='tool/call'||e.type==='tool/result'),false)
assert.equal(session.surface.nodes.length,0)

const throwing=bindNativeTools({agents:{requireInitiator:()=>agent},tools:{async execute(){throw new Error('fixture failure')}}},schemas)
await assert.rejects(throwing.execute({...request,id:'3'},new AbortController().signal),/fixture failure/)
assert.equal(session.events.filter(e=>e.type==='refractagent/tool-result').length,3)
assert.equal(session.surface.nodes.length,0)
console.log('PASS: real DSH Session and ToolRuntime; success, denial, exception; unchanged outer surface')
