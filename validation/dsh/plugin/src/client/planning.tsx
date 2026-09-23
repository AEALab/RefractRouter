import { useEffect, useState, useRef, useSyncExternalStore } from 'react'
import { EMPTY_PLANNING, PLANNING_NAMES, validatePlanningShape, type PlanningConfig, type PlanningStrategy } from '../planning-config.js'
import type { CardScope } from '../settings-card.js'
import type { ClientContext, DshModelCatalog } from './types.js'

type Report={valid?:boolean;issues?:string[];defaultStrategy?:string;coverage?:string;
  strategies?:Array<{id:string;name:string;available:boolean;issues:string[]}>}
export interface PlanningUi {
  scope:CardScope
  preview():Promise<Report>
  simulate():Promise<{message:string;simulatedCalls:number;models:string[]}>
  loadCatalog():Promise<DshModelCatalog>
}
const HELP:Record<PlanningStrategy,string>={
  stage:'根据工具执行轨迹调整模型，不额外调用判别模型。',
  task:'开始时判别任务难度，当前任务保持选定模型。',
  composite:'任务判别确定默认模型，再根据执行轨迹调整。',
  advisor:'执行器准备结束时审核，必要时有界返工。',
  escalation:'审核高效模型回复，连续困难时切换并锁定强模型。',
  static:'固定执行模型，或使用保存种子的随机对照。'}
const ROLES={efficient:'高效执行模型',capable:'强执行模型',classifier:'任务／升级判别模型',advisor:'审核模型'} as const
function errorText(e:unknown){return e instanceof Error?e.message:String(e)}
export function PlanningSettings({scope,preview,loadCatalog,simulate}:PlanningUi){
  const snapshot=useSyncExternalStore(cb=>scope.subscribe(cb),()=>scope.getSnapshot())
  const saved=snapshot.value?.planningRouting??EMPTY_PLANNING
  const [draft,setDraft]=useState<PlanningConfig>(()=>structuredClone(saved))
  const [dirty,setDirty]=useState(false),[busy,setBusy]=useState(false),[status,setStatus]=useState('')
  const [report,setReport]=useState<Report>(),[catalog,setCatalog]=useState<DshModelCatalog>()
  const [advanced,setAdvanced]=useState('')
  useEffect(()=>{if(!dirty)setDraft(structuredClone(saved))},[saved,dirty])
  useEffect(()=>{void loadCatalog().then(setCatalog).catch(e=>setStatus(errorText(e)))},[loadCatalog])
  function patch(value:Partial<PlanningConfig>){setDraft(v=>({...v,...value}));setDirty(true);setReport(undefined)}
  async function save(){
    setBusy(true);setStatus('')
    try{await scope.set('planningRouting',JSON.parse(JSON.stringify(draft)));setDirty(false);setReport(await preview());setStatus('已保存；现有任务继续使用启动时配置。')}
    catch(e){setStatus(errorText(e))}finally{setBusy(false)}
  }
  function rolePatch(role:keyof typeof ROLES,value:Partial<NonNullable<PlanningConfig['models']>[number]>){
    const id=draft.roles?.[role]??role
    const previous=draft.models?.find(m=>m.id===id)
    const model={id,provider:'',model:'',contextWindow:32000,maxOutputTokens:2048,
      inputPer1k:Number.NaN,outputPer1k:Number.NaN,deployment:'external-cloud',...previous,...value}
    patch({roles:{...draft.roles,[role]:id},models:[...(draft.models??[]).filter(m=>m.id!==id),model]})
  }
  return <section aria-label="规划路由设置" style={{borderTop:'1px solid #8885',padding:'16px 0',lineHeight:1.7}}>
    <h3>规划路由</h3><p>保留 DSH 原生工具、审批与委派。凭证沿用宿主模型目录；费用仅覆盖当前受管 Agent。</p>
    <label><input type="checkbox" checked={draft.enabled} onChange={e=>patch({enabled:e.target.checked})}/>启用独立规划路由</label>
    <div><label>新会话默认策略 <select value={draft.defaultStrategy??'stage'} onChange={e=>patch({defaultStrategy:e.target.value as PlanningStrategy})}>
      {Object.entries(PLANNING_NAMES).map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></label></div>
    <label>生产预算 <input type="number" min="0" step="any" value={draft.maxProductionCost??''}
      onChange={e=>patch({maxProductionCost:e.target.value===''?undefined:Number(e.target.value)})}/></label>
    <label>计费单位 <select value={draft.billingUnit??'USD'} onChange={e=>patch({billingUnit:e.target.value as PlanningConfig['billingUnit']})}>
      <option>USD</option><option>AFP</option><option>CNY</option></select></label>
    <div><label>任务期限（毫秒） <input type="number" value={draft.timeoutMs??300000} onChange={e=>patch({timeoutMs:Number(e.target.value)})}/></label>
      <label>最大调用数 <input type="number" value={draft.maxCalls??128} onChange={e=>patch({maxCalls:Number(e.target.value)})}/></label></div>
    {Object.entries(ROLES).map(([r,label])=>{
      const role=r as keyof typeof ROLES,model=draft.models?.find(m=>m.id===draft.roles?.[role])
      return <details key={role}><summary>{label}：{model?model.provider+'/'+model.model:'尚未配置'}</summary>
        <label>复用模型 <select value={draft.roles?.[role]??''} onChange={e=>patch({roles:{...draft.roles,[role]:e.target.value||undefined}})}>
          <option value="">未配置</option>{draft.models?.map(m=><option key={m.id} value={m.id}>{m.id} · {m.provider}/{m.model}</option>)}</select></label>
        <label>宿主目录 <select value={model?JSON.stringify([model.provider,model.model]):''}
          onChange={e=>{if(e.target.value){const [provider,model]=JSON.parse(e.target.value) as string[];rolePatch(role,{provider,model})}}}>
          <option value="">选择已配置模型…</option>{catalog?.groups.filter(g=>g.id!=='refractagent').map(g=><optgroup key={g.id} label={g.name}>
            {g.models.map(m=><option key={m.id} value={JSON.stringify([g.id,m.id])}>{m.name}</option>)}</optgroup>)}</select></label>
        {model&&<div>
          <label>推理等级 <input value={model.reasoningEffort??''} onChange={e=>rolePatch(role,{reasoningEffort:e.target.value||undefined})}/></label>
          {(['contextWindow','maxOutputTokens','inputPer1k','outputPer1k','cachedInputPer1k','cacheWritePer1k'] as const).map((key,i)=>
            <label key={key} style={{display:'block'}}>{['上下文容量','输出容量','输入／千 token','输出／千 token','缓存读取／千 token','缓存写入／千 token'][i]} <input
              type="number" min="0" step="any" value={Number.isFinite(model[key])?model[key]:''} onChange={e=>rolePatch(role,{[key]:e.target.value===''?undefined:Number(e.target.value)})}/></label>)}
          <p>价格需按实际计费口径填写；0 仅适用于已确认不收费的模型。</p>
          <label>数据域 <select value={model.deployment??'external-cloud'} onChange={e=>rolePatch(role,{deployment:e.target.value})}>
            <option value="external-cloud">外部云</option><option value="local">真实本地</option><option value="trusted-cloud">可信云（需信任策略）</option></select></label>
          <label>信任策略 ID <input value={model.trustPolicy??''} onChange={e=>rolePatch(role,{trustPolicy:e.target.value||undefined})}/></label>
          <label>能力卡 <textarea value={model.capabilityCard??''} onChange={e=>rolePatch(role,{capabilityCard:e.target.value})}/></label>
        </div>}
      </details>
    })}
    <details><summary>策略参数与历史兼容</summary>
      <p>参数尚未校准。修改只影响新任务。</p>
      {Object.entries({window:3,threshold:.5,holdTurns:2,baseThreshold:.5,thresholdStep:.1,maxReviews:1,maxRedos:1,stallTurns:0,confirmations:2,seed:0,efficientWeight:1,capableWeight:1}).map(([key,value])=>
        <label key={key} style={{display:'block'}}>{({window:'证据窗口',threshold:'阶段判断阈值',holdTurns:'强模型保持轮数',baseThreshold:'任务基础阈值',
            thresholdStep:'能力边界修正步长',maxReviews:'审核次数上限',maxRedos:'返工次数上限',
            stallTurns:'停滞审核轮数（0 为关闭）',confirmations:'连续升级判断次数',seed:'随机种子',
            efficientWeight:'高效模型权重',capableWeight:'强模型权重'} as Record<string,string>)[key]} <input type="number"  step="any" value={draft.parameters?.[key]??value}
          onChange={e=>patch({parameters:{...draft.parameters,[key]:Number(e.target.value)}})}/></label>)}
      <label>Static <select value={draft.parameters?.staticMode??'fixed'} onChange={e=>patch({parameters:{...draft.parameters,staticMode:e.target.value}})}>
        <option value="fixed">固定高效角色</option><option value="random">随机对照</option></select></label>
      <p>信任策略、敏感词和已验收的 replay 模型对可在完整配置中编辑。</p>
      <button type="button" onClick={()=>setAdvanced(JSON.stringify(draft,null,2))}>读取完整配置</button>
      <textarea aria-label="规划路由完整配置" style={{display:'block',width:'100%',minHeight:160}} value={advanced} onChange={e=>setAdvanced(e.target.value)}/>
      <button type="button" onClick={()=>{try{const next:unknown=JSON.parse(advanced);validatePlanningShape(next);setDraft(next);setDirty(true)}catch(e){setStatus(errorText(e))}}}>应用配置草稿</button>
    </details>
    <button type="button" disabled={!snapshot.writable||busy||!dirty} onClick={()=>void save()}>保存规划路由</button>
    <button type="button" disabled={busy||dirty} onClick={()=>void preview().then(setReport).catch(e=>setStatus(errorText(e)))}>零调用检查</button>
    <button type="button" disabled={busy||dirty} onClick={()=>void simulate().then(r=>setStatus(
      r.message+' 模拟调用 '+r.simulatedCalls+' 次：'+r.models.join(' → '))).catch(e=>setStatus(errorText(e)))}>离线模拟</button>
    <p role="status">{status}</p>
    {report&&<div>{report.issues?.map((s,i)=><p key={i}>{s}</p>)}{report.strategies?.map(s=><p key={s.id}>{s.name}：{s.available?'可用':s.issues.join('；')}</p>)}<p>{report.coverage}</p></div>}
  </section>
}
export interface ModelDirectory {
  store:{getSnapshot():{current:{provider:string;model:string;reasoningEffort?:string}|null;error?:string|null};
    subscribe(cb:()=>void):()=>void}
  load():Promise<unknown>
  select(value:{provider:string;model:string;reasoningEffort:string}):Promise<void>
}
function Dock({directory,ui,sessionId}:{directory:ModelDirectory;ui:PlanningUi;sessionId:string}){
  const state=useSyncExternalStore(cb=>directory.store.subscribe(cb),()=>directory.store.getSnapshot())
  const previous=useRef<string>()
  useEffect(()=>{
    if(!state.current){previous.current=undefined;return}
    const route=state.current.provider+'/'+state.current.model
    const key='refractagent-planning-selection:'+sessionId
    try{
      if(route==='refractagent/planning'){
        const remembered=localStorage.getItem(key)
        if(previous.current&&previous.current!==route&&remembered&&remembered!==state.current?.reasoningEffort){
          void directory.select({provider:'refractagent',model:'planning',reasoningEffort:remembered}).catch(e=>setError(errorText(e)))
        }else if(state.current?.reasoningEffort?.startsWith('rr:'))localStorage.setItem(key,state.current.reasoningEffort)
      }
    }catch{/* 存储受限时仍可使用宿主原生持久化选择。 */}
    previous.current=route
  },[state.current,directory,sessionId])
  const [report,setReport]=useState<Report>(),[error,setError]=useState(''),[settings,setSettings]=useState(false)
  useEffect(()=>{void directory.load().catch(e=>setError(errorText(e)))},[directory])
  useEffect(()=>{const load=()=>void ui.preview().then(setReport).catch(e=>setError(errorText(e)));load();return ui.scope.subscribe(load)},[ui])
  if(state.current?.provider!=='refractagent'||state.current.model!=='planning')return null
  const selected=state.current.reasoningEffort?.replace(/^rr:/,'')??report?.defaultStrategy??'stage'
  const focusId=report?.strategies?.find(s=>s.id===selected&&s.available)?.id??report?.strategies?.find(s=>s.available)?.id
  const choose=(id:string)=>void directory.select({provider:'refractagent',model:'planning',reasoningEffort:'rr:'+id}).catch(e=>setError(errorText(e)))
  return <section aria-label="规划路由策略" style={{padding:'8px 12px'}}>
    <div role="radiogroup" aria-label="策略" style={{display:'flex',gap:6,overflowX:'auto'}}
      onKeyDown={e=>{
        if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return
        const choices=report?.strategies?.filter(s=>s.available)??[]
        if(!choices.length)return
        e.preventDefault();let index=choices.findIndex(s=>s.id===focusId)
        index=e.key==='Home'?0:e.key==='End'?choices.length-1:(index+(e.key==='ArrowLeft'?-1:1)+choices.length)%choices.length
        choose(choices[index].id)
        const buttons=e.currentTarget.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')
        buttons[index]?.focus()
      }}>
      {(report?.strategies??[]).map(s=><button type="button" key={s.id} role="radio" aria-checked={selected===s.id}
        tabIndex={focusId===s.id?0:-1} disabled={!s.available} title={s.issues.join('；')||HELP[s.id as PlanningStrategy]}
        onClick={()=>choose(s.id)} style={{whiteSpace:'nowrap',border:selected===s.id?'2px solid currentColor':undefined}}>
        {PLANNING_NAMES[s.id as PlanningStrategy]}</button>)}
    </div>
    <p>{HELP[selected as PlanningStrategy]} <small>运行中切换将于下个任务生效。</small> <button type="button" onClick={()=>setSettings(!settings)}>策略设置…</button></p>
    <p role="status">{error||state.error||report?.issues?.join('；')||report?.strategies?.find(s=>s.id===selected)?.issues.join('；')}</p>
    {settings&&<PlanningSettings {...ui}/>}
  </section>
}
type History={records:Array<{runId:string;strategy:string;status:string;costs:{production:number};billingUnit:string;
  calls:Array<{call_id:string;model_id:string;purpose:string;disposition:string;charged:number;latency_ms?:number}>;
  decisions:Array<{callId:string;reason:string}>}>}
function Trace({load}:{load:()=>Promise<History>}){
  const [data,setData]=useState<History>(),[error,setError]=useState('')
  useEffect(()=>{let active=true
    const refresh=()=>void load().then(v=>{if(active)setData(v)}).catch(e=>{if(active)setError(errorText(e))})
    refresh();const timer=setInterval(refresh,2500);return()=>{active=false;clearInterval(timer)}
  },[load])
  return <section style={{padding:24}}><h2>路由轨迹</h2><p>只统计当前受管 Agent；普通 DSH 子模型费用尚未汇总。</p>
    <p role="status">{error}</p>{!data?.records.length&&<p>尚无规划路由记录。</p>}
    {data?.records.map(r=><article key={r.runId}><h3>{r.strategy} · {r.status}</h3><p>{r.costs.production} {r.billingUnit}</p>
      <table><thead><tr>{['模型','用途','交付状态','费用','耗时 ms','理由'].map(h=><th key={h}>{h}</th>)}</tr></thead>
        <tbody>{r.calls.map(c=><tr key={c.call_id}><td>{c.model_id}</td><td>{c.purpose}</td><td>{c.disposition}{(c as unknown as {review_status?:string}).review_status==='revised-unreviewed'?' · 未复审':''}</td>
          <td>{c.charged}</td><td>{c.latency_ms?.toFixed(0)??'待核对'}</td><td>{r.decisions.find(d=>d.callId===c.call_id)?.reason??'策略判别'}</td></tr>)}</tbody></table></article>)}
  </section>
}
export function planningUi(ctx:ClientContext,scope:CardScope):PlanningUi {
  return {scope,simulate:async()=>{const r=await ctx.remote.llm.discoverModels('refractagent-planning',{provider:'local',api:'simulate'});
    if(!r.ok)throw new Error(r.error?.message);return JSON.parse(r.value?.[0]?.name??'{}')},
    loadCatalog:async()=>{const r=await ctx.remote.session.modelCatalog();if(!r.ok||!r.value)throw new Error(r.error?.message);return r.value},
    preview:async()=>{const r=await ctx.remote.llm.discoverModels('refractagent-planning',{provider:'local'});if(!r.ok)throw new Error(r.error?.message);return JSON.parse(r.value?.[0]?.name??'{}') as Report}}
}
export function applyPlanning(ctx:ClientContext,ui:PlanningUi){
  if(ctx.modelDirectories)ctx.slots.inject('conversation.composer.dock',function*(){
    yield ctx.slots.register({name:'conversation.composer.dock',id:'refractagent-planning',order:10,
      inject:(sessionId:string)=>({directory:ctx.modelDirectories!.directoryFor(sessionId),ui,sessionId})},Dock)
  })
  ctx.slots.inject('conversation.view',function*(){
    yield ctx.slots.register({name:'conversation.view',id:'refractagent-routing',order:16,label:()=> '路由轨迹',
      inject:(sessionId:string)=>({load:async()=>{
        const r=await ctx.remote.llm.discoverModels('refractagent-planning',{provider:sessionId})
        if(!r.ok)throw new Error(r.error?.message)
        return JSON.parse(r.value?.[0]?.name??'{"records":[]}') as History
      }})},Trace)
  })
}
