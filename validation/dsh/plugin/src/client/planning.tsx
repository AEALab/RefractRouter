import { useEffect, useState, useSyncExternalStore } from 'react'
import { EMPTY_PLANNING, PLANNING_NAMES, validatePlanningShape, type MediaRouteConfig, type PlanningConfig, type PlanningStrategy } from '../planning-config.js'
import type { CardScope } from '../settings-card.js'
import type { ClientContext, DshModelCatalog } from './types.js'

type Report={valid?:boolean;issues?:string[];defaultStrategy?:string;coverage?:string;
  strategies?:Array<{id:string;name:string;available:boolean;issues:string[]}>;
  mediaRoutes?:Array<{id:string;provider:string;model:string;available:boolean;verification:string;issues:string[]}>}
type ModelMetadata={provider:string;model:string;billingUnit:'USD'|'AFP'|'CNY';
  capacity?:{contextWindow:number;maxOutputTokens:number}|null;
  pricing?:{inputPer1k:number;outputPer1k:number;cachedInputPer1k?:number}|null;
  capabilities?:NonNullable<NonNullable<PlanningConfig['models']>[number]['capabilities']>|null;
  sources?:{capacity?:string;pricing?:string;pricingCheckedAt?:string;conversion?:string;
    conversionAsOf?:string;pricingNote?:string};issues?:string[]}
export interface PlanningUi {
  scope:CardScope
  preview():Promise<Report>
  simulate():Promise<{message:string;simulatedCalls:number;models:string[]}>
  loadCatalog():Promise<DshModelCatalog>
  loadMetadata(provider:string,model:string,billingUnit:string):Promise<ModelMetadata>
  loadFx():Promise<{rate:number;source:string;asOf:string}>
  localJudge(config:PlanningConfig,action:'status'|'download'|'load'|'unload'):Promise<{
    installed:boolean;downloaded:boolean;loaded:boolean;path:string;sourceModel:string;revision:string;
    revisionVerified:boolean;sizeBytes:number}>
}
const HELP:Record<PlanningStrategy,string>={
  stage:'根据工具执行轨迹调整模型，不额外调用判别模型。',
  task:'开始时判别任务难度，当前任务保持选定模型。',
  composite:'任务判别确定默认模型，再根据执行轨迹调整。',
  advisor:'执行器准备结束时审核，必要时有界返工。',
  escalation:'审核高效模型回复，连续困难时切换并锁定强模型。',
  static:'固定执行模型，或每个任务随机选择一次并在工具续接中保持。'}
const ROLES={efficient:'高效执行模型',capable:'强执行模型',classifier:'任务／升级判别模型',advisor:'审核模型'} as const
const SEEDREAM_CONNECTED:MediaRouteConfig={id:'ark-plan-seedream-5-lite',provider:'ark-plan',credentialProvider:'ark',
  model:'doubao-seedream-5.0-lite',operations:['image-generate','image-edit'],billingUnit:'AFP',
  pricing:{basis:'image',unitCost:99,source:'https://docs.volcengine.com/docs/ark/agent-plan-personal-afp-credits-billing-rules?lang=zh',checkedAt:'2026-09-26'},
  deployment:'external-cloud',verification:'connected',endpoint:'https://ark.cn-beijing.volces.com/api/plan/v3'}
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
export function PlanningSettings({scope,preview,loadCatalog,loadMetadata,loadFx,localJudge,simulate}:PlanningUi){
  const snapshot=useSyncExternalStore(cb=>scope.subscribe(cb),()=>scope.getSnapshot())
  const saved=snapshot.value?.planningRouting??EMPTY_PLANNING
  const [draft,setDraft]=useState<PlanningConfig>(()=>structuredClone(saved))
  const [dirty,setDirty]=useState(false),[busy,setBusy]=useState(false),[status,setStatus]=useState('')
  const [report,setReport]=useState<Report>(),[catalog,setCatalog]=useState<DshModelCatalog>()
  const [advanced,setAdvanced]=useState('')
  const [metadata,setMetadata]=useState<Record<string,ModelMetadata>>({})
  const [metadataErrors,setMetadataErrors]=useState<Record<string,string>>({})
  const [localJudgeStatus,setLocalJudgeStatus]=useState<{installed:boolean;downloaded:boolean;loaded:boolean;path:string;revisionVerified:boolean;sizeBytes:number}>()
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
            ...(info.capacity??{}),...(info.pricing??{}),...(info.capabilities?{capabilities:info.capabilities}:{})}
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
    try{await scope.set('planningRouting',JSON.parse(JSON.stringify({...draft,schemaVersion:'refractagent-planning-v4'})));setDirty(false)
      const result=await preview();setReport(result)
      const selected=result.strategies?.find(row=>row.id===(draft.defaultStrategy??'stage'))
      setStatus(selected?.available
        ?'已保存；当前策略可运行。其他策略的限制见零调用诊断。现有任务继续使用启动时配置。'
        :'已保存；当前策略暂不可运行，请查看零调用诊断。')}
    catch(e){setStatus(errorText(e))}finally{setBusy(false)}
  }
  async function operateLocalJudge(action:'status'|'download'|'load'|'unload'){
    setBusy(true);setStatus(action==='download'?'正在明确下载固定 revision；任务执行不会触发此操作。':'')
    try{const result=await localJudge({...draft,schemaVersion:'refractagent-planning-v4'},action)
      setLocalJudgeStatus(result);setStatus(`本地 Judge：依赖${result.installed?'已安装':'未安装'}；权重${result.downloaded?'已就绪':'未就绪'}；revision ${result.revisionVerified?'已核对':'未核对'}；本地文件 ${(result.sizeBytes/1024/1024).toFixed(1)} MiB；进程${result.loaded?'已加载':'未加载'}。`)
    }catch(error){setStatus(errorText(error))}finally{setBusy(false)}
  }
  function rolePatch(role:keyof typeof ROLES,value:Partial<NonNullable<PlanningConfig['models']>[number]>){
    const id=draft.roles?.[role]??role
    const previous=draft.models?.find(m=>m.id===id)
    const model={id,provider:'',model:'',deployment:'external-cloud',...previous,...value}
    patch({roles:{...draft.roles,[role]:id},models:[...(draft.models??[]).filter(m=>m.id!==id),model]})
  }
  function modelPatch(id:string,value:Partial<NonNullable<PlanningConfig['models']>[number]>){
    patch({models:(draft.models??[]).map(model=>model.id===id?{...model,...value}:model)})
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
  function addTaskPoolModel(provider:string,model:string){
    const existing=draft.models?.find(item=>item.provider===provider&&item.model===model)
    let id=existing?.id
    let models=draft.models??[]
    if(!id){
      const base=`task-${provider}-${model}`.replace(/[^a-zA-Z0-9_-]/g,'-')
      id=base;let index=2
      while(models.some(item=>item.id===id))id=`${base}-${index++}`
      models=[...models,{id,provider,model,deployment:'external-cloud',capabilities:{mainExecutor:true,
        toolCalling:'unknown',modalities:{}}}]
    }
    const previous=draft.task
    const pool=[...new Set([...(previous?.pool??[]),id])]
    const judge=previous?.judge??(draft.roles?.classifier
      ?{type:'llm' as const,modelId:draft.roles.classifier}
      :{type:'llm' as const,modelId:id})
    patch({models,task:{pool,fallback:previous?.fallback??id,judge,
      threshold:previous?.threshold??.8,maxInputChars:previous?.maxInputChars??12000}})
    void retrieveMetadata(provider,model,'AUTO')
  }
  function selectTaskJudgeCatalog(provider:string,model:string){
    const existing=draft.models?.find(item=>item.provider===provider&&item.model===model)
    let id=existing?.id,models=draft.models??[]
    if(!id){
      const base=`judge-${provider}-${model}`.replace(/[^a-zA-Z0-9_-]/g,'-')
      id=base;let index=2
      while(models.some(item=>item.id===id))id=`${base}-${index++}`
      models=[...models,{id,provider,model,deployment:'external-cloud',capabilities:{mainExecutor:false,
        toolCalling:'unknown',modalities:{}}}]
    }
    patch({models,task:{...draft.task!,judge:{type:'llm',modelId:id}}})
    void retrieveMetadata(provider,model,'AUTO')
  }
  function moveTaskPool(index:number,direction:-1|1){
    if(!draft.task)return
    const target=index+direction
    if(target<0||target>=draft.task.pool.length)return
    const pool=[...draft.task.pool];[pool[index],pool[target]]=[pool[target],pool[index]]
    patch({task:{...draft.task,pool}})
  }
  function mediaRoutePatch(id:string,value:Partial<MediaRouteConfig>){
    patch({mediaRoutes:(draft.mediaRoutes??[]).map(route=>route.id===id?{...route,...value}:route)})
  }
  function migrateTaskSettings(){
    const pool=[...new Set([draft.roles?.efficient,draft.roles?.capable].filter((id):id is string=>Boolean(id)))]
    if(!pool.length){setStatus('请先在上方登记至少一个模型。');return}
    patch({task:{pool,fallback:draft.roles?.capable&&pool.includes(draft.roles.capable)?draft.roles.capable:pool[0],
      judge:{type:'llm',modelId:draft.roles?.classifier??pool[0]},threshold:.8,maxInputChars:12000,
      maxExecutionOutputTokens:8192}})
  }
  function migrateEscalationSettings(){
    const initial=draft.roles?.efficient,takeover=draft.roles?.capable
    const judgeId=draft.roles?.classifier
    if(!initial||!takeover||!judgeId){setStatus('请先配置高效、强执行和任务／升级判别模型。');return}
    patch({escalation:{initial,takeover,judge:{type:'llm',modelId:judgeId},stallConfirmations:2,
      threshold:.8,judgeTimeoutMs:30000,maxJudgeInputBytes:65536,
      maxExecutionOutputTokens:8192,maxJudgeOutputTokens:1024}})
  }
  function addEscalationCatalog(field:'initial'|'takeover'|'judge',provider:string,model:string){
    const existing=draft.models?.find(item=>item.provider===provider&&item.model===model)
    let id=existing?.id,models=draft.models??[]
    if(!id){
      const base=`escalation-${field}-${provider}-${model}`.replace(/[^a-zA-Z0-9_-]/g,'-')
      id=base;let index=2
      while(models.some(item=>item.id===id))id=`${base}-${index++}`
      models=[...models,{id,provider,model,deployment:'external-cloud',capabilities:{
        mainExecutor:field!=='judge',toolCalling:'unknown',modalities:{}}}]
    }
    const current=draft.escalation??{initial:draft.roles?.efficient??id,
      takeover:draft.roles?.capable??id,judge:{type:'llm' as const,modelId:draft.roles?.classifier??id}}
    const escalation=field==='judge'?{...current,judge:{type:'llm' as const,modelId:id}}:{...current,[field]:id}
    patch({models,escalation});void retrieveMetadata(provider,model,'AUTO')
  }
  const activeModelIds=[...new Set([...Object.values(draft.roles??{}),...(draft.task?.pool??[]),
    ...(draft.task?.judge.type==='llm'?[draft.task.judge.modelId]:[]),
    ...(draft.escalation?[draft.escalation.initial,draft.escalation.takeover]:[]),
    ...(draft.escalation?.judge.type==='llm'?[draft.escalation.judge.modelId]:[])]
    .filter((id):id is string=>Boolean(id)))]
  const activeUnits=[...new Set([...activeModelIds.map(id=>{
    const unit=draft.models?.find(model=>model.id===id)?.billingUnit??draft.billingUnit??'CNY'
    return unit==='USD'?'CNY':unit
  }),...(draft.mediaRoutes??[]).map(route=>route.billingUnit==='USD'?'CNY':route.billingUnit??'CNY')])]
  const efficientModel=draft.models?.find(model=>model.id===draft.roles?.efficient)
  const capableModel=draft.models?.find(model=>model.id===draft.roles?.capable)
  const sameStageModel=Boolean(efficientModel&&capableModel&&efficientModel.provider===capableModel.provider&&
    efficientModel.model===capableModel.model&&efficientModel.reasoningEffort===capableModel.reasoningEffort)
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
    {draft.defaultStrategy==='stage'&&<div className="rra-planning-fields">
      <p>通常使用高效模型，检测到相同任务失败持续出现时切换强模型；Stage 不调用判别或审核模型。</p>
      <p className="rra-field-hint">高效：{efficientModel?`${efficientModel.provider}/${efficientModel.model} · ${efficientModel.reasoningEffort??'提供方默认推理等级'}`:'未配置'}<br/>
        强执行：{capableModel?`${capableModel.provider}/${capableModel.model} · ${capableModel.reasoningEffort??'提供方默认推理等级'}`:'未配置'}。模型与推理等级在上方通用角色设置中编辑。</p>
      {sameStageModel&&<p className="rra-field-hint" role="status">两个角色绑定相同模型和推理等级，可以运行，但不会发生实际模型切换。</p>}
      <label className="rra-compact-field">强模型保持轮数 <input className="rra-input" type="number" min="0" step="1"
        value={draft.parameters?.holdTurns??2} onChange={e=>patch({parameters:{...draft.parameters,holdTurns:Number(e.target.value)}})}/></label>
      <p className="rra-field-hint">2 轮表示触发升级的当前执行调用加下一次执行调用，共连续两次使用强模型。新的重复失败会重新开始保持期。</p>
      <details className="rra-details"><summary>Stage 高级参数</summary><div className="rra-planning-fields">
        <p>参数会在新任务开始时冻结。默认值用于首轮验证，尚未证明适合所有任务。</p>
        <label className="rra-compact-field">证据窗口 <input className="rra-input" type="number" min="1" step="1" value={draft.parameters?.window??3}
          onChange={e=>patch({parameters:{...draft.parameters,window:Number(e.target.value)}})}/><span className="rra-field-hint">默认 3：只看最近三条有效且已完成的工具结果。</span></label>
        <label className="rra-compact-field">判断阈值 <input className="rra-input" type="number" min="0" max="1" step="0.05" value={draft.parameters?.threshold??.5}
          onChange={e=>patch({parameters:{...draft.parameters,threshold:Number(e.target.value)}})}/><span className="rra-field-hint">默认 0.5：有符号评分绝对值不超过阈值时视为含糊，使用高效模型。</span></label>
      </div></details>
    </div>}
    {draft.defaultStrategy==='task'&&<div className="rra-planning-fields">
      <p>Task 在新任务开始时从模型池选择一次主执行模型；工具续接、上下文压缩和进行中的追加指导沿用该模型。</p>
      <p className="rra-field-hint">先检查任务能力、数据域和本轮预算，再逐一判断候选是否适合。达到适合度门槛后，按同一计费单位下的首次执行费用上界选择；这不是完整任务预计费用。AFP 与现金不直接比较，缺少可比证据时使用指定备援。可靠时延资料不足时沿用模型池顺序。</p>
      {!draft.task&&<div className="rra-simple-status"><strong>尚未升级 Task 设置</strong><span>旧配置仍按高效／强执行两角色运行。升级只预填草稿，不下载权重或切换默认策略。</span>
        <button className="rra-button rra-button-secondary" type="button" onClick={migrateTaskSettings}>从现有角色预填模型池</button></div>}
      {draft.task&&<>
        {draft.task.pool.length>1&&draft.task.pool.every(id=>!draft.models?.find(model=>model.id===id)?.capabilityCard)&&
          <p className="rra-field-hint" role="status">当前模型池缺少可核对的任务能力卡。本地 Judge 仍可运行，但遇到无法区分的候选会按设置使用备援模型；路由轨迹会记录原因。</p>}
        <label className="rra-compact-field">从 DSH 目录加入执行模型 <select className="rra-select" value="" onChange={e=>{
          if(!e.target.value)return;const [provider,model]=JSON.parse(e.target.value) as string[];addTaskPoolModel(provider,model)}}>
          <option value="">选择并加入…</option>{catalog?.groups.filter(group=>group.id!=='refractagent').map(group=><optgroup key={group.id} label={group.name}>
            {group.models.map(model=><option key={model.id} value={JSON.stringify([group.id,model.id])}>{model.name}</option>)}</optgroup>)}</select></label>
        <div className="rra-planning-fields">{draft.task.pool.map((id,index)=>{
          const model=draft.models?.find(row=>row.id===id)
          if(!model)return <p key={id} role="status">缺少模型配置：{id}</p>
          const catalogModel=catalog?.groups.find(group=>group.id===model.provider)?.models.find(row=>row.id===model.model)
          const efforts=catalogModel?.reasoning?.efforts??[]
          const caps=model.capabilities?.modalities??{}
          return <div className="rra-row-card" key={id}><div className="rra-section-head"><div><strong>{index+1}. {model.provider}/{model.model}</strong><p className="rra-field-hint">优先顺序由上到下；首次执行费用上界相同且没有可比时延数据时，选择靠前模型。</p></div>
            <div className="rra-actions"><button type="button" className="rra-button rra-button-secondary" disabled={index===0} onClick={()=>moveTaskPool(index,-1)}>上移</button>
            <button type="button" className="rra-button rra-button-secondary" disabled={index===draft.task!.pool.length-1} onClick={()=>moveTaskPool(index,1)}>下移</button>
            <button type="button" className="rra-button rra-button-secondary" disabled={draft.task!.pool.length===1} onClick={()=>{
              const pool=draft.task!.pool.filter(value=>value!==id)
              patch({task:{...draft.task!,pool,fallback:draft.task!.fallback===id?pool[0]:draft.task!.fallback}})}}>移除</button></div></div>
            <label className="rra-compact-field">推理等级 <select className="rra-select" value={model.reasoningEffort??''} onChange={e=>modelPatch(id,{reasoningEffort:e.target.value||undefined})}>
              <option value="">使用提供方默认</option>{efforts.map(entry=><option key={entry.id} value={entry.id}>{entry.name}</option>)}</select></label>
            <p className="rra-field-hint">工具调用：{model.capabilities?.toolCalling??'unknown'}；图片输入：{caps.imageInput??'unknown'}；影片输入：{caps.videoInput??'unknown'}；图片输出：{caps.imageOutput??'unknown'}；影片输出：{caps.videoOutput??'unknown'}。</p>
            <p className="rra-field-hint">能力来源：{model.capabilities?.source??(model.capabilityCard?'见下方任务能力说明':'尚未查证')}{model.capabilities?.checkedAt?`（${model.capabilities.checkedAt}）`:''}。只有 connected／verified 会进入对应媒体任务候选。</p>
            <p className="rra-field-hint">任务能力说明：{model.capabilityCard??'尚无可核对资料'}<br/>官方声明与本项目已验收能力需分别核对。</p>
          </div>})}</div>
        <label className="rra-compact-field">不确定时的强执行备援 <select className="rra-select" value={draft.task.fallback} onChange={e=>patch({task:{...draft.task!,fallback:e.target.value}})}>
          {draft.task.pool.map(id=><option key={id} value={id}>{id}</option>)}</select></label>
        <label className="rra-compact-field">Judge 类型 <select className="rra-select" value={draft.task.judge.type} onChange={e=>patch({task:{...draft.task!,judge:e.target.value==='local-decision'
          ?{type:'local-decision',adapter:'laya-mlx',modelPath:'',sourceModel:'aac6fef/laya-multilingual-mlx',
            revision:'f2b4faf51023039425946074e2cf1361d2db11d5',device:'gpu',dtype:'float16',method:'ordinal-v1'}
          :{type:'llm',modelId:draft.roles?.classifier??draft.task!.pool[0]}}})}>
          <option value="llm">轻量 LLM Judge</option><option value="local-decision">本地结构化 Judge（Laya-MLX）</option></select></label>
        {draft.task.judge.type==='local-decision'&&<p className="rra-field-hint">模型已就绪只表示本地推论可运行；选模质量需用有标注任务验证。不确定时使用上方指定备援。</p>}
        {draft.task.judge.type==='llm'?<div className="rra-planning-fields"><label className="rra-compact-field">从 DSH 目录选择 Judge <select className="rra-select" value="" onChange={e=>{
          if(!e.target.value)return;const [provider,model]=JSON.parse(e.target.value) as string[];selectTaskJudgeCatalog(provider,model)}}>
          <option value="">选择并登记…</option>{catalog?.groups.filter(group=>group.id!=='refractagent').map(group=><optgroup key={group.id} label={group.name}>
            {group.models.map(model=><option key={model.id} value={JSON.stringify([group.id,model.id])}>{model.name}</option>)}</optgroup>)}</select></label>
          <label className="rra-compact-field">Judge 模型 <select className="rra-select" value={draft.task.judge.modelId} onChange={e=>patch({task:{...draft.task!,judge:{type:'llm',modelId:e.target.value}}})}>
            {(draft.models??[]).map(model=><option key={model.id} value={model.id}>{model.id} · {model.provider}/{model.model}</option>)}</select><span className="rra-field-hint">Judge 不必属于执行模型池；每个任务最多调用一次，工具关闭，结构化输出无自动修复。</span></label></div>:
          <div className="rra-planning-fields">
            <p className="rra-field-hint">推荐 checkpoint：aac6fef/laya-multilingual-mlx。任务执行不会隐式下载；路径必须指向已核对 revision 的本地目录。</p>
            <label className="rra-compact-field">本地权重目录 <input className="rra-input" value={draft.task.judge.modelPath} onChange={e=>patch({task:{...draft.task!,judge:{...draft.task!.judge as Extract<typeof draft.task.judge,{type:'local-decision'}>,modelPath:e.target.value}}})}/></label>
            <label className="rra-compact-field">固定 revision <input className="rra-input" value={draft.task.judge.revision??''} onChange={e=>patch({task:{...draft.task!,judge:{...draft.task!.judge as Extract<typeof draft.task.judge,{type:'local-decision'}>,revision:e.target.value}}})}/><span className="rra-field-hint">推荐多语言 checkpoint 当前验收 revision：f2b4faf51023039425946074e2cf1361d2db11d5。</span></label>
            <div className="rra-grid rra-grid-2"><label className="rra-compact-field">装置 <select className="rra-select" value={draft.task.judge.device??'gpu'} onChange={e=>patch({task:{...draft.task!,judge:{...draft.task!.judge as Extract<typeof draft.task.judge,{type:'local-decision'}>,device:e.target.value as 'gpu'|'metal'|'cpu'}}})}><option value="gpu">GPU／MLX</option><option value="metal">Metal</option><option value="cpu">CPU</option></select></label>
              <label className="rra-compact-field">精度 <select className="rra-select" value={draft.task.judge.dtype??'float16'} onChange={e=>patch({task:{...draft.task!,judge:{...draft.task!.judge as Extract<typeof draft.task.judge,{type:'local-decision'}>,dtype:e.target.value as 'float16'|'float32'|'bfloat16'}}})}><option>float16</option><option>float32</option><option>bfloat16</option></select></label></div>
            <div className="rra-actions"><button className="rra-button rra-button-secondary" type="button" disabled={busy} onClick={()=>void operateLocalJudge('status')}>检查本地状态</button>
              <button className="rra-button rra-button-secondary" type="button" disabled={busy||!draft.task.judge.modelPath||!draft.task.judge.revision} onClick={()=>void operateLocalJudge('download')}>下载固定权重</button>
              <button className="rra-button rra-button-secondary" type="button" disabled={busy||!draft.task.judge.modelPath} onClick={()=>void operateLocalJudge('load')}>加载并预热</button>
              <button className="rra-button rra-button-secondary" type="button" disabled={busy||!localJudgeStatus?.loaded} onClick={()=>void operateLocalJudge('unload')}>卸载</button></div>
          </div>}
        <details className="rra-details"><summary>Task 高级参数</summary><div className="rra-planning-fields">
          {draft.task.judge.type==='local-decision'&&<label className="rra-compact-field">本地判别问法 <select className="rra-select" value={draft.task.judge.method??'ordinal-v1'} onChange={e=>patch({task:{...draft.task!,judge:{...draft.task!.judge as Extract<typeof draft.task.judge,{type:'local-decision'}>,method:e.target.value as 'ordinal-v1'|'choice-v2'}}})}>
            <option value="ordinal-v1">逐候选评分（支持费用排序）</option><option value="choice-v2">候选直选（实验）</option></select><span className="rra-field-hint">直选只评价被选中的候选，无法证明其他候选也达到质量门槛，因此不能进行候选间费用排序。两种问法的分数不能相互比较，实验问法尚未通过真实选模质量验收。</span></label>}
          <label className="rra-compact-field">每次执行输出上限 <input className="rra-input" type="number" min="256" step="1" value={draft.task.maxExecutionOutputTokens??8192} onChange={e=>patch({task:{...draft.task!,maxExecutionOutputTokens:Number(e.target.value)}})}/><span className="rra-field-hint">默认 8192 tokens。模型目录的输出容量是接口上限；预算按这里的实际执行上限预留。宿主设置更小时，以较小值为准。</span></label>
          <label className="rra-compact-field">{draft.task.judge.type==='local-decision'&&draft.task.judge.method==='choice-v2'?'选择概率门槛':'适合度门槛'} <input className="rra-input" type="number" min="0" max="1" step="0.05" value={draft.task.threshold??.8} onChange={e=>patch({task:{...draft.task!,threshold:Number(e.target.value)}})}/><span className="rra-field-hint">默认 0.8，为待校准的产品初始值，不表示任务成功率。</span></label>
          <label className="rra-compact-field">Judge 文字输入上限 <input className="rra-input" type="number" min="512" step="1" value={draft.task.maxInputChars??12000} onChange={e=>patch({task:{...draft.task!,maxInputChars:Number(e.target.value)}})}/><span className="rra-field-hint">超出时不截断后继续判别，改用已验证合格的指定备援。</span></label>
        </div></details>
      </>}
    </div>}
    {draft.defaultStrategy==='escalation'&&<div className="rra-planning-fields">
      <p>先缓冲起始模型回复，由 Judge 判定后放行；明确缺陷、最终回复停滞或无法判断时，由接管模型继续当前任务。</p>
      {!draft.escalation&&<div className="rra-simple-status"><strong>尚未升级 Escalation 设置</strong>
        <span>旧配置仍使用通用高效、强执行和判别角色。升级只预填草稿，不切换默认策略。</span>
        <button className="rra-button rra-button-secondary" type="button" onClick={migrateEscalationSettings}>从现有角色预填</button></div>}
      {draft.escalation&&<>
        {(['initial','takeover'] as const).map(field=>{const id=draft.escalation![field]
          const model=draft.models?.find(item=>item.id===id)
          const efforts=catalog?.groups.find(group=>group.id===model?.provider)?.models
            .find(item=>item.id===model?.model)?.reasoning?.efforts??[]
          return <div className="rra-row-card" key={field}><strong>{field==='initial'?'起始执行模型':'强模型接管'}</strong>
            <label className="rra-compact-field">从 DSH 目录选择 <select className="rra-select" value="" onChange={e=>{
              if(!e.target.value)return;const [provider,selected]=JSON.parse(e.target.value) as string[]
              addEscalationCatalog(field,provider,selected)}}><option value="">选择并登记…</option>
              {catalog?.groups.filter(group=>group.id!=='refractagent').map(group=><optgroup key={group.id} label={group.name}>
                {group.models.map(item=><option key={item.id} value={JSON.stringify([group.id,item.id])}>{item.name}</option>)}</optgroup>)}</select></label>
            <label className="rra-compact-field">复用已登记配置 <select className="rra-select" value={id} onChange={e=>patch({
              escalation:{...draft.escalation!,[field]:e.target.value}})}>{draft.models?.map(item=><option key={item.id} value={item.id}>
                {item.id} · {item.provider}/{item.model}</option>)}</select></label>
            {model&&<label className="rra-compact-field">推理等级 <select className="rra-select" value={model.reasoningEffort??''}
              onChange={e=>modelPatch(model.id,{reasoningEffort:e.target.value||undefined})}><option value="">使用提供方默认</option>
              {efforts.map(entry=><option key={entry.id} value={entry.id}>{entry.name}</option>)}</select></label>}
            {model&&<div className="rra-grid rra-grid-2"><label className="rra-compact-field">数据域 <select className="rra-select" value={model.deployment??'external-cloud'}
              onChange={e=>modelPatch(model.id,{deployment:e.target.value,trustPolicy:e.target.value==='trusted-cloud'?model.trustPolicy:undefined})}>
              <option value="external-cloud">外部云</option><option value="trusted-cloud">已授权的可信云</option><option value="local">本地部署</option></select></label>
              {model.deployment==='trusted-cloud'&&<label className="rra-compact-field">信任策略 <select className="rra-select" value={model.trustPolicy??''}
                onChange={e=>modelPatch(model.id,{trustPolicy:e.target.value||undefined})}><option value="">选择已登记的许可…</option>
                {draft.trustPolicies?.map(policy=><option key={String(policy.id)} value={String(policy.id)}>{String(policy.id)}</option>)}</select></label>}</div>}
          </div>})}
        {draft.escalation.initial===draft.escalation.takeover&&<p role="status">起始与接管模型不能相同，否则无法形成有效接管。</p>}
        <label className="rra-compact-field">Judge 类型 <select className="rra-select" value={draft.escalation.judge.type}
          onChange={e=>patch({escalation:{...draft.escalation!,judge:e.target.value==='local-decision'
            ?{type:'local-decision',adapter:'laya-mlx',modelPath:'',sourceModel:'aac6fef/laya-multilingual-mlx',
              revision:'f2b4faf51023039425946074e2cf1361d2db11d5',device:'gpu',dtype:'float16',method:'choice-v2'}
            :{type:'llm',modelId:draft.roles?.classifier??draft.escalation!.initial}}})}>
          <option value="llm">轻量 LLM Judge</option><option value="local-decision">本地结构化 Judge（Laya-MLX）</option></select></label>
        {draft.escalation.judge.type==='llm'?<>
          <label className="rra-compact-field">从 DSH 目录选择 Judge <select className="rra-select" value="" onChange={e=>{
            if(!e.target.value)return;const [provider,selected]=JSON.parse(e.target.value) as string[]
            addEscalationCatalog('judge',provider,selected)}}><option value="">选择并登记…</option>
            {catalog?.groups.filter(group=>group.id!=='refractagent').map(group=><optgroup key={group.id} label={group.name}>
              {group.models.map(item=><option key={item.id} value={JSON.stringify([group.id,item.id])}>{item.name}</option>)}</optgroup>)}</select></label>
          <label className="rra-compact-field">Judge 模型 <select className="rra-select" value={draft.escalation.judge.modelId}
            onChange={e=>patch({escalation:{...draft.escalation!,judge:{type:'llm',modelId:e.target.value}}})}>
            {draft.models?.map(item=><option key={item.id} value={item.id}>{item.id} · {item.provider}/{item.model}</option>)}</select></label>
          {(()=>{const judge=draft.escalation?.judge
            const model=judge?.type==='llm'?draft.models?.find(item=>item.id===judge.modelId):undefined
            if(!model)return null
            const efforts=catalog?.groups.find(group=>group.id===model.provider)?.models.find(item=>item.id===model.model)?.reasoning?.efforts??[]
            return <div className="rra-row-card"><label className="rra-compact-field">Judge 推理等级 <select className="rra-select" value={model.reasoningEffort??''}
              onChange={e=>modelPatch(model.id,{reasoningEffort:e.target.value||undefined})}><option value="">使用提供方默认</option>
              {efforts.map(entry=><option key={entry.id} value={entry.id}>{entry.name}</option>)}</select></label>
              <div className="rra-grid rra-grid-2"><label className="rra-compact-field">Judge 数据域 <select className="rra-select" value={model.deployment??'external-cloud'}
                onChange={e=>modelPatch(model.id,{deployment:e.target.value,trustPolicy:e.target.value==='trusted-cloud'?model.trustPolicy:undefined})}>
                <option value="external-cloud">外部云</option><option value="trusted-cloud">已授权的可信云</option><option value="local">本地部署</option></select></label>
                {model.deployment==='trusted-cloud'&&<label className="rra-compact-field">Judge 信任策略 <select className="rra-select" value={model.trustPolicy??''}
                  onChange={e=>modelPatch(model.id,{trustPolicy:e.target.value||undefined})}><option value="">选择已登记的许可…</option>
                  {draft.trustPolicies?.map(policy=><option key={String(policy.id)} value={String(policy.id)}>{String(policy.id)}</option>)}</select></label>}</div>
              {model.provider==='ark'&&model.model==='glm-5.3-flash'&&<p role="status">当前 Agent Plan 路线不支持关闭思考；真实验收中默认思考占满 1024 token 判别输出。增加输出上限并重新验收前，请将它视为实验 Judge。</p>}
            </div>})()}
        </>:<div className="rra-planning-fields">
          <label className="rra-compact-field">本地权重目录 <input className="rra-input" value={draft.escalation.judge.modelPath}
            onChange={e=>patch({escalation:{...draft.escalation!,judge:{...draft.escalation!.judge as Extract<typeof draft.escalation.judge,{type:'local-decision'}>,modelPath:e.target.value}}})}/></label>
          <label className="rra-compact-field">固定 revision <input className="rra-input" value={draft.escalation.judge.revision??''}
            onChange={e=>patch({escalation:{...draft.escalation!,judge:{...draft.escalation!.judge as Extract<typeof draft.escalation.judge,{type:'local-decision'}>,revision:e.target.value}}})}/></label>
          <div className="rra-actions"><button className="rra-button rra-button-secondary" type="button" disabled={busy} onClick={()=>void operateLocalJudge('status')}>检查本地状态</button>
            <button className="rra-button rra-button-secondary" type="button" disabled={busy||!draft.escalation.judge.modelPath||!draft.escalation.judge.revision} onClick={()=>void operateLocalJudge('download')}>下载固定权重</button>
            <button className="rra-button rra-button-secondary" type="button" disabled={busy||!draft.escalation.judge.modelPath} onClick={()=>void operateLocalJudge('load')}>加载并预热</button>
            <button className="rra-button rra-button-secondary" type="button" disabled={busy||!localJudgeStatus?.loaded} onClick={()=>void operateLocalJudge('unload')}>卸载</button></div>
          {localJudgeStatus&&<p role="status">本地 Judge：{localJudgeStatus.loaded?'已加载并预热':localJudgeStatus.downloaded?'权重已下载，尚未加载':'尚未就绪'}；revision {localJudgeStatus.revisionVerified?'已核对':'未核对'}。</p>}
          <p className="rra-field-hint">固定多语言 Laya revision 的 24 条 Escalation 案例仅匹配 5 条，尚未达到日常使用门槛；当前保留为低时延实验后端。</p>
        </div>}
        <p className="rra-field-hint">接管后本任务固定使用强模型，不再调用 Judge；轨迹会注明“接管后未追加审核”。</p>
        <details className="rra-details"><summary>Escalation 高级参数</summary><div className="rra-planning-fields">
          <label className="rra-compact-field">工具过程连续停滞次数 <input className="rra-input" type="number" min="1" step="1" value={draft.escalation.stallConfirmations??2} onChange={e=>patch({escalation:{...draft.escalation!,stallConfirmations:Number(e.target.value)}})}/></label>
          <label className="rra-compact-field">本地判别确定性门槛 <input className="rra-input" type="number" min="0" max="1" step="0.05" value={draft.escalation.threshold??.8} onChange={e=>patch({escalation:{...draft.escalation!,threshold:Number(e.target.value)}})}/></label>
          <label className="rra-compact-field">Judge 期限（毫秒） <input className="rra-input" type="number" min="100" step="100" value={draft.escalation.judgeTimeoutMs??30000} onChange={e=>patch({escalation:{...draft.escalation!,judgeTimeoutMs:Number(e.target.value)}})}/></label>
          <label className="rra-compact-field">Judge 输入包络（bytes） <input className="rra-input" type="number" min="1024" step="1024" value={draft.escalation.maxJudgeInputBytes??65536} onChange={e=>patch({escalation:{...draft.escalation!,maxJudgeInputBytes:Number(e.target.value)}})}/></label>
          <label className="rra-compact-field">执行输出上限 <input className="rra-input" type="number" min="256" step="1" value={draft.escalation.maxExecutionOutputTokens??8192} onChange={e=>patch({escalation:{...draft.escalation!,maxExecutionOutputTokens:Number(e.target.value)}})}/></label>
          <label className="rra-compact-field">LLM Judge 输出上限 <input className="rra-input" type="number" min="64" step="1" value={draft.escalation.maxJudgeOutputTokens??1024} onChange={e=>patch({escalation:{...draft.escalation!,maxJudgeOutputTokens:Number(e.target.value)}})}/></label>
        </div></details>
      </>}
    </div>}
    {draft.defaultStrategy==='static'&&<details className="rra-details"><summary>Static 设置</summary><div className="rra-planning-fields">
      <p>参数尚未校准。修改只影响新任务。</p>
      <>
        <p className="rra-field-hint">选模方式默认「固定高效角色」，这是当前程序默认值，不表示你曾主动设置。</p>
        <label className="rra-compact-field">选模方式 <select className="rra-select" value={draft.parameters?.staticMode??'fixed'} onChange={e=>patch({parameters:{...draft.parameters,staticMode:e.target.value}})}>
          <option value="fixed">固定高效执行模型</option><option value="random">按权重每任务随机选择一次</option></select></label>
        {(draft.parameters?.staticMode??'fixed')==='fixed'&&<p className="rra-field-hint">当前固定使用上方「高效执行模型」：{draft.models?.find(m=>m.id===draft.roles?.efficient)?.provider??'未配置'}/{draft.models?.find(m=>m.id===draft.roles?.efficient)?.model??'未配置'}；其推理等级读取该模型的「推理等级」字段。</p>}
      </>
      {Object.entries({window:3,threshold:.5,holdTurns:2,baseThreshold:.5,thresholdStep:.1,maxReviews:1,maxRedos:1,stallTurns:0,confirmations:2,seed:0,efficientWeight:1,capableWeight:1}).filter(([key])=>({stage:['window','threshold','holdTurns'],task:['baseThreshold','thresholdStep'],composite:['window','threshold','holdTurns','baseThreshold','thresholdStep'],advisor:['maxReviews','maxRedos','stallTurns'],escalation:['confirmations'],static:(draft.parameters?.staticMode??'fixed')==='random'?['seed','efficientWeight','capableWeight']:[]}[draft.defaultStrategy??'stage']).includes(key)).map(([key,value])=>
        <label className="rra-compact-field" key={key}>{({window:'证据窗口',threshold:'阶段判断阈值',holdTurns:'强模型保持轮数',baseThreshold:'任务基础阈值',
            thresholdStep:'能力边界修正步长',maxReviews:'审核次数上限',maxRedos:'返工次数上限',
            stallTurns:'停滞审核轮数（0 为关闭）',confirmations:'连续升级判断次数',seed:'随机种子',
            efficientWeight:'高效模型权重',capableWeight:'强模型权重'} as Record<string,string>)[key]} <input className="rra-input" type="number"  step="any" value={draft.parameters?.[key]??value}
          onChange={e=>patch({parameters:{...draft.parameters,[key]:Number(e.target.value)}})}/></label>)}
      </div></details>}
    {draft.defaultStrategy!=='stage'&&draft.defaultStrategy!=='static'&&draft.defaultStrategy!=='task'&&draft.defaultStrategy!=='escalation'&&<details className="rra-details"><summary>策略参数</summary><div className="rra-planning-fields">
      <p>参数尚未校准。修改只影响新任务。</p>
      {Object.entries({window:3,threshold:.5,holdTurns:2,baseThreshold:.5,thresholdStep:.1,maxReviews:1,maxRedos:1,stallTurns:0,confirmations:2}).filter(([key])=>(({task:['baseThreshold','thresholdStep'],composite:['window','threshold','holdTurns','baseThreshold','thresholdStep'],advisor:['maxReviews','maxRedos','stallTurns'],escalation:['confirmations']} as Record<string,string[]>)[draft.defaultStrategy??'task']??[]).includes(key)).map(([key,value])=>
        <label className="rra-compact-field" key={key}>{({window:'证据窗口',threshold:'阶段判断阈值',holdTurns:'强模型保持轮数',baseThreshold:'任务基础阈值',thresholdStep:'能力边界修正步长',maxReviews:'审核次数上限',maxRedos:'返工次数上限',stallTurns:'停滞审核轮数（0 为关闭）',confirmations:'连续升级判断次数'} as Record<string,string>)[key]} <input className="rra-input" type="number" step="any" value={draft.parameters?.[key]??value} onChange={e=>patch({parameters:{...draft.parameters,[key]:Number(e.target.value)}})}/></label>)}
    </div></details>}</div>
    <div className="rra-row-card"><h3>图片与影片路线</h3>
      <p className="rra-field-hint">系统资料会区分“提供方声明、适配已接通、真实验收”。只有 verified 路线能由受管工具派发。价格与接口由系统预设，不能手填。</p>
      {!(draft.mediaRoutes??[]).some(route=>route.id===SEEDREAM_CONNECTED.id)&&<button type="button" className="rra-button rra-button-secondary" onClick={()=>patch({mediaRoutes:[...(draft.mediaRoutes??[]),structuredClone(SEEDREAM_CONNECTED)]})}>加入 Ark Agent Plan Seedream 已接通路线</button>}
      {(draft.mediaRoutes??[]).map(route=><div className="rra-row-card" key={route.id}>
        <div className="rra-section-head"><div><strong>{route.provider}/{route.model}</strong><p className="rra-field-hint">{route.operations.join('、')}；{route.pricing?.unitCost??'待核对'} {route.billingUnit??'未知'}/{route.pricing?.basis??'单位'}；状态 {route.verification??(route.verified?'verified':'declared')}</p></div>
          <button type="button" className="rra-button rra-button-secondary" onClick={()=>patch({mediaRoutes:(draft.mediaRoutes??[]).filter(item=>item.id!==route.id)})}>移除</button></div>
        <div className="rra-grid rra-grid-2"><label className="rra-compact-field">数据域 <select className="rra-select" value={route.deployment??'external-cloud'} onChange={e=>mediaRoutePatch(route.id,{deployment:e.target.value,trustPolicy:e.target.value==='trusted-cloud'?route.trustPolicy:undefined})}>
          <option value="external-cloud">外部云</option><option value="trusted-cloud">已授权的可信云</option><option value="local">本地部署</option></select></label>
          {route.deployment==='trusted-cloud'&&<label className="rra-compact-field">信任策略 <select className="rra-select" value={route.trustPolicy??''} onChange={e=>mediaRoutePatch(route.id,{trustPolicy:e.target.value||undefined})}>
            <option value="">选择已登记的许可…</option>{draft.trustPolicies?.map(policy=><option key={String(policy.id)} value={String(policy.id)}>{String(policy.id)}</option>)}</select></label>}</div>
        <p className="rra-field-hint">价格来源：{route.pricing?.source??'尚未核对'}{route.pricing?.checkedAt?`（${route.pricing.checkedAt}）`:''}。凭证复用 DSH provider：{route.credentialProvider??route.provider}。</p>
        {(route.verification??(route.verified?'verified':'declared'))!=='verified'&&<p role="status">尚未完成真实付费接口验收，当前只保存接线与官方资料，不会派发生成请求。</p>}
      </div>)}
      <p role="status">当前 DSH 0.1.5 只有原生图片内容块与图片附件服务；尚无影片内容块、上传、播放器和影片附件合同，因此影片路线不会显示为已接通或已验收。</p>
    </div>
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
    {report&&<div className="rra-issue-summary" role="status">{report.issues?.map((s,i)=><p key={i}>{s}</p>)}{report.strategies?.map(s=><p key={s.id}>{s.name}：{s.available?'可用':s.issues.join('；')}</p>)}
      {report.mediaRoutes?.map(route=><p key={route.id}>媒体 {route.provider}/{route.model}：{route.available?'已验收可用':route.issues.join('；')}</p>)}<p>{report.coverage}</p></div>}
  </section>
}
type TaskRouteEvidence={candidateId?:string;reason?:string;costBasis?:string;latencyBasis?:string;
  candidateAssessments?:Array<{candidateId:string;score:number;missingInformation:number;qualified:boolean}>;
  firstCallUpperBounds?:Record<string,{amount:number;unit:string}>;qualifiedCandidates?:string[];
  decision?:TaskRouteEvidence}
type History={records:Array<{runId:string;strategy:string;status:string;costs:{production:number|null};billingUnit:string|null;billingWarning?:string;
  costsByUnit?:Record<string,{production:number;evaluation:number}>;
  calls:Array<{call_id?:string;label?:string;model_id:string;provider?:string;actual_model?:string;purpose:string;disposition:string;status?:string;charged:number;billing_unit?:string;latency_ms?:number;ttft_ms?:number;reasoning_effort?:string;usage_type?:string;usage?:{basis?:string;actualUnits?:number;maximumUnits?:number}}>;
  decisions:Array<{callId?:string;reason:string;score?:number|null;evidenceIds?:string[];evidenceSummary?:string;holdBefore?:number;holdAfter?:number;ruleVersion?:string;
    streakBefore?:number;streakAfter?:number;takeoverUnreviewed?:boolean;
    decision?:TaskRouteEvidence&{backend?:string;coldStartMs?:number;latencyMs?:number};judgeDecision?:TaskRouteEvidence;
    rejectedCandidates?:Array<{id:string;reason:string}>}>}>}
const REASON:Record<string,string>={fixed:'固定模型','no-signal':'无有效信号，保持高效','ambiguous':'证据含糊，保持高效',
  'repeated-failure':'重复失败，升级强模型','capable-hold':'强模型保持期','tool-signal':'Stage 信号选模',
  'task-classifier':'任务判别','task-local-judge':'本地 Judge 判别','single-eligible-candidate':'单一合格候选',
  'local-judge-uncertain':'本地 Judge 不确定，使用指定备援',
  'local-judge-no-capability-evidence':'缺少能力卡，使用指定备援',
  'local-judge-no-differentiating-evidence':'候选缺少区分证据，使用指定备援',
  'local-judge-capacity':'本地 Judge 输入超出容量，使用指定备援',
  'quality-then-first-call-cost':'质量达标后按首次调用费用上界选择',
  'no-quality-qualified-candidate':'无质量达标候选，使用指定备援',
  'incomparable-billing-units':'候选计费单位不可比较，使用指定备援',
  'single-choice-no-comparative-evidence':'直选仅有单一候选证据，未比较费用',
  'escalation-latch':'升级锁定','escalation-initial':'起始模型候选',
  'escalation-proceed':'Judge 放行','escalation-defect':'明确缺陷，立即接管',
  'escalation-stall':'工具过程疑似停滞','escalation-final-stall':'最终回复停滞，立即接管',
  'escalation-uncertain':'Judge 无法判断，交给强模型',
  'escalation-takeover-unreviewed':'强模型接管后未追加审核'}
function TaskEvidence({row}:{row:History['records'][number]['decisions'][number]}){
  const value=row.judgeDecision?.decision??row.judgeDecision??row.decision
  if(!value?.candidateAssessments?.length&&!row.rejectedCandidates?.length)return null
  return <details><summary>查看 Task 判别依据</summary>
    {value?.candidateAssessments?.map(item=><p key={item.candidateId}>{item.candidateId}：
      {item.qualified?'达到初始门槛':'未达到初始门槛'}；适合度信号 {item.score.toFixed(3)}；
      关键信息不足信号 {item.missingInformation.toFixed(3)}；
      首次执行费用上界 {value.firstCallUpperBounds?.[item.candidateId]
        ?`${value.firstCallUpperBounds[item.candidateId].amount.toFixed(4)} ${value.firstCallUpperBounds[item.candidateId].unit}`:'未核对'}</p>)}
    {row.rejectedCandidates?.map(item=><p key={item.id}>排除 {item.id}：{item.reason}</p>)}
    {value?.costBasis&&<p>费用依据：{value.costBasis==='first-execution-upper-bound'?'首次执行调用保守上界；不代表完整任务预计费用':'不可比较'}。
      时延依据：{value.latencyBasis==='unavailable'?'暂无可靠可比数据，平价时按模型池顺序':'已核对样本'}。</p>}
  </details>
}
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
      {r.calls.some(c=>c.status==='unknown-usage'||c.status==='reserved')&&<p role="status">以上金额包含尚未结算的预留，不等于已确认扣费。用量待核对的调用不会自动重发。</p>}
      <table><thead><tr>{['模型／推理等级','用途','交付状态','本次金额／累计占用','首字／总耗时 ms','决策与证据'].map(h=><th key={h}>{h}</th>)}</tr></thead>
        <tbody>{(()=>{const totals:Record<string,number>={};return r.calls.map(c=>{const unit=c.billing_unit??r.billingUnit??'';totals[unit]=(totals[unit]??0)+c.charged
          const d=r.decisions.find(row=>row.callId===c.call_id)
          return <tr key={c.call_id??c.label}><td>{c.provider&&c.actual_model?`${c.provider}/${c.actual_model}`:c.model_id}<br/><small>{c.usage_type==='non-token'?`${c.usage?.actualUnits??c.usage?.maximumUnits??'待核对'} ${c.usage?.basis??'媒体单位'}`:c.reasoning_effort??'提供方默认'}</small></td><td>{c.purpose}</td><td>{c.disposition??c.status}{(c as unknown as {review_status?:string}).review_status==='revised-unreviewed'?' · 未复审':''}</td>
          <td>{c.status==='unknown-usage'?'用量待核对，保留预留：':c.status==='reserved'?'尚未派发预留：':''}{c.charged}{r.billingWarning?'（单位待核对）':unit?` ${unit}`:''}<br/><small>累计占用 {totals[unit]}{unit?` ${unit}`:''}</small></td><td>{c.ttft_ms?.toFixed(0)??'待核对'}／{c.latency_ms?.toFixed(0)??'待核对'}</td>
          <td>{REASON[d?.reason??'']??d?.reason??'策略判别'}{typeof d?.score==='number'?`（评分 ${d.score.toFixed(3)}）`:''}<br/>
            <small>{d?.evidenceSummary??(d?.decision?.backend?`后端 ${d.decision.backend}`:'旧记录无证据摘要')}{d?.holdBefore!==undefined?`；保持 ${d.holdBefore} → ${d.holdAfter}`:''}{d?.streakBefore!==undefined?`；连续停滞 ${d.streakBefore} → ${d.streakAfter}`:''}{d?.decision?.coldStartMs!==undefined?`；冷启动 ${d.decision.coldStartMs.toFixed(0)} ms`:''}{d?.ruleVersion?`；${d.ruleVersion}`:''}</small>{d&&<TaskEvidence row={d}/>}</td></tr>})})()}</tbody></table></article>)}
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
    localJudge:async(config,action)=>{const r=await ctx.remote.llm.discoverModels('refractagent-planning',{
      provider:JSON.stringify(config),api:'local-judge:'+action})
      if(!r.ok)throw new Error(r.error?.message??'本地 Judge 操作失败')
      return JSON.parse(r.value?.[0]?.name??'{}') as {installed:boolean;downloaded:boolean;loaded:boolean;path:string;sourceModel:string;revision:string;revisionVerified:boolean;sizeBytes:number}},
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
