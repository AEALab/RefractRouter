/** RefractAgent 设置卡片：遵循宿主卡片外观与表单交互。 */
import { useEffect, useState } from 'react'
import examples from '../provider-examples.json' with { type: 'json' }
import v4Example from '../../../../../data/schema/refractagent-providers-v4-example.json' with { type: 'json' }
import { afpMetadata, candidateChoices, MODE_KEYS, type CardField, type LimitKey, type ModeKey,
  type RefractCardProjection, type V4CollectionKey, type V4DagMode, type V4DataMode } from '../settings-card.js'
import type {DshModelPoolView,RouterConnectionView} from '../settings-card.js'
import type {DshModelCatalog,RouterProjectDirectory} from './types.js'
import { V4Settings } from './v4-settings.js'

export interface RefractCardOwnerProps {
  t: (key: string) => string
  useRefractCard: <T>(selector: (snapshot: RefractCardProjection) => T) => T
  editPlannerThinking(value: string): void
  editDefaultEffort(value: string): void
  editStrategyEffort(mode: ModeKey, value: string): void
  editStrategyAfpCeiling(mode: ModeKey, value: string): void
  editStrategyModels(mode: ModeKey, text: string): void
  editV4QualityMin(value: number): void
  editV4DagMode(value: V4DagMode): void
  editV4DataMode(value: V4DataMode): void
  editV4SensitiveTerms(text: string): void
  editV4Classifier(enabled: boolean, modelId?: string): void
  upsertV4Row(collection: V4CollectionKey, value: Record<string, unknown>, previousId?: string): void
  removeV4Row(collection: V4CollectionKey, id: string): void
  editLimit(key: LimitKey, checked: boolean): void
  editProviderJson(text: string): void
  editDshModelPool(value:DshModelPoolView):void
  editRouter(value:RouterConnectionView|undefined):void
  loadCatalog():Promise<DshModelCatalog>
  loadRouterProjects(connection:{url:string;credential?:string}):Promise<RouterProjectDirectory>
  resetField(field: CardField): void
  save(): void
  discard(): void
}

const EFFORTS = ['minimal', 'low', 'medium', 'high', 'xhigh']

const STRATEGY_LABEL_KEYS: Record<ModeKey, string> = {
  economy: 'strategyEconomy',
  balanced: 'strategyBalanced',
  quality: 'strategyQuality',
}

const css = `
.rra-card{border:1px solid var(--dsw-alias-border-l2);border-radius:12px;list-style:none;background:var(--dsw-alias-bg-layer-3);transition:border-color .16s,background .16s}
.rra-card:hover,.rra-card-open{border-color:var(--dsw-alias-label-dimmed)}
.rra-card-open{background:var(--dsw-alias-bg-layer-2)}
.rra-head{appearance:none;width:100%;font:inherit;color:inherit;text-align:left;cursor:pointer;background:none;border:0;border-radius:12px;display:flex;align-items:center;gap:12px;padding:14px 16px}
.rra-head-text{display:flex;flex:1;flex-direction:column;gap:4px;min-width:0}
.rra-name{color:var(--dsw-alias-label-primary);font-size:15px;font-weight:600;line-height:1.4}
.rra-desc{color:var(--dsw-alias-label-tertiary);font-size:13px;line-height:1.5}
.rra-chevron{color:var(--dsw-alias-label-tertiary);flex:none;transition:transform .16s}
.rra-card-open .rra-chevron{transform:rotate(180deg)}
.rra-body{border-top:1px solid var(--dsw-alias-border-l2);margin:0 16px;padding-bottom:8px}
.rra-badge{white-space:nowrap;background:var(--dsw-alias-bg-module-platform);color:var(--dsw-alias-label-secondary);border-radius:999px;padding:1px 8px;font-size:11px;font-weight:500;line-height:17px}
.rra-field{display:flex;flex-direction:column;gap:8px;padding:16px 0;border-bottom:1px solid var(--dsw-alias-border-l2)}
.rra-label-row{display:flex;align-items:center;gap:8px}
.rra-label{font-size:13px;font-weight:500;color:var(--dsw-alias-label-primary);flex:1}
.rra-field-hint,.rra-hint{margin:0;font-size:12px;line-height:1.5;color:var(--dsw-alias-label-tertiary);overflow-wrap:anywhere}
.rra-hint{margin-top:12px}
.rra-select,.rra-textarea,.rra-input{box-sizing:border-box;font:inherit;font-size:13px;color:var(--dsw-alias-label-primary);border:1px solid var(--dsw-alias-border-l2);border-radius:8px;background:var(--dsw-alias-bg-layer-3);padding:8px 10px}
.rra-select{height:34px;width:220px;max-width:100%}
.rra-input{height:34px;width:100%;min-width:0}
.rra-textarea{width:100%;min-height:76px;line-height:1.5;resize:vertical}
.rra-textarea::placeholder{color:var(--dsw-alias-label-tertiary)}
.rra-select:disabled,.rra-textarea:disabled,.rra-input:disabled{opacity:.4;cursor:default}
.rra-strategy{display:flex;flex-direction:column;gap:12px;margin-top:16px;padding:20px 16px;border:1px solid var(--dsw-alias-border-l2);border-radius:10px;background:var(--dsw-alias-bg-layer-3);min-width:0}
.rra-strategy-name{margin:0;padding-bottom:12px;border-bottom:1px solid var(--dsw-alias-border-l2);font-size:15px;font-weight:600;line-height:1.4;color:var(--dsw-alias-label-primary)}
.rra-models{display:flex;flex-direction:column;gap:8px;border:0;margin:0;padding:4px 0;min-width:0}
.rra-models legend{padding:0;margin-bottom:6px}
.rra-models .rra-reset{align-self:flex-start;padding:0}
.rra-json{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px;min-height:240px}
.rra-check{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--dsw-alias-label-primary)}
.rra-v4-section{display:flex;flex-direction:column;gap:14px;padding:18px 0;border-bottom:1px solid var(--dsw-alias-border-l2)}
.rra-v4-section h3{margin:0;font-size:15px;color:var(--dsw-alias-label-primary)}
.rra-section-head,.rra-row-title{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}
.rra-section-head>div{display:flex;flex-direction:column;gap:4px}
.rra-grid{display:grid;gap:12px}.rra-grid-2{grid-template-columns:repeat(2,minmax(0,1fr))}.rra-grid-3{grid-template-columns:repeat(3,minmax(0,1fr))}
.rra-compact-field{display:flex;flex-direction:column;gap:6px;min-width:0}.rra-compact-field .rra-select{width:100%}
.rra-preview-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}
.rra-preview-cell{display:flex;flex-direction:column;gap:4px;padding:10px;border-radius:8px;background:var(--dsw-alias-bg-module-platform);color:var(--dsw-alias-label-tertiary);font-size:12px}
.rra-preview-cell strong{color:var(--dsw-alias-label-primary);font-size:18px}
.rra-scenarios{display:grid;gap:8px}.rra-scenarios>div{display:flex;justify-content:space-between;gap:12px;padding:8px 10px;border:1px solid var(--dsw-alias-border-l2);border-radius:8px;font-size:12px;color:var(--dsw-alias-label-secondary)}
.rra-scenarios strong{color:var(--dsw-alias-label-primary)}
.rra-status{white-space:nowrap;border-radius:999px;padding:2px 8px;font-size:11px;background:var(--dsw-alias-bg-module-platform);color:var(--dsw-alias-label-secondary)}
.rra-status-bad{color:var(--dsw-alias-label-error)}.rra-status-warn{color:var(--dsw-alias-label-secondary)}
.rra-row-card{display:flex;flex-direction:column;gap:12px;padding:14px;border:1px solid var(--dsw-alias-border-l2);border-radius:10px;background:var(--dsw-alias-bg-layer-3)}
.rra-row-title strong{font-size:13px;color:var(--dsw-alias-label-primary)}
.rra-check-row,.rra-role-grid{display:flex;flex-wrap:wrap;gap:12px 18px;border:0;margin:0;padding:0}.rra-role-grid legend{margin-bottom:8px;padding:0}
.rra-empty{margin:0;padding:12px;border:1px dashed var(--dsw-alias-border-l2);border-radius:8px;text-align:center;font-size:12px;color:var(--dsw-alias-label-tertiary)}
.rra-simple-status{display:flex;flex-direction:column;gap:5px;padding:12px 14px;border-radius:10px;background:var(--dsw-alias-bg-module-platform);font-size:12px;color:var(--dsw-alias-label-secondary)}
.rra-simple-status strong{font-size:14px;color:var(--dsw-alias-label-primary)}
.rra-advanced-toggle{display:flex;justify-content:flex-start;padding:12px 0;border-bottom:1px solid var(--dsw-alias-border-l2)}
.rra-reset{font:inherit;font-size:12px;color:var(--dsw-alias-label-secondary);background:none;border:none;cursor:pointer}
.rra-invalid{margin:8px 0;font-size:12px;line-height:1.5;color:var(--dsw-alias-label-error)}
.rra-actions{display:flex;justify-content:flex-end;gap:8px;padding:12px 0 4px}
.rra-button{appearance:none;font:inherit;font-size:13px;line-height:1.5;cursor:pointer;border:1px solid transparent;border-radius:8px;padding:5px 14px;background:var(--dsw-alias-label-primary);color:var(--dsw-alias-bg-layer-3)}
.rra-button-secondary{border-color:var(--dsw-alias-border-l2);color:var(--dsw-alias-label-secondary);background:none}
.rra-button:disabled,.rra-reset:disabled{opacity:.4;cursor:default}
.rra-head:focus-visible,.rra-button:focus-visible,.rra-select:focus-visible,.rra-textarea:focus-visible,.rra-input:focus-visible{outline:2px solid var(--dsw-alias-brand-primary);outline-offset:1px}
@media(max-width:760px){.rra-grid-2,.rra-grid-3{grid-template-columns:1fr}.rra-preview-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.rra-scenarios>div{flex-direction:column;gap:4px}}
`

if (typeof document !== 'undefined' && document.querySelector('style[data-plugin-css="refractagent-settings-card"]') === null) {
  const tag = document.createElement('style')
  tag.dataset.pluginCss = 'refractagent-settings-card'
  tag.textContent = css
  document.head.appendChild(tag)
}

export function RefractCard(props: RefractCardOwnerProps) {
  const { t } = props
  const state = props.useRefractCard(snapshot => snapshot)
  const [expanded, setExpanded] = useState(false)
  const [v4Advanced, setV4Advanced] = useState(false)
  const [catalog,setCatalog]=useState<DshModelCatalog|undefined>()
  const [catalogError,setCatalogError]=useState<string|undefined>()
  const [routerProjects,setRouterProjects]=useState<RouterProjectDirectory|undefined>()
  const [routerError,setRouterError]=useState<string|undefined>()
  useEffect(()=>{let active=true;void props.loadCatalog().then(value=>{if(active){setCatalog(value);setCatalogError(undefined)}})
    .catch(error=>{if(active)setCatalogError(error instanceof Error?error.message:String(error))});return()=>{active=false}},[])
  useEffect(()=>{let active=true
    const router=state.router
    if(!router){setRouterProjects(undefined);setRouterError(undefined);return()=>{active=false}}
    setRouterProjects(undefined);setRouterError(undefined)
    void props.loadRouterProjects({url:router.url,credential:router.credential}).then(value=>{
      if(!active)return
      setRouterProjects(value)
      if(value.protocol==='refractagent-http-v2'&&!router.project&&value.projects.length===1){
        props.editRouter({...router,project:value.projects[0]!.id})
      }
    }).catch(error=>{if(active)setRouterError(error instanceof Error?error.message:String(error))})
    return()=>{active=false}
  },[state.router?.url,state.router?.credential])

  const pool=state.dshModelPool
  const beginPool=()=>props.editDshModelPool({schemaVersion:'refractagent-dsh-model-pool-v1',billingUnit:state.provider?.billingUnit??'USD',routes:[],
    ...(state.provider?.objective?{objective:state.provider.objective}:{}),
    ...(state.provider?.security?{security:state.provider.security}:{}),
    ...(state.provider?.trustPolicies?{trustPolicies:state.provider.trustPolicies.filter((row):row is Record<string,unknown>=>row!==null&&typeof row==='object'&&!Array.isArray(row))}:{})})
  const updatePool=(next:DshModelPoolView)=>props.editDshModelPool(next)
  const catalogRows=(catalog?.groups??[]).filter(group=>group.id!=='refractagent')
    .flatMap(group=>group.models.map(model=>({provider:group.id,providerName:group.name,model:model.id,name:model.name})))
  const identity=(provider:string,model:string)=>provider+'/'+model
  const updateRoute=(provider:string,model:string,enabled:boolean)=>{
    if(!pool)return
    const routes=pool.routes.filter(row=>!(row.provider===provider&&row.model===model))
    if(enabled)routes.push({provider,model,enabled:true,deployment:''})
    updatePool({...pool,routes})
  }
  const patchRoute=(provider:string,model:string,patch:Record<string,unknown>)=>{
    if(!pool)return
    updatePool({...pool,routes:pool.routes.map(row=>row.provider===provider&&row.model===model?{...row,...patch}:row)})
  }
  const routeOptions=pool?.routes.filter(row=>row.enabled!==false)??[]
  const trustPolicyOptions=(pool?.trustPolicies??[]).filter(row=>typeof row.id==='string')
  const patchRole=(role:'planner'|'judge'|'classifier',value:string)=>{
    if(!pool)return
    updatePool({...pool,roleOverrides:{...pool.roleOverrides,[role]:value||undefined}})
  }
  const patchWorkers=(route:string,checked:boolean)=>{
    if(!pool)return
    const current=pool.roleOverrides?.workers??[]
    const workers=checked?[...new Set([...current,route])]:current.filter(value=>value!==route)
    updatePool({...pool,roleOverrides:{...pool.roleOverrides,workers:workers.length?workers:undefined}})
  }

  if (state.status === 'unavailable') {
    return (
      <li className="rra-card">
        <div className="rra-head">
          <span className="rra-name">{t('title')}</span>
        </div>
        <p className="rra-hint">{t('unavailable')}</p>
      </li>
    )
  }

  const disabled = state.status !== 'ready' || !state.writable || state.saving
  const provider = state.provider
  const choices = candidateChoices(provider)
  const effortSelect = (label: string, value: string | undefined, onEdit: (value: string) => void) => {
    const options = [...EFFORTS, ...(value !== undefined && !EFFORTS.includes(value) ? [value] : [])]
    return (
      <select className="rra-select" aria-label={label} value={value ?? ''} disabled={disabled}
        onChange={event => onEdit(event.target.value)}>
        <option value="">{t('effortDefault')}</option>
        {options.map(option => <option key={option} value={option}>{t('effort_' + option) === 'effort_' + option ? option : t('effort_' + option)}</option>)}
      </select>
    )
  }

  return (
    <li className={'rra-card' + (expanded ? ' rra-card-open' : '')}>
      <button type="button" className="rra-head" aria-expanded={expanded}
        aria-label={(expanded ? t('collapse') : t('expand')) + ': ' + t('title')}
        onClick={() => setExpanded(value => !value)}>
        <span className="rra-head-text">
          <span className="rra-name">{t('title')}</span>
          <span className="rra-desc">{t(state.automaticRouting ? 'v4Description' : 'description')}</span>
        </span>
        {state.dirty ? <span className="rra-badge">{t('unsaved')}</span> : null}
        <svg className="rra-chevron" width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
          <path d="M3 5.5L7 9.5L11 5.5" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      </button>
      {expanded ? (
        <div className="rra-body">
          <div className="rra-v4-section"><div className="rra-section-head"><div><h3>RefractRouter 连接</h3>
            <p className="rra-field-hint">本地模式由插件启动已安装的 Python 核心；远程模式把任务发送到指定 Router 服务。</p></div>
            {state.overriddenRouter?<button type="button" className="rra-reset" disabled={disabled} onClick={()=>props.resetField('router')}>恢复默认</button>:null}</div>
            <label className="rra-compact-field">连接方式<select className="rra-select" disabled={disabled}
              value={state.router?'remote':'local'} onChange={event=>props.editRouter(event.target.value==='remote'?{url:'http://127.0.0.1:8787'}:undefined)}>
              <option value="local">本地 Python 核心</option><option value="remote">远程 Router URL</option></select></label>
            {state.router?<div className="rra-grid rra-grid-2"><label className="rra-compact-field">Router URL
              <input className="rra-input" type="url" disabled={disabled} value={state.router.url}
                onChange={event=>props.editRouter({...state.router!,url:event.target.value,project:undefined})}/>
              <span className="rra-field-hint">例如 http://127.0.0.1:8787；非本机地址必须使用 HTTPS。</span></label>
              <label className="rra-compact-field">凭证引用（可选）<input className="rra-input" disabled={disabled}
                value={state.router.credential??''} placeholder="REFRACTROUTER_SERVICE_TOKEN"
                onChange={event=>props.editRouter({...state.router!,credential:event.target.value||undefined,project:undefined})}/>
              <span className="rra-field-hint">只保存 DSH 凭证名称，不保存 token。</span></label></div>:null}
            {state.router?<>{routerError?<p className="rra-invalid">连接检查失败：{routerError}</p>:null}
              {!routerError&&!routerProjects?<p className="rra-field-hint">正在检查 Router 协议和项目权限…</p>:null}
              {routerProjects?.protocol==='refractagent-http-v1'?<div className="rra-simple-status"><strong>HTTP v1 同步兼容</strong><span>服务未开放持久任务协议；提交前将继续使用 v1。</span></div>:null}
              {routerProjects?.protocol==='refractagent-http-v2'?<label className="rra-compact-field">团队项目
                <select className="rra-select" disabled={disabled} value={state.router.project??''}
                  onChange={event=>props.editRouter({...state.router!,project:event.target.value||undefined})}>
                  <option value="">请选择项目</option>{routerProjects.projects.map(project=><option key={project.id} value={project.id}>{project.name}</option>)}</select>
                <span className="rra-field-hint">项目来自 Router 当前成员权限，不支持自由填写。</span></label>:null}
              {routerProjects?.protocol==='refractagent-http-v2'&&state.router.project
                &&!routerProjects.projects.some(project=>project.id===state.router?.project)?<p className="rra-invalid">已保存项目当前不可用，请重新选择。</p>:null}</>:null}
          </div>
          {!state.hasProvider ? <p className="rra-hint">{t('providerAbsentHint')}</p> : null}
          {pool ? <div className="rra-v4-section"><div className="rra-section-head"><div><h3>DSH 模型目录</h3>
            <p className="rra-field-hint">只显示“设置 → 模型”中当前可调用的路线；RefractAgent 自身已排除。</p></div>
            {state.overriddenDshPool?<button type="button" className="rra-reset" onClick={()=>props.resetField('dshModelPool')}>恢复旧配置</button>:null}</div>
            {catalogError?<p className="rra-invalid">{catalogError}</p>:null}
            {catalog?.failures.map(row=><p className="rra-invalid" key={row.id}>{row.name}: {row.message}</p>)}
            {catalogRows.map(row=>{const selected=pool.routes.find(route=>route.provider===row.provider&&route.model===row.model)
              return <div className="rra-row-card" key={identity(row.provider,row.model)}><label className="rra-check">
                <input type="checkbox" checked={!!selected} disabled={disabled} onChange={event=>updateRoute(row.provider,row.model,event.target.checked)}/>
                <strong>{row.providerName} / {row.name}</strong></label>{selected?<><label className="rra-compact-field">部署属性
                <select className="rra-select" value={selected.deployment} onChange={event=>{const deployment=event.target.value;patchRoute(row.provider,row.model,{deployment,...(['trusted-cloud','simulated-local'].includes(deployment)?{}:{trustPolicy:undefined})})}}>
                  <option value="">请选择部署属性</option>{['local','external-cloud','trusted-cloud','simulated-local'].map(value=><option key={value}>{value}</option>)}</select></label>
                {selected.deployment==='trusted-cloud'||selected.deployment==='simulated-local'?<label className="rra-compact-field">信任策略<select className="rra-select" value={selected.trustPolicy??''} onChange={event=>patchRoute(row.provider,row.model,{trustPolicy:event.target.value||undefined})}><option value="">请选择信任策略</option>{trustPolicyOptions.map(policy=><option key={String(policy.id)} value={String(policy.id)}>{String(policy.id)}</option>)}</select></label>:null}
                {v4Advanced?<><div className="rra-grid rra-grid-3">{[['inputPer1k','输入价 / 1k'],['cachedInputPer1k','缓存输入价 / 1k'],['outputPer1k','输出价 / 1k'],['quality','质量预测'],['latencyMs','时延预测（ms）']].map(([key,label])=><label className="rra-compact-field" key={key}>{label}<input className="rra-input" type="number" value={String(selected.overrides?.[key]??'')} onChange={event=>patchRoute(row.provider,row.model,{overrides:{...selected.overrides,[key]:event.target.value===''?undefined:Number(event.target.value)}})}/></label>)}</div>
                <label className="rra-compact-field">说明<input className="rra-input" value={String(selected.overrides?.note??'')} onChange={event=>patchRoute(row.provider,row.model,{overrides:{...selected.overrides,note:event.target.value||undefined}})}/></label>
                <button type="button" className="rra-reset" onClick={()=>patchRoute(row.provider,row.model,{overrides:{}})}>恢复公开档案</button></>:null}</>:null}</div>})}
            {!catalog?<p className="rra-field-hint">正在读取 DSH 模型目录…</p>:null}
            <div className="rra-advanced-toggle"><button type="button" className="rra-reset" onClick={()=>setV4Advanced(value=>!value)}>{v4Advanced?'收起高级设置':'展开高级设置'}</button></div>
            {v4Advanced?<><div className="rra-grid rra-grid-3">{([['planner','规划模型'],['judge','评审模型'],['classifier','分类模型']] as const).map(([role,label])=><label className="rra-compact-field" key={role}>{label}<select className="rra-select" value={pool.roleOverrides?.[role]??''} onChange={event=>patchRole(role,event.target.value)}><option value="">自动分配</option>{routeOptions.map(row=><option key={identity(row.provider,row.model)} value={identity(row.provider,row.model)}>{identity(row.provider,row.model)}</option>)}</select></label>)}</div>
            <fieldset className="rra-models"><legend className="rra-label">执行模型池</legend><p className="rra-field-hint">不勾选时由 Python 核心自动分配；勾选后仅使用指定路线。</p>{routeOptions.map(row=>{const key=identity(row.provider,row.model);return <label className="rra-check" key={key}><input type="checkbox" checked={pool.roleOverrides?.workers?.includes(key)??false} onChange={event=>patchWorkers(key,event.target.checked)}/>{key}</label>})}</fieldset></>:null}
          </div> : state.automaticRouting && provider ? <><div className="rra-v4-section"><h3>迁移到 DSH 模型目录</h3><p className="rra-field-hint">旧 providerConfig 会保留供 CLI 和历史运行使用；预览确认后再保存新模型池，不会静默覆盖。</p><button type="button" className="rra-button" onClick={beginPool}>查看迁移预览</button></div><V4Settings t={t} provider={provider} disabled={true}
            advanced={v4Advanced}
            editV4QualityMin={props.editV4QualityMin} editV4DagMode={props.editV4DagMode}
            editV4DataMode={props.editV4DataMode} editV4SensitiveTerms={props.editV4SensitiveTerms}
            editV4Classifier={props.editV4Classifier} upsertV4Row={props.upsertV4Row}
            removeV4Row={props.removeV4Row} />
            <div className="rra-advanced-toggle"><button type="button" className="rra-reset"
              onClick={() => setV4Advanced(value => !value)}>
              {t(v4Advanced ? 'v4HideAdvanced' : 'v4ShowAdvanced')}
            </button></div></> : <>
          <div className="rra-field">
            <div className="rra-label-row">
              <span className="rra-label">{t('defaultEffort')}</span>
              {state.overriddenProvider
                ? <button type="button" className="rra-reset" disabled={disabled}
                    onClick={() => props.resetField('providerConfig')}>{t('reset')}</button> : null}
            </div>
            <p className="rra-field-hint">{t('defaultEffortHint')}</p>
            {effortSelect(t('defaultEffort'), provider?.defaultReasoningEffort, value => props.editDefaultEffort(value))}
          </div>
          <div className="rra-field">
            <span className="rra-label">{t('plannerThinking')}</span>
            <p className="rra-field-hint">{t('plannerThinkingHint')}</p>
            <select className="rra-select" aria-label={t('plannerThinking')} disabled={disabled}
              value={provider?.plannerThinking ?? 'inherit'} onChange={event => props.editPlannerThinking(event.target.value)}>
              {['inherit','enabled','disabled'].map(value => <option key={value} value={value}>{t('plannerThinking_' + value)}</option>)}
            </select>
            <p className="rra-field-hint">{t('plannerCapacityHint')}</p>
          </div>
          <div className="rra-field">
            <span className="rra-label">{t('strategies')}</span>
            <p className="rra-field-hint">{t('separateControlsHint')}</p>
            {provider?.billingUnit === 'AFP' ? <p className="rra-field-hint">{t('afpSourceHint')} {afpMetadata.snapshotDate} · <a href={afpMetadata.sourceUrl} target="_blank" rel="noreferrer">{t('afpSource')}</a></p> : null}
            {MODE_KEYS.map(mode => {
              const selected = provider?.strategies?.[mode]?.models ?? []
              const missing = selected.filter(id => !choices.some(choice => choice.id === id))
              const update = (id: string, checked: boolean) => props.editStrategyModels(mode,
                (checked ? [...new Set([...selected, id])] : selected.filter(value => value !== id)).join('\n'))
              return (
                <section key={mode} className="rra-strategy" aria-label={t(STRATEGY_LABEL_KEYS[mode])}>
                  <h3 className="rra-strategy-name">{t(STRATEGY_LABEL_KEYS[mode])}</h3>
                  <p className="rra-field-hint">{t(STRATEGY_LABEL_KEYS[mode] + 'Hint')}</p>
                  {provider?.billingUnit === 'AFP' ? <label className="rra-label">
                    {t('afpCeiling')}
                    <select className="rra-select" style={{display:'block',marginTop:6}} disabled={disabled}
                      aria-label={t(STRATEGY_LABEL_KEYS[mode]) + ' · ' + t('afpCeiling')}
                      value={provider.strategies?.[mode]?.maxAfpCoefficient ?? ''}
                      onChange={event => props.editStrategyAfpCeiling(mode, event.target.value)}>
                      <option value="">{t('noCostCeiling')}</option>
                      {afpMetadata.tiers.map(value => <option key={value} value={value}>{t('afpAtMost')} {value}</option>)}
                    </select>
                  </label> : null}
                  <span className="rra-label">{t('modeEffort')}</span>
                  {effortSelect(t(STRATEGY_LABEL_KEYS[mode]) + ' · ' + t('defaultEffort'), provider?.strategies?.[mode]?.reasoningEffort,
                    value => props.editStrategyEffort(mode, value))}
                  <fieldset className="rra-models" disabled={disabled}>
                    <legend className="rra-label">{t('modelsLabel')}</legend>
                    <p className="rra-field-hint">{t('modelsHint')}</p>
                    {choices.map(choice => (
                      <label key={choice.id} className="rra-check">
                        <input type="checkbox" checked={selected.includes(choice.id)}
                          aria-label={t(STRATEGY_LABEL_KEYS[mode]) + ' · ' + choice.label}
                          onChange={event => update(choice.id, event.target.checked)} />
                        <span>{choice.label}{choice.costLabel ? <small style={{display:'block'}} className="rra-field-hint">{choice.costLabel} · {choice.planLabel}</small> : null}{choice.thinkingAuto ? <small className="rra-field-hint" style={{display:'block'}}>{t('thinkingAuto_' + choice.thinkingAuto)}</small> : null}</span>
                      </label>
                    ))}
                    {missing.map(id => (
                      <label key={id} className="rra-check">
                        <input type="checkbox" checked aria-label={t(STRATEGY_LABEL_KEYS[mode]) + ' · ' + t('missingModel') + ': ' + id}
                          onChange={() => update(id, false)} />
                        <span>{t('missingModel')}: {id}</span>
                      </label>
                    ))}
                    {choices.length === 0 ? <p className="rra-field-hint">{t('noModels')}</p> : null}
                    <p className="rra-field-hint">{selected.length ? t('selectedModels') + selected.length : t('allModels')}</p>
                    {selected.length ? <button type="button" className="rra-reset"
                      onClick={() => props.editStrategyModels(mode, '')}>{t('useAllModels')}</button> : null}
                  </fieldset>
                </section>
              )
            })}
          </div>
          </>}
          {(!state.automaticRouting || v4Advanced) ? <div className="rra-field">
            <div className="rra-label-row">
              <span className="rra-label">{t('limitsTitle')}</span>
              {state.overriddenLimits
                ? <button type="button" className="rra-reset" disabled={disabled}
                    onClick={() => props.resetField('limits')}>{t('reset')}</button> : null}
            </div>
            <label className="rra-check">
              <input type="checkbox" disabled={disabled} checked={state.limits.relaxBudget === true}
                onChange={event => props.editLimit('relaxBudget', event.target.checked)} />
              <span>{t('relaxBudget')}</span>
            </label>
            <p className="rra-field-hint">{t('relaxBudgetHint')}</p>
            <label className="rra-check">
              <input type="checkbox" disabled={disabled} checked={state.limits.relaxContext === true}
                onChange={event => props.editLimit('relaxContext', event.target.checked)} />
              <span>{t('relaxContext')}</span>
            </label>
            <p className="rra-field-hint">{t('relaxContextHint')}</p>
            <label className="rra-check">
              <input type="checkbox" disabled={disabled} checked={state.limits.unlimitedTime === true}
                onChange={event => props.editLimit('unlimitedTime', event.target.checked)} />
              <span>{t('unlimitedTime')}</span>
            </label>
            <p className="rra-field-hint">{t('unlimitedTimeHint')}</p>
          </div> : null}
          {!pool&&(!state.automaticRouting || v4Advanced) ? <div className="rra-field">
            <div className="rra-label-row">
              <span className="rra-label">{t('providerJsonTitle')}</span>
              <button type="button" className="rra-reset" disabled={disabled}
                onClick={() => props.editProviderJson(JSON.stringify(
                  state.automaticRouting ? v4Example : examples['openai-compatible'], null, 2))}>{t('insertExample')}</button>
            </div>
            <p className="rra-field-hint">{t('providerJsonHint')}</p>
            <textarea className="rra-textarea rra-json" rows={12} disabled={disabled} spellCheck={false}
              aria-label={t('providerJsonTitle')} placeholder={JSON.stringify(
                state.automaticRouting ? v4Example : examples['openai-compatible'], null, 2)}
              value={state.providerJson}
              onChange={event => props.editProviderJson(event.target.value)} />
            {state.providerJsonError !== null
              ? <p className="rra-invalid">{t('invalidJson') + ': ' + state.providerJsonError}</p> : null}
          </div> : null}
          <div className="rra-actions">
            <button type="button" className="rra-button" disabled={disabled || !state.dirty || state.providerJsonError !== null}
              onClick={() => props.save()}>{state.saving ? t('saving') : t('save')}</button>
            <button type="button" className="rra-button rra-button-secondary" disabled={disabled || !state.dirty}
              onClick={() => props.discard()}>{t('discard')}</button>
          </div>
          {state.failed ? <p className="rra-invalid">{t('saveFailed')}</p> : null}
        </div>
      ) : null}
    </li>
  )
}
