/** 规划路由受管图片工具：宿主负责 HTTP 与附件，Python 负责资格、预算和状态。 */
import { createHash } from 'node:crypto'
import type { AgentContext } from './agent-provider.js'
import type { ImageAttachmentRef } from './contracts.js'
import type { NativeAgent } from './native-tools.js'
import type { PlanningController } from './planning-routing.js'

type Json=Record<string,any>
const MAX_RESPONSE_BYTES=20*1024*1024

function object(value:unknown):value is Json{return value!==null&&typeof value==='object'&&!Array.isArray(value)}
function text(value:unknown,name:string,max=20000):string{
  if(typeof value!=='string'||!value.trim()||value.length>max)throw new Error(`${name} 无效`)
  return value
}
function imageRef(value:unknown):ImageAttachmentRef{
  if(!object(value)||typeof value.attachmentId!=='string'||typeof value.mediaType!=='string'
    ||!['image/png','image/jpeg','image/webp','image/gif'].includes(value.mediaType)
    ||!Number.isSafeInteger(value.bytes)||!Number.isSafeInteger(value.width)||!Number.isSafeInteger(value.height))
    throw new Error('参考图片引用无效')
  return value as ImageAttachmentRef
}
function outputHostAllowed(url:URL):boolean{
  return url.protocol==='https:'&&(url.hostname.endsWith('.volces.com')||url.hostname==='volces.com')
}
async function boundedBytes(response:Response):Promise<Uint8Array>{
  const length=Number(response.headers.get('content-length')??0)
  if(length>MAX_RESPONSE_BYTES)throw new Error('生成图片超过附件大小上限')
  const data=new Uint8Array(await response.arrayBuffer())
  if(data.byteLength>MAX_RESPONSE_BYTES)throw new Error('生成图片超过附件大小上限')
  return data
}
async function referenceData(ctx:AgentContext,refs:ImageAttachmentRef[],signal:AbortSignal):Promise<string[]>{
  if(!ctx.attachments)throw new Error('当前 DSH 未提供图片附件服务')
  return Promise.all(refs.map(async ref=>{
    const stored=await ctx.attachments!.readImage(ref,signal)
    return `data:${stored.ref.mediaType};base64,${Buffer.from(stored.data).toString('base64')}`
  }))
}

export function registerPlanningMediaTools(ctx:AgentContext,planning:PlanningController):void{
  if(!ctx.tools?.register)return
  ctx.tools.register({
    name:'refract_generate_image',
    description:'使用规划路由设置中已验收的图片路线生成或编辑图片。结果保存为 DSH 持久图片附件。',
    parameters:{type:'object',additionalProperties:false,required:['prompt'],properties:{
      prompt:{type:'string',description:'图片内容或编辑要求'},
      routeId:{type:'string',description:'可选的已配置媒体路线 ID'},
      size:{type:'string',enum:['2K','3K','4K','2048x2048','4096x4096']},
      count:{type:'integer',minimum:1,maximum:4},
      references:{type:'array',maxItems:10,items:{type:'object',required:['attachmentId','mediaType','bytes','width','height'],properties:{
        attachmentId:{type:'string'},mediaType:{type:'string'},bytes:{type:'integer'},width:{type:'integer'},height:{type:'integer'},name:{type:'string'}}}},
    }},
    output:{schema:{type:'object'},render:(_args:unknown,value:Json)=>[
      {type:'text',text:`图片生成完成：${String(value.model)}；操作 ${String(value.operationId)}`},
      ...((value.images??[]) as ImageAttachmentRef[]).map(attachment=>({type:'image',attachment})),
    ]},
    async execute(raw:unknown,exec:{signal:AbortSignal;agent?:NativeAgent}){
      if(!object(raw)||!exec.agent)throw new Error('图片工具缺少参数或可信 Agent 身份')
      const prompt=text(raw.prompt,'prompt')
      const count=raw.count??1
      if(!Number.isSafeInteger(count)||count<1||count>4)throw new Error('count 必须为 1 到 4')
      const size=raw.size??'2K'
      if(!['2K','3K','4K','2048x2048','4096x4096'].includes(size))throw new Error('size 不受支持')
      const references=Array.isArray(raw.references)?raw.references.map(imageRef):[]
      const operation=references.length?'image-edit':'image-generate'
      const requestHash=createHash('sha256').update(JSON.stringify({prompt,count,size,
        references:references.map(ref=>ref.attachmentId)})).digest('hex')
      const reserved=await planning.reserveMedia(exec.agent,{routeId:raw.routeId,operation,maxUnits:count,requestHash,
        input:{prompt,references:references.map(ref=>({attachmentId:ref.attachmentId,mediaType:ref.mediaType,
          bytes:ref.bytes,width:ref.width,height:ref.height}))}})
      const operationId=String(reserved.operationId),route=reserved.route as Json
      const endpoint=text(route.endpoint,'媒体 endpoint',1000).replace(/\/+$/,'')
      if(route.billingUnit==='AFP'&&endpoint!=='https://ark.cn-beijing.volces.com/api/plan/v3'){
        await planning.updateMedia(exec.agent,{operationId,status:'cancelled',actualUnits:0})
        throw new Error('AFP 图片路线必须使用 Ark Agent Plan 专属端点')
      }
      let apiKey:string,images:string[]
      try{
        apiKey=await planning.mediaCredential(String(route.credentialProvider??route.provider))
        images=references.length?await referenceData(ctx,references,exec.signal):[]
      }catch(error){
        // 尚未向提供方派发，可以安全释放预留。
        await planning.updateMedia(exec.agent,{operationId,status:'cancelled',actualUnits:0}).catch(()=>{})
        throw error
      }
      await planning.updateMedia(exec.agent,{operationId,status:'submitted'})
      let response:Response
      try{response=await fetch(`${endpoint}/images/generations`,{method:'POST',signal:exec.signal,
        headers:{'content-type':'application/json',authorization:`Bearer ${apiKey}`},body:JSON.stringify({
          model:route.model,prompt,size,response_format:'url',sequential_image_generation:'disabled',
          ...(images.length?{image:images}:{}),...(count>1?{sequential_image_generation:'auto',
            sequential_image_generation_options:{max_images:count}}:{})})})}
      catch(error){await planning.updateMedia(exec.agent,{operationId,status:'unknown'}).catch(()=>{})
        throw new Error(`图片提交结果不明；不会自动重发：${error instanceof Error?error.message:String(error)}`)}
      let payload:unknown
      try{payload=await response.json()}catch{payload=undefined}
      if(!response.ok||!object(payload)||!Array.isArray(payload.data)||payload.data.length===0){
        await planning.updateMedia(exec.agent,{operationId,status:'unknown'}).catch(()=>{})
        throw new Error(`图片生成返回不可核对结果（HTTP ${response.status}）；不会自动重发`)
      }
      if(!ctx.attachments){await planning.updateMedia(exec.agent,{operationId,status:'unknown'}).catch(()=>{})
        throw new Error('当前 DSH 未提供图片附件服务，生成结果无法持久保存')}
      let refs:readonly ImageAttachmentRef[]
      try{
        const generated=await Promise.all(payload.data.map(async(item:unknown,index:number)=>{
          if(!object(item)||typeof item.url!=='string')throw new Error('图片结果缺少 URL')
          const url=new URL(item.url);if(!outputHostAllowed(url))throw new Error('图片结果来源域不受信任')
          const file=await fetch(url,{signal:exec.signal});if(!file.ok)throw new Error(`图片下载失败（HTTP ${file.status}）`)
          const mediaType=(file.headers.get('content-type')??'image/png').split(';')[0]
          if(!['image/png','image/jpeg','image/webp','image/gif'].includes(mediaType))throw new Error('图片结果格式不受支持')
          return {data:await boundedBytes(file),mediaType:mediaType as ImageAttachmentRef['mediaType'],name:`generated-${index+1}.${mediaType.split('/')[1]}`}
        }))
        refs=await ctx.attachments.saveImages(generated)
      }catch(error){
        await planning.updateMedia(exec.agent,{operationId,status:'unknown'}).catch(()=>{})
        throw new Error(`图片已生成但产物下载或附件保存失败；不会重新生成：${error instanceof Error?error.message:String(error)}`)}
      await planning.updateMedia(exec.agent,{operationId,status:'succeeded',actualUnits:refs.length,
        artifacts:refs.map(ref=>({attachmentId:ref.attachmentId,mediaType:ref.mediaType,bytes:ref.bytes}))})
      return {operationId,model:route.model,images:refs,usage:{basis:'image',actualUnits:refs.length}}
    },
  })
}
