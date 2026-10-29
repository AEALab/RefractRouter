/** 按宿主 BlockAssembler 的首次出现顺序投影规范候选；block-end 覆盖增量。 */
type Json=Record<string,any>
interface Partial {kind:string;text:string;id?:string;name?:string;arguments:string;block?:Json}
export function dshCandidate(chunks:readonly Json[],finishReason:unknown):Json{
  const partials=new Map<number|undefined,Partial>()
  function ensure(chunk:Json,kind:string):Partial{
    const index=chunk.index as number|undefined
    if(index!==undefined&&(!Number.isSafeInteger(index)||index<0))throw new Error('DSH 内容块索引无效')
    let partial=partials.get(index)
    if(!partial){partial={kind,text:'',arguments:''};partials.set(index,partial)}
    return partial
  }
  for(const chunk of chunks){
    if(chunk.type==='block-start')ensure(chunk,String(chunk.blockType??chunk.block?.type))
    else if(chunk.type==='text-delta'||chunk.type==='reasoning-delta'){
      const partial=ensure(chunk,chunk.type==='text-delta'?'text':'reasoning')
      if(!partial.block)partial.text+=String(chunk.text)
    }else if(chunk.type==='tool-call-delta'){
      const partial=ensure(chunk,'tool-call')
      if(!partial.block){partial.id=chunk.id;if(chunk.name)partial.name=chunk.name;partial.arguments+=String(chunk.argumentsDelta)}
    }else if(chunk.type==='block-end'){
      const partial=ensure(chunk,String(chunk.block?.type))
      if(!partial.block)partial.block=chunk.block as Json
    }
  }
  const blocks=[...partials.entries()].map(([index,p])=>p.block??(p.kind==='tool-call'
    ?{type:'tool-call',id:p.id??`call-${index}`,name:p.name??'',arguments:p.arguments}
    :p.kind==='text'||p.kind==='reasoning'?{type:p.kind,text:p.text}:(()=>{throw new Error('未知的未结束DSH内容块')})()))
  return {content:blocks.filter(b=>b.type==='text').map(b=>b.text).join(''),
    toolCalls:finishReason==='max-tokens'?[]:blocks.filter(b=>b.type==='tool-call'),
    finishReason:finishReason==='tool-calls'?'tool_calls':finishReason}
}
