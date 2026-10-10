import {traceDuration} from './trace-record.js'

export type FlowTone='active'|'waiting'|'ok'|'discarded'|'failed'|'neutral'
export interface RouteFlowNode {
  id:string;title:string;model:string;status:string;tone:FlowTone;details:string[];independent?:boolean
}
const COLORS:Record<FlowTone,string>={active:'#60a5fa',waiting:'#fbbf24',ok:'#34d399',
  discarded:'#c4b5fd',failed:'#fb7185',neutral:'#94a3b8'}

/** 图中只排列已有调用，不推导工具依赖、升级结论或尚未派发的步骤。 */
export function RouteFlow({identity,nodes,state,running=false,orderLabel='调用记录顺序'}:{
  identity:string;nodes:RouteFlowNode[];state:string;running?:boolean;orderLabel?:string
}) {
  const marker=`refract-route-arrow-${identity.replace(/[^a-zA-Z0-9-]/g,'-')}`
  const height=Math.max(160,nodes.length*190-24)
  const clip=(value:string,length:number)=>value.length>length?`${value.slice(0,length)}…`:value
  return <section aria-label="路由调用流程">
    <h4>路由调用流程</h4>
    <p role="status">{state}{running?' · 每 2.5 秒刷新已保存状态':''}。</p>
    <p style={{fontSize:12,opacity:.75}}>箭头表示{orderLabel}，不表示 DAG 依赖或并发完成顺序。模型、接受／丢弃和审核状态以核心记录为准。</p>
    {nodes.some(n=>n.independent)&&<p style={{fontSize:12,opacity:.75}}>独立结构判别未归入主调用账本，单独显示，不与主账本绘制顺序连线。</p>}
    {!nodes.length?<p>尚无可展示的调用记录；等待选模或预检结果，不补造执行步骤。</p>:
      <div style={{overflow:'auto',maxHeight:640,borderRadius:16,background:'#111827',padding:8}}>
        <svg role="img" aria-label={`路由调用流程图，${nodes.length} 条调用记录，${state}`} viewBox={`0 0 640 ${height}`}
          width="100%" height={height} style={{display:'block',minWidth:440}}>
          <title>{`路由调用流程：${orderLabel}；${state}`}</title>
          <defs><marker id={marker} viewBox="0 0 10 10" refX={9} refY={5} markerWidth={7} markerHeight={7} orient="auto">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8"/>
          </marker></defs>
          {nodes.slice(1).map((n,index)=>!n.independent&&!nodes[index].independent&&<path key={`edge-${n.id}`} d={`M 320 ${index*190+162} L 320 ${index*190+190}`}
            fill="none" stroke="#94a3b8" strokeWidth={2} markerEnd={`url(#${marker})`}/>)}
          {nodes.map((n,index)=><g key={n.id} transform={`translate(20,${index*190+8})`}>
            <title>{`${index+1}. ${n.title}\n${n.model}\n${n.status}\n${n.details.join('\n')}`}</title>
            <rect width={600} height={154} rx={14} fill="#1e293b" stroke={COLORS[n.tone]} strokeWidth={2}
              strokeDasharray={n.tone==='waiting'?'7 4':undefined}/>
            <circle cx={18} cy={25} r={5} fill={COLORS[n.tone]}/>
            <text x={32} y={30} fill="#f8fafc" fontSize={15} fontWeight={600}>{clip(`${index+1}. ${n.title}`,40)}</text>
            <text x={16} y={55} fill="#e2e8f0" fontSize={13}>{clip(n.model,69)}</text>
            <text x={16} y={80} fill={COLORS[n.tone]} fontSize={13}>{clip(n.status,52)}</text>
            {n.details.slice(0,2).map((line,i)=><text key={i} x={16} y={105+i*23} fill="#cbd5e1" fontSize={12}>{clip(line,65)}</text>)}
          </g>)}
        </svg>
      </div>}
  </section>
}
export function flowLatency(value:unknown):string {
  return typeof value==='number'&&Number.isFinite(value)&&value>=0?traceDuration(value):'未记录'
}

// 用量未确认在派发时就写入账本；任务仍运行时显示等待，不把它当成已结算或失败。
export function flowTone(status:string|undefined,disposition:string|undefined,running:boolean):FlowTone {
  if(disposition==='failed'||status==='failed')return 'failed'
  if(disposition==='discarded')return 'discarded'
  if(status==='unknown-usage')return running&&disposition!=='failed'?'active':'failed'
  if(status==='reserved')return 'waiting'
  if(disposition==='buffered')return 'waiting'
  if(disposition==='accepted'||disposition==='consult'||status==='billed')return 'ok'
  if(disposition==='pending')return running?'active':'neutral'
  return 'neutral'
}
