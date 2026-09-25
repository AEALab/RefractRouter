import { useEffect, useState, useSyncExternalStore } from 'react'
import { EMPTY_PLANNING, PLANNING_NAMES, validatePlanningShape, type PlanningConfig, type PlanningStrategy } from '../planning-config.js'
import type { CardScope } from '../settings-card.js'
import type { ClientContext, DshModelCatalog } from './types.js'

type Report={valid?:boolean;issues?:string[];defaultStrategy?:string;coverage?:string;
  strategies?:Array<{id:string;name:string;available:boolean;issues:string[]}>}
type ModelMetadata={provider:string;model:string;billingUnit:'USD'|'AFP'|'CNY';
  capacity?:{contextWindow:number;maxOutputTokens:number}|null;
  pricing?:{inputPer1k:number;outputPer1k:number;cachedInputPer1k?:number}|null;
  sources?:{capacity?:string;pricing?:string;pricingCheckedAt?:string;conversion?:string;
    conversionAsOf?:string;pricingNote?:string};issues?:string[]}
export interface PlanningUi {
  scope:CardScope
  preview():Promise<Report>
  simulate():Promise<{message:string;simulatedCalls:number;models:string[]}>
  loadCatalog():Promise<DshModelCatalog>
  loadMetadata(provider:string,model:string,billingUnit:string):Promise<ModelMetadata>
  loadFx():Promise<{rate:number;source:string;asOf:string}>
}
const HELP:Record<PlanningStrategy,string>={
  stage:'根据工具执行轨迹调整模型，不额外调用判别模型。',
  task:'开始时判别任务难度，当前任务保持选定模型。',
  composite:'任务判别确定默认模型，再根据执行轨迹调整。',
  advisor:'执行器准备结束时审核，必要时有界返工。',
  escalation:'审核高效模型回复，连续困难时切换并锁定强模型。',
  static:'固定执行模型，或每个任务随机选择一次并在工具续接中保持。'}
const ROLES={efficient:'高效执行模型',capable:'强执行模型',classifier:'任务／升级判别模型',advisor:'审核模型'} as const
function errorText(e:unknown){return e instanceof Error?e.message:String(e)}
export function PlanningCard(props:PlanningUi){
  const [expanded,setExpanded]=useState(false)
  const snapshot=useSyncExternalStore(cb=>props.scope.subscribe(cb),()=>props.scope.getSnapshot())
  return <li className={'rra-card'+(expanded?' rra-card-open':'')}>
    <button type="button" className="rra-head" aria-expanded={expanded}
      aria-label={(expanded?'收起设置':'展开设置')+': RefractAgent 规划路由'}
      onClick={()=>setExpanded(value=>!value)}>
      <span className="rra-head-text"><span className="rra-name">RefractAgent 规划路由</span>
        <span className="rra-desc">在 DSH 原生 Agent 循环中选择模型与策略。</span></span>
      <span className="rra-badge">{snapshot.value?.planningRouting?.enabled?'已启用':'未启用'}</span>
      <svg className="rra-chevron" width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
        <path d="M3 5.5L7 9.5L11 5.5" stroke="currentColor" strokeWidth="1.5"/>
      </svg>
    </button>
    {expanded&&<div className="rra-body"><PlanningSettings {...props}/></div>}
  </li>
}
/** DSH 0.1.5 的模型菜单将 reasoning 元数据统一标作「推理等级」。
 * 仅在规划路由为当前模型时修正宿主菜单的显示与可访问名称；模式仍由原生菜单保存。
 */
function labelPlanningModeMenu():()=>void {
  if(typeof document==='undefined'||typeof MutationObserver==='undefined')return ()=>{}
  const update=()=>{
    const triggers=[...document.querySelectorAll<HTMLButtonElement>('button[aria-haspopup="menu"]')]
    const planning=triggers.some(button=>button.getAttribute('aria-label')?.includes('RefractAgent · 规划路由'))
    for(const button of triggers){
      const label=button.getAttribute('aria-label')??''
      if(!label.includes('RefractAgent · 规划路由'))continue
      const next=label.replace('推理等级','路由模式').replace('reasoning effort','routing mode')
      if(next!==label)button.setAttribute('aria-label',next)
    }
    const menu=document.querySelector<HTMLElement>('[role="menu"][aria-label="模型与推理等级"], [role="menu"][aria-label="模型与路由模式"], [role="menu"][aria-label="Model and reasoning effort"], [role="menu"][aria-label="Model and routing mode"]')
    if(!menu)return
    const label=menu.getAttribute('aria-label')??''
    const next=planning?label.replace('模型与推理等级','模型与路由模式').replace('Model and reasoning effort','Model and routing mode'):
      label.replace('模型与路由模式','模型与推理等级').replace('Model and routing mode','Model and reasoning effort')
    if(next!==label)menu.setAttribute('aria-label',next)
    for(const item of menu.querySelectorAll<HTMLElement>('[role="menuitem"]')){
      const name=item.firstElementChild
      if(!name)continue
      const current=name.textContent
      const desired=planning?current==='推理等级'?'路由模式':current==='Effort'?'Routing mode':current:
        current==='路由模式'?'推理等级':current==='Routing mode'?'Effort':current
      if(desired!==current)name.textContent=desired
    }
  }
  const observer=new MutationObserver(update)
  observer.observe(document.documentElement,{subtree:true,childList:true,characterData:true,
    attributes:true,attributeFilter:['aria-label']})
  update()
  return ()=>observer.disconnect()
}
export function PlanningSettings({scope,preview,loadCatalog,loadMetadata,loadFx,simulate}:PlanningUi){
  const snapshot=useSyncExternalStore(cb=>scope.subscribe(cb),()=>scope.getSnapshot())
  const saved=snapshot.value?.planningRouting??EMPTY_PLANNING
  const [draft,setDraft]=useState<PlanningConfig>(()=>structuredClone(saved))
  const [dirty,setDirty]=useState(false),[busy,setBusy]=useState(false),[status,setStatus]=useState('')
  const [report,setReport]=useState<Report>(),[catalog,setCatalog]=useState<DshModelCatalog>()
  const [advanced,setAdvanced]=useState('')
  const [metadata,setMetadata]=useState<Record<string,ModelMetadata>>({})
  const [metadataErrors,setMetadataErrors]=useState<Record<string,string>>({})
  useEffect(()=>{if(!dirty)setDraft(structuredClone(saved))},[saved,dirty])
  useEffect(()=>{void loadCatalog().then(setCatalog).catch(e=>setStatus(errorText(e)))},[loadCatalog])
  function patch(value:Partial<PlanningConfig>){setDraft(v=>({...v,...value}));setDirty(true);setReport(undefined)}
  const modelKey=(provider:string,model:string,unit:string)=>JSON.stringify([provider,model,unit])
  async function retrieveMetadata(provider:string,model:string,unit:string){
    const key=modelKey(provider,model,unit)
    try{
      const info=await loadMetadata(provider,model,unit)
      setMetadata(previous=>({...previous,[key]:info,[modelKey(provider,model,info.billingUnit)]:info}))
      setMetadataErrors(previous=>{const next={...previous};delete next[key];return next})
      if(!info.capacity&&!info.pricing)return
      setDraft(previous=>{
        let changed=false
        const models=previous.models?.map(row=>{
          if(row.provider!==provider||row.model!==model)return row
          if(unit!=='AUTO'&&(row.billingUnit??previous.billingUnit??'USD')!==unit)return row
          const next={...row,...(unit==='AUTO'?{billingUnit:info.billingUnit}:{}),
            ...(info.capacity??{}),...(info.pricing??{})}
          if(JSON.stringify(next)!==JSON.stringify(row)){changed=true;return next}
          return row
        })
        if(changed){queueMicrotask(()=>{setDirty(true);setReport(undefined)
          setStatus('系统已将查到的模型资料填入草稿；保存后对新任务生效。')});return {...previous,models}}
        return previous
      })
    }catch(error){setMetadataErrors(previous=>({...previous,[key]:errorText(error)}))}
  }
  useEffect(()=>{
    if(!catalog)return
    for(const row of saved.models??[])void retrieveMetadata(row.provider,row.model,'AUTO')
  },[catalog,saved])
  useEffect(()=>{
    if(dirty||draft.maxProductionCostByUnit?.CNY!==undefined)return
    const legacyUnit=draft.billingUnit??(draft.schemaVersion==='refractagent-planning-v1'?'USD':'CNY')
    const legacyUsd=draft.maxProductionCostByUnit?.USD??
      (legacyUnit==='USD'?draft.maxProductionCost:undefined)
    if(typeof legacyUsd!=='number'||!Number.isFinite(legacyUsd))return
    void loadFx().then(fx=>{
      setDraft(previous=>{
        if(previous.maxProductionCostByUnit?.CNY!==undefined)return previous
        queueMicrotask(()=>{setDirty(true);setReport(undefined)
          setStatus(`旧 USD 预算已按冻结汇率 ${fx.rate}（${fx.asOf}）换算为 CNY 草稿；保存后生效。`)})
        return {...previous,billingUnit:'CNY',maxProductionCostByUnit:{...previous.maxProductionCostByUnit,
          CNY:legacyUsd*fx.rate}}
      })
    }).catch(error=>setStatus(errorText(error)))
  },[dirty,draft.billingUnit,draft.maxProductionCost,draft.maxProductionCostByUnit,loadFx])
  async function save(){
    setBusy(true);setStatus('')
    try{await scope.set('planningRouting',JSON.parse(JSON.stringify({...draft,schemaVersion:'refractagent-planning-v2'})));setDirty(false)
      const result=await preview();setReport(result)
      const selected=result.strategies?.find(row=>row.id===(draft.defaultStrategy??'stage'))
      setStatus(selected?.available
        ?'已保存；当前策略可运行。其他策略的限制见零调用诊断。现有任务继续使用启动时配置。'
        :'已保存；当前策略暂不可运行，请查看零调用诊断。')}
    catch(e){setStatus(errorText(e))}finally{setBusy(false)}
  }
  function rolePatch(role:keyof typeof ROLES,value:Partial<NonNullable<PlanningConfig['models']>[number]>){
    const id=draft.roles?.[role]??role
    const previous=draft.models?.find(m=>m.id===id)
    const model={id,provider:'',model:'',deployment:'external-cloud',...previous,...value}
    patch({roles:{...draft.roles,[role]:id},models:[...(draft.models??[]).filter(m=>m.id!==id),model]})
  }
  function selectCatalogModel(role:keyof typeof ROLES,provider:string,model:string){
    const existing=draft.models?.find(item=>item.provider===provider&&item.model===model)
    if(existing){patch({roles:{...draft.roles,[role]:existing.id}})
      void retrieveMetadata(provider,model,'AUTO');return}
    const base=`${role}-${provider}-${model}`.replace(/[^a-zA-Z0-9_-]/g,'-')
    let id=base,index=2
    while(draft.models?.some(item=>item.id===id))id=`${base}-${index++}`
    patch({roles:{...draft.roles,[role]:id},models:[...(draft.models??[]),{
      id,provider,model,deployment:'external-cloud'}]})
    void retrieveMetadata(provider,model,'AUTO')
  }
  const activeUnits=[...new Set(Object.values(draft.roles??{}).map(id=>{
    const unit=draft.models?.find(model=>model.id===id)?.billingUnit??draft.billingUnit??'CNY'
    return unit==='USD'?'CNY':unit
  }))]
  return <section className="rra-v4-section rra-planning" aria-label="规划路由设置">
    <div className="rra-section-head"><div><h3>规划路由</h3><p className="rra-field-hint">根据任务与执行轨迹选择模型，使用 DSH 原生工具、审批与委派。</p></div>{dirty&&<span className="rra-badge">未保存</span>}</div>
    <label className="rra-check"><input type="checkbox" checked={draft.enabled} onChange={e=>patch({enabled:e.target.checked})}/>启用独立规划路由</label>
    <div className="rra-row-card"><h3>通用运行设置</h3><p className="rra-field-hint">现金预算统一使用 CNY；USD 模型价格优先采用可核对的官方人民币价格，否则按冻结汇率折算。AFP 点数单独结算。留空表示该单位尚未配置；0 表示不限制。当前角色使用：{activeUnits.join('、')}。</p>
    <div className="rra-grid rra-grid-2">{(['AFP','CNY'] as const).map(unit=><label className="rra-compact-field" key={unit}>{unit==='AFP'?'AFP 点数预算':'CNY 现金预算'}（0 为不限制） <input className="rra-input" type="number" min="0" step="any"
      value={draft.maxProductionCostByUnit?.[unit]??(unit===(draft.billingUnit??'USD')?draft.maxProductionCost:'')??''}
      onChange={e=>patch({maxProductionCostByUnit:{...draft.maxProductionCostByUnit,
        [unit]:e.target.value===''?undefined:Number(e.target.value)}})}/></label>)}</div>
    <div className="rra-grid rra-grid-2"><label className="rra-compact-field">任务期限（毫秒，0 为不限制） <input className="rra-input" type="number" min="0" value={draft.timeoutMs??300000} onChange={e=>patch({timeoutMs:Number(e.target.value)})}/></label>
      <label className="rra-compact-field">最大调用数（0 为不限制） <input className="rra-input" type="number" min="0" value={draft.maxCalls??128} onChange={e=>patch({maxCalls:Number(e.target.value)})}/></label></div></div>
    <div className="rra-row-card"><h3>模型与角色</h3><p className="rra-field-hint">四种角色集中管理；每项策略只要求它实际使用的模型。系统查询容量和价格；历史值保留并注明尚未核对，新路线缺项时不可运行。</p>
    {Object.entries(ROLES).map(([r,label])=>{
      const role=r as keyof typeof ROLES,model=draft.models?.find(m=>m.id===draft.roles?.[role])
      const key=model?modelKey(model.provider,model.model,model.billingUnit==='USD'?'CNY':model.billingUnit??draft.billingUnit??'CNY'):''
      const info=metadata[key]
      const efforts=catalog?.groups.find(group=>group.id===model?.provider)?.models.find(row=>row.id===model?.model)?.reasoning?.efforts??[]
      const supported=efforts.some(entry=>entry.id===model?.reasoningEffort)
      return <details className="rra-details" key={role}><summary>{label}：{model?model.provider+'/'+model.model:'尚未配置'}</summary><div className="rra-planning-fields">
        <label className="rra-compact-field">从 DSH 模型目录选择 <select className="rra-select" value={model?JSON.stringify([model.provider,model.model]):''}
          onChange={e=>{if(e.target.value){const [provider,selected]=JSON.parse(e.target.value) as string[];selectCatalogModel(role,provider,selected)}}}>
          <option value="">选择模型…</option>{catalog?.groups.filter(g=>g.id!=='refractagent').map(g=><optgroup key={g.id} label={g.name}>
            {g.models.map(m=><option key={m.id} value={JSON.stringify([g.id,m.id])}>{m.name}</option>)}</optgroup>)}</select></label>
        <p className="rra-field-hint">模型与推理等级来自 DSH；容量与实际路线价格由系统资料源核对。</p>
        <label className="rra-compact-field">复用已登记配置 <select className="rra-select" value={draft.roles?.[role]??''} onChange={e=>{
          const selected=draft.models?.find(item=>item.id===e.target.value)
          patch({roles:{...draft.roles,[role]:e.target.value||undefined}})
          if(selected)void retrieveMetadata(selected.provider,selected.model,'AUTO')
        }}>
          <option value="">未配置</option>{draft.models?.map(m=><option key={m.id} value={m.id}>{m.id} · {m.provider}/{m.model}</option>)}</select></label>
        {model&&<div className="rra-grid rra-grid-2">
          <label className="rra-compact-field">计费单位 <select className="rra-select" value={model.billingUnit==='USD'?'CNY':model.billingUnit??draft.billingUnit??'CNY'} onChange={e=>{
            const unit=e.target.value as 'USD'|'AFP'|'CNY'
            rolePatch(role,{billingUnit:unit,inputPer1k:undefined,outputPer1k:undefined,
              cachedInputPer1k:undefined,cacheWritePer1k:undefined})
            void retrieveMetadata(model.provider,model.model,unit)
          }}><option>AFP</option><option>CNY</option></select></label>
          <label className="rra-compact-field">推理等级 <select className="rra-select" value={model.reasoningEffort??''} onChange={e=>rolePatch(role,{reasoningEffort:e.target.value||undefined})}>
            <option value="">使用提供方默认</option>{!supported&&model.reasoningEffort&&<option value={model.reasoningEffort}>旧值未在 DSH 目录中：{model.reasoningEffort}</option>}
            {efforts.map(entry=><option key={entry.id} value={entry.id}>{entry.name}</option>)}
          </select></label>
          <label className="rra-compact-field">数据域 <select className="rra-select" value={model.deployment??'external-cloud'} onChange={e=>rolePatch(role,{
            deployment:e.target.value,trustPolicy:e.target.value==='trusted-cloud'?model.trustPolicy:undefined})}>
            <option value="external-cloud">外部云（拦截本机路径等敏感输入）</option>
            <option value="trusted-cloud">已授权的可信云</option>
            <option value="local">本地部署</option>
            <option value="simulated-local" disabled>模拟本地（仅实验；真实规划路由不可用）</option>
          </select></label>
          {model.deployment==='trusted-cloud'&&<label className="rra-compact-field">信任策略 <select className="rra-select" value={model.trustPolicy??''}
            onChange={e=>rolePatch(role,{trustPolicy:e.target.value||undefined})}>
            <option value="">选择已登记的许可…</option>
            {draft.trustPolicies?.map(policy=><option key={String(policy.id)} value={String(policy.id)}>{String(policy.id)}</option>)}
          </select></label>}
          {(['contextWindow','maxOutputTokens','inputPer1k','outputPer1k','cachedInputPer1k','cacheWritePer1k'] as const).map((field,i)=><div className="rra-compact-field" key={field}>
            <span>{['上下文容量','输出容量','输入／千 token','输出／千 token','缓存读取／千 token','缓存写入／千 token'][i]}</span>
            <strong>{model.billingUnit==='USD'&&i>=2
              ?(field==='inputPer1k'?info?.pricing?.inputPer1k:field==='outputPer1k'?info?.pricing?.outputPer1k:
                field==='cachedInputPer1k'?info?.pricing?.cachedInputPer1k:undefined)??'待换算'
              :typeof model[field]==='number'&&Number.isFinite(model[field])?model[field]:'待核对'}
              {i>=2?' CNY/千 token':''}{i>=2&&model.billingUnit!=='USD'&&!info?.pricing&&typeof model[field]==='number'?'（历史值待核对）':''}</strong>
          </div>)}
          <p className="rra-field-hint">容量来源：{info?.sources?.capacity??'尚未核对'}；价格来源：{info?.sources?.pricing??'尚未核对'}{info?.sources?.pricingCheckedAt?'（'+info.sources.pricingCheckedAt+'）':''}。{info?.sources?.pricingNote??''}</p>
          {(info?.issues?.length||metadataErrors[key])&&<p className="rra-field-hint">{[...(info?.issues??[]),metadataErrors[key]].filter(Boolean).join('；')}。资料不足时不会以参考价或 0 冒充实际费用。</p>}
        </div>}
      </div></details>
    })}</div>
    <div className="rra-row-card"><h3>策略设置</h3><label className="rra-compact-field">默认路由策略 <select className="rra-select" value={draft.defaultStrategy??'stage'} onChange={e=>patch({defaultStrategy:e.target.value as PlanningStrategy})}>
      {Object.entries(PLANNING_NAMES).map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></label><p className="rra-field-hint">{HELP[draft.defaultStrategy??'stage']}</p><p className="rra-field-hint">保存后从下个任务生效；当前任务继续使用启动时配置。</p>
    <details className="rra-details"><summary>{draft.defaultStrategy==='static'?'Static 设置':'策略参数'}</summary><div className="rra-planning-fields">
      <p>参数尚未校准。修改只影响新任务。</p>
      {draft.defaultStrategy==='static'&&<>
        <p className="rra-field-hint">选模方式默认「固定高效角色」，这是当前程序默认值，不表示你曾主动设置。</p>
        <label className="rra-compact-field">选模方式 <select className="rra-select" value={draft.parameters?.staticMode??'fixed'} onChange={e=>patch({parameters:{...draft.parameters,staticMode:e.target.value}})}>
          <option value="fixed">固定高效执行模型</option><option value="random">按权重每任务随机选择一次</option></select></label>
        {(draft.parameters?.staticMode??'fixed')==='fixed'&&<p className="rra-field-hint">当前固定使用上方「高效执行模型」：{draft.models?.find(m=>m.id===draft.roles?.efficient)?.provider??'未配置'}/{draft.models?.find(m=>m.id===draft.roles?.efficient)?.model??'未配置'}；其推理等级读取该模型的「推理等级」字段。</p>}
      </>}
      {Object.entries({window:3,threshold:.5,holdTurns:2,baseThreshold:.5,thresholdStep:.1,maxReviews:1,maxRedos:1,stallTurns:0,confirmations:2,seed:0,efficientWeight:1,capableWeight:1}).filter(([key])=>({stage:['window','threshold','holdTurns'],task:['baseThreshold','thresholdStep'],composite:['window','threshold','holdTurns','baseThreshold','thresholdStep'],advisor:['maxReviews','maxRedos','stallTurns'],escalation:['confirmations'],static:(draft.parameters?.staticMode??'fixed')==='random'?['seed','efficientWeight','capableWeight']:[]}[draft.defaultStrategy??'stage']).includes(key)).map(([key,value])=>
        <label className="rra-compact-field" key={key}>{({window:'证据窗口',threshold:'阶段判断阈值',holdTurns:'强模型保持轮数',baseThreshold:'任务基础阈值',
            thresholdStep:'能力边界修正步长',maxReviews:'审核次数上限',maxRedos:'返工次数上限',
            stallTurns:'停滞审核轮数（0 为关闭）',confirmations:'连续升级判断次数',seed:'随机种子',
            efficientWeight:'高效模型权重',capableWeight:'强模型权重'} as Record<string,string>)[key]} <input className="rra-input" type="number"  step="any" value={draft.parameters?.[key]??value}
          onChange={e=>patch({parameters:{...draft.parameters,[key]:Number(e.target.value)}})}/></label>)}
      </div></details></div>
    <details className="rra-details"><summary>数据与历史兼容（高级）</summary><div className="rra-planning-fields">
      <p>数据域决定请求能否发送到目标模型；信任策略是已登记的数据处理许可；能力卡只供 Task 等判别策略参考。它们都不是 Static 的选模参数。</p>
      <p>敏感词、信任策略和已验收的跨模型 replay 组合保留在高级配置中。模型容量与价格由系统查询。</p>
      {draft.models?.map(model=><p key={model.id}>{model.provider}/{model.model}：数据域 {model.deployment??'外部云'}；信任策略 {model.trustPolicy??'无'}；能力卡 {model.capabilityCard?'已登记':'无'}</p>)}
      <button className="rra-button rra-button-secondary" type="button" onClick={()=>setAdvanced(JSON.stringify({
        security:draft.security??{},trustPolicies:draft.trustPolicies??[],compatiblePairs:draft.compatiblePairs??[]},null,2))}>读取数据与历史配置</button>
      <textarea className="rra-textarea rra-json" aria-label="数据与历史兼容配置" value={advanced} onChange={e=>setAdvanced(e.target.value)}/>
      <button className="rra-button rra-button-secondary" type="button" onClick={()=>{try{
        const value:unknown=JSON.parse(advanced)
        if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).some(key=>
          !['security','trustPolicies','compatiblePairs'].includes(key)))throw new Error('只允许数据与历史兼容字段')
        const next={...draft,...value};validatePlanningShape(next);setDraft(next);setDirty(true)
      }catch(e){setStatus(errorText(e))}}}>应用高级配置草稿</button>
    </div></details>
    <div className="rra-actions">
    <button className="rra-button" type="button" disabled={!snapshot.writable||busy||!dirty} onClick={()=>void save()}>保存规划路由</button>
    <button className="rra-button rra-button-secondary" type="button" disabled={busy||dirty} onClick={()=>void preview().then(setReport).catch(e=>setStatus(errorText(e)))}>零调用检查</button>
    <button className="rra-button rra-button-secondary" type="button" disabled={busy||dirty} onClick={()=>void simulate().then(r=>setStatus(
      r.message+' 模拟调用 '+r.simulatedCalls+' 次：'+r.models.join(' → '))).catch(e=>setStatus(errorText(e)))}>离线模拟</button>
    </div>
    {status&&<p className="rra-simple-status" role="status">{status}</p>}
    {report&&<div className="rra-issue-summary" role="status">{report.issues?.map((s,i)=><p key={i}>{s}</p>)}{report.strategies?.map(s=><p key={s.id}>{s.name}：{s.available?'可用':s.issues.join('；')}</p>)}<p>{report.coverage}</p></div>}
  </section>
}
type History={records:Array<{runId:string;strategy:string;status:string;costs:{production:number|null};billingUnit:string|null;billingWarning?:string;
  costsByUnit?:Record<string,{production:number;evaluation:number}>;
  calls:Array<{call_id:string;model_id:string;provider?:string;actual_model?:string;purpose:string;disposition:string;charged:number;billing_unit?:string;latency_ms?:number}>;
  decisions:Array<{callId:string;reason:string}>}>}
function Trace({load}:{load:()=>Promise<History>}){
  const [data,setData]=useState<History>(),[error,setError]=useState('')
  useEffect(()=>{let active=true
    const refresh=()=>void load().then(v=>{if(active)setData(v)}).catch(e=>{if(active)setError(errorText(e))})
    refresh();const timer=setInterval(refresh,2500);return()=>{active=false;clearInterval(timer)}
  },[load])
  return <section style={{padding:24}}><h2>路由轨迹</h2><p>只统计当前受管 Agent；普通 DSH 子模型费用尚未汇总。</p>
    <p role="status">{error}</p>{!data?.records.length&&<p>尚无规划路由记录。</p>}
    {data?.records.map(r=><article key={r.runId}><h3>{r.strategy} · {r.status}</h3>
      {r.billingWarning?<p>{r.costs.production}（单位待核对）</p>:
        r.costsByUnit?<p>{Object.entries(r.costsByUnit).filter(([unit,amount])=>amount.production!==0||r.calls.some(c=>c.billing_unit===unit))
          .map(([unit,amount])=>`${amount.production} ${unit}`).join('；')||'尚无调用'}</p>:
        <p>{r.costs.production} {r.billingUnit}</p>}
      {r.billingWarning&&<p role="status">{r.billingWarning}</p>}
      <table><thead><tr>{['模型','用途','交付状态','费用','耗时 ms','理由'].map(h=><th key={h}>{h}</th>)}</tr></thead>
        <tbody>{r.calls.map(c=><tr key={c.call_id}><td>{c.provider&&c.actual_model?`${c.provider}/${c.actual_model}`:c.model_id}</td><td>{c.purpose}</td><td>{c.disposition}{(c as unknown as {review_status?:string}).review_status==='revised-unreviewed'?' · 未复审':''}</td>
          <td>{c.charged}{r.billingWarning?'（单位待核对）':c.billing_unit?` ${c.billing_unit}`:''}</td><td>{c.latency_ms?.toFixed(0)??'待核对'}</td><td>{r.decisions.find(d=>d.callId===c.call_id)?.reason??'策略判别'}</td></tr>)}</tbody></table></article>)}
  </section>
}
export function planningUi(ctx:ClientContext,scope:CardScope):PlanningUi {
  return {scope,simulate:async()=>{const r=await ctx.remote.llm.discoverModels('refractagent-planning',{provider:'local',api:'simulate'});
    if(!r.ok)throw new Error(r.error?.message);return JSON.parse(r.value?.[0]?.name??'{}')},
    loadCatalog:async()=>{const r=await ctx.remote.session.modelCatalog();if(!r.ok||!r.value)throw new Error(r.error?.message);return r.value},
    loadMetadata:async(provider,model,billingUnit)=>{
      const api='metadata:'+encodeURIComponent(model)+':'+billingUnit
      const r=await ctx.remote.llm.discoverModels('refractagent-planning',{provider,api})
      if(!r.ok)throw new Error(r.error?.message??'模型资料查询失败')
      return JSON.parse(r.value?.[0]?.name??'{}') as ModelMetadata
    },
    loadFx:async()=>{const r=await ctx.remote.llm.discoverModels('refractagent-planning',{provider:'local',api:'fx'})
      if(!r.ok)throw new Error(r.error?.message??'汇率资料查询失败')
      return JSON.parse(r.value?.[0]?.name??'{}') as {rate:number;source:string;asOf:string}},
    preview:async()=>{const r=await ctx.remote.llm.discoverModels('refractagent-planning',{provider:'local'});if(!r.ok)throw new Error(r.error?.message);return JSON.parse(r.value?.[0]?.name??'{}') as Report}}
}
export function applyPlanning(ctx:ClientContext){
  ctx.effect(labelPlanningModeMenu,'refractagent-planning: mode menu label')
  ctx.slots.inject('conversation.view',function*(){
    yield ctx.slots.register({name:'conversation.view',id:'refractagent-routing',order:16,label:()=> '路由轨迹',
      inject:(sessionId:string)=>({load:async()=>{
        const r=await ctx.remote.llm.discoverModels('refractagent-planning',{provider:sessionId})
        if(!r.ok)throw new Error(r.error?.message)
        return JSON.parse(r.value?.[0]?.name??'{"records":[]}') as History
      }})},Trace)
  })
}
