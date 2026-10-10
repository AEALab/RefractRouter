import type {ReactNode} from 'react'

export interface TraceTiming {startedAt?:string;finishedAt?:string|null;elapsedMs?:number}

export function automaticStartedAt(id:string):string|undefined {
  const match=/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z-/.exec(id)
  if(!match)return
  const iso=`${match[1]}-${match[2]}-${match[3]}T${match[4]}:${match[5]}:${match[6]}.000Z`
  const date=new Date(iso)
  return Number.isFinite(date.getTime())&&date.toISOString()===iso?iso:undefined
}

export function traceTimestamp(value:unknown,timeZone?:string):string {
  if(typeof value!=='string'||!value)return '未记录'
  const date=new Date(value)
  if(!Number.isFinite(date.getTime()))return '未记录'
  const parts=new Intl.DateTimeFormat('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit',
    hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23',...(timeZone?{timeZone}:{})}).formatToParts(date)
  const part=(type:string)=>parts.find(p=>p.type===type)?.value??''
  return `${part('year')}-${part('month')}-${part('day')} ${part('hour')}:${part('minute')}:${part('second')}`
}

export function traceDuration(value:unknown):string {
  if(typeof value!=='number'||!Number.isFinite(value)||value<0)return '未记录'
  if(value<1000)return `${Math.round(value)} 毫秒`
  if(value<60000)return `${(value/1000).toFixed(1)} 秒`
  const seconds=Math.floor(value/1000),minutes=Math.floor(seconds/60)
  if(minutes<60)return `${minutes} 分 ${seconds%60} 秒`
  return `${Math.floor(minutes/60)} 小时 ${minutes%60} 分 ${seconds%60} 秒`
}

// 不控制 open 属性：证据刷新时保留用户的展开状态，原生 summary 支持键盘操作。
export function TraceRecord({title,identity,startedAt,elapsedMs,running=false,timeLabel='开始时间',children}:{
  title:string;identity:string;startedAt?:string;elapsedMs?:number;running?:boolean;timeLabel?:string;children:ReactNode
}) {
  const start=startedAt?new Date(startedAt).getTime():NaN
  const elapsed=running&&Number.isFinite(start)?Math.max(elapsedMs??0,Date.now()-start):elapsedMs
  return <details className="rra-trace-record" style={{border:'1px solid var(--border-color, #8884)',borderRadius:12,marginBottom:12}}>
    <summary style={{cursor:'pointer',padding:'16px 18px',overflowWrap:'anywhere'}}>
      <span style={{fontWeight:600}}>{title}</span>
      <span style={{display:'block',fontSize:13,marginTop:6}}>{timeLabel}：{traceTimestamp(startedAt)}（本地时间） · {running?'已运行':'总耗时'}：{traceDuration(elapsed)}</span>
      <span style={{display:'block',fontSize:12,marginTop:4,opacity:.7}}>{identity}</span>
    </summary>
    <div style={{padding:'0 18px 18px',overflowX:'auto'}}>{children}</div>
  </details>
}
