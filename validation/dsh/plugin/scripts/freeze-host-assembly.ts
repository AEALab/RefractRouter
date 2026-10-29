/** 从明确指定的已安装 DSH SDK 生成组装回归数据；不读取仓库内容或调用模型。 */
import { readFile,writeFile } from 'node:fs/promises'
import { pathToFileURL } from 'node:url'
import { createHash } from 'node:crypto'

const [modulePath,packagePath,outputPath]=process.argv.slice(2)
if(!modulePath||!packagePath||!outputPath)throw new Error('需要SDK模块、package.json及新输出路径')
const {BlockAssembler}=await import(pathToFileURL(modulePath).href)
const cases=[
  {name:'结束块覆盖不同的增量',chunks:[{type:'text-delta',index:0,text:'2'},
    {type:'block-end',index:0,block:{type:'text',text:'3'}}],finish:'stop'},
  {name:'部分文本块只有结束块',chunks:[{type:'text-delta',index:0,text:'前文'},
    {type:'block-end',index:0,block:{type:'text',text:'前文'}},
    {type:'block-end',index:1,block:{type:'text',text:'后文😀'}}],finish:'stop'},
  {name:'仅增量协议',chunks:[{type:'text-delta',index:0,text:'中'},
    {type:'text-delta',index:0,text:'文😀'}],finish:'stop'},
  {name:'已结束块忽略后续非法增量',chunks:[{type:'block-end',index:0,block:{type:'text',text:'完成'}},
    {type:'text-delta',index:0,text:'不应追加'}],finish:'stop'},
  {name:'按首次出现顺序组装',chunks:[{type:'block-start',index:8,blockType:'text'},
    {type:'block-start',index:1,blockType:'text'},
    {type:'block-end',index:1,block:{type:'text',text:'后'}},
    {type:'block-end',index:8,block:{type:'text',text:'先'}}],finish:'stop'},
  {name:'工具参数只有增量',chunks:[{type:'tool-call-delta',index:0,id:'call-1',name:'read',argumentsDelta:'{"p":'},
    {type:'tool-call-delta',index:0,id:'call-1',argumentsDelta:'"文"}'}],finish:'tool-calls'},
  {name:'截断丢弃不安全工具',chunks:[{type:'block-end',index:0,block:{type:'tool-call',id:'call-1',name:'read',arguments:'{}'}},
    {type:'text-delta',index:1,text:'未完'}],finish:'max-tokens'},
]
const packageInfo=JSON.parse(await readFile(packagePath,'utf8'))
const fixtures=cases.map(item=>{
  const assembler=new BlockAssembler()
  for(const chunk of item.chunks)assembler.push(chunk)
  assembler.push({type:'finish',reason:{kind:item.finish}})
  const blocks=assembler.blocks() as Record<string,any>[]
  return {...item,expected:{content:blocks.filter(b=>b.type==='text').map(b=>b.text).join(''),
    toolCalls:blocks.filter(b=>b.type==='tool-call'),finishReason:item.finish==='tool-calls'?'tool_calls':item.finish}}
})
const content={schemaVersion:'dsh-assembly-fixtures-v1',package:packageInfo.name,version:packageInfo.version,
  moduleSha256:createHash('sha256').update(await readFile(modulePath)).digest('hex'),fixtures}
await writeFile(outputPath,JSON.stringify(content,null,2)+'\n',{flag:'wx'})
