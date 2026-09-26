import assert from 'node:assert/strict'
import test from 'node:test'
import { registerPlanningMediaTools } from '../dist/media-tools.js'

const agent={id:'agent-1',session:{header:{id:'session-1'},events:[{type:'step/start',data:{turn:1,step:0}}],append(){}}}

test('受管图片工具先取得 Python 预算，生成后保存 DSH 附件并按实际张数结算',async()=>{
  let tool:any
  const updates:any[]=[]
  const ref={attachmentId:'sha256:image',mediaType:'image/png',bytes:3,width:1,height:1}
  const ctx:any={tools:{register(value:any){tool=value}},attachments:{
    async saveImages(inputs:any[]){assert.equal(inputs.length,1);return [ref]},
    async readImage(){throw new Error('不应读取参考图')},
  }}
  const planning:any={
    async reserveMedia(_agent:unknown,input:any){assert.equal(input.operation,'image-generate');assert.equal(input.maxUnits,1)
      assert.equal(input.input.prompt,'生成公开风景');return {operationId:'op-1',route:{id:'seedream',provider:'ark-plan',
        model:'doubao-seedream-5.0-lite',billingUnit:'AFP',endpoint:'https://ark.cn-beijing.volces.com/api/plan/v3'}}},
    async updateMedia(_agent:unknown,input:any){updates.push(input);return input},
    async mediaCredential(){return 'secret-key'},
  }
  registerPlanningMediaTools(ctx,planning)
  assert.equal(tool.name,'refract_generate_image')
  const original=globalThis.fetch
  let requests=0
  globalThis.fetch=(async(input:any,init?:any)=>{
    requests++
    if(requests===1){
      assert.equal(String(input),'https://ark.cn-beijing.volces.com/api/plan/v3/images/generations')
      assert.equal(init.headers.authorization,'Bearer secret-key')
      return new Response(JSON.stringify({data:[{url:'https://artifact.volces.com/image.png'}]}),{
        status:200,headers:{'content-type':'application/json'}})
    }
    assert.equal(String(input),'https://artifact.volces.com/image.png')
    return new Response(new Uint8Array([1,2,3]),{status:200,headers:{'content-type':'image/png'}})
  }) as typeof fetch
  try{
    const result=await tool.execute({prompt:'生成公开风景',count:1},{signal:new AbortController().signal,agent})
    assert.equal(result.images[0].attachmentId,'sha256:image')
    assert.deepEqual(updates.map(row=>row.status),['submitted','succeeded'])
    assert.equal(updates[1].actualUnits,1)
    const blocks=tool.output.render({},result)
    assert.equal(blocks[1].type,'image')
  }finally{globalThis.fetch=original}
})

test('图片提交结果不明只派发一次并标记 unknown',async()=>{
  let tool:any
  const updates:any[]=[]
  const ctx:any={tools:{register(value:any){tool=value}},attachments:{}}
  const planning:any={
    async reserveMedia(){return {operationId:'op-2',route:{provider:'ark-plan',model:'seedream',billingUnit:'AFP',
      endpoint:'https://ark.cn-beijing.volces.com/api/plan/v3'}}},
    async updateMedia(_agent:unknown,input:any){updates.push(input);return input},
    async mediaCredential(){return 'secret-key'},
  }
  registerPlanningMediaTools(ctx,planning)
  const original=globalThis.fetch
  let requests=0
  globalThis.fetch=(async()=>{requests++;throw new Error('connection reset')}) as typeof fetch
  try{
    await assert.rejects(tool.execute({prompt:'生成图片'},{signal:new AbortController().signal,agent}),/不会自动重发/)
    assert.equal(requests,1)
    assert.deepEqual(updates.map(row=>row.status),['submitted','unknown'])
  }finally{globalThis.fetch=original}
})

test('凭证或参考图在派发前失败会取消并释放预留',async()=>{
  let tool:any
  const updates:any[]=[]
  const ctx:any={tools:{register(value:any){tool=value}},attachments:{}}
  const planning:any={
    async reserveMedia(){return {operationId:'op-3',route:{provider:'ark-plan',credentialProvider:'ark',
      model:'seedream',billingUnit:'AFP',endpoint:'https://ark.cn-beijing.volces.com/api/plan/v3'}}},
    async updateMedia(_agent:unknown,input:any){updates.push(input);return input},
    async mediaCredential(provider:string){assert.equal(provider,'ark');throw new Error('凭证不可用')},
  }
  registerPlanningMediaTools(ctx,planning)
  await assert.rejects(tool.execute({prompt:'生成图片'},{signal:new AbortController().signal,agent}),/凭证不可用/)
  assert.deepEqual(updates,[{operationId:'op-3',status:'cancelled',actualUnits:0}])
})
