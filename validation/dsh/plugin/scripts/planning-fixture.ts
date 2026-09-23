/** 本地验收专用模型与工具：无网络、无凭证，不随产品包发布。 */
export const inject=['llm','tools']
export function apply(ctx:any){
  ctx.tools.register({name:'refract_fixture',description:'离线验收工具，返回固定字符串',
    parameters:{type:'object',properties:{},additionalProperties:false},
    output:{schema:{type:'string'},render:(_args:unknown,value:string)=>[{type:'text',text:value}]},
    execute:async()=> '离线工具已完成'})
  const info=(provider:string,model:string)=>({provider,id:model,name:'离线验收 '+model,
    inputModalities:['text'],context:{contextWindow:1000000},defaultMaxTokens:1024})
  const adapter={
    providerInfo:(provider:string)=>({id:provider,name:'Refract 离线验收'}),
    providerRetryPolicy:()=>({mode:'normal',maxRetries:0,retryableCodes:[]}),
    listModels:async(provider:string)=>['small','large','judge'].map(m=>info(provider,m)),
    resolveModel:async(provider:string,model:string)=>info(provider,model),
    prepareCall:async(provider:string,model:string)=>({model:info(provider,model),stream:adapter.stream}),
    async *stream(options:any){
      const prompt=JSON.stringify(options.messages)
      let text=''
      if(prompt.includes('p_solve'))text='{"p_solve":0.9,"capability_boundary":"supported","crux":"离线工具读取"}'
      else if(prompt.includes('APPROVE|REDO'))text='{"verdict":"APPROVE","feedback":"轨迹包含两次工具回执"}'
      else if(prompt.includes('escalate'))text='{"escalate":false,"reason":"工具正常完成"}'
      else if(options.purpose==='compaction')text='离线任务仍需完成工具验收。'
      const results=options.messages.flatMap((m:any)=>Array.isArray(m.content)?m.content:[]).filter((b:any)=>b.type==='tool-result')
      let hasTool=false
      if(!text&&results.length<2){
        const direct=options.tools?.find((t:any)=>t.name==='refract_fixture')
        const code=options.tools?.find((t:any)=>t.name==='run_code')
        if(direct||code){
          const name=direct?'refract_fixture':'run_code'
          const args=direct?'{}':JSON.stringify({code:'return await tools.refract_fixture({})',description:'离线工具验收'})
          yield {type:'block-start',index:0,blockType:'tool-call'}
          yield {type:'tool-call-delta',index:0,id:'fixture-'+results.length,name,argumentsDelta:args}
          yield {type:'block-end',index:0,block:{type:'tool-call',id:'fixture-'+results.length,name,arguments:args}}
          hasTool=true
        }else text='未发现离线验收工具。'
      }
      if(!text&&!hasTool)text='离线验收完成：宿主已完成两轮原生工具交互。'
      if(text){
        yield {type:'block-start',index:0,blockType:'text'}
        yield {type:'text-delta',index:0,text}
        yield {type:'block-end',index:0,block:{type:'text',text}}
      }
      yield {type:'usage',usage:{inputTokens:100,outputTokens:30}}
      yield {type:'finish',reason:{kind:hasTool?'tool-calls':'stop'}}
    }}
  ctx.llm.registerAdapter(['refract-fixture'],adapter)
}
