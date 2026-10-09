import {useEffect,useState} from 'react'
import type {ReactNode} from 'react'

// 展示 Python 的只读投影；这里不重新判断能力、预算或路由。
type Row=Record<string,any>
export interface AutomaticHistory {schema_version:string;records:Row[];errors:Array<{run_id:string;message:string}>}
export function parseAutomaticHistory(value:unknown):AutomaticHistory{
  const v=value as AutomaticHistory|undefined
  if(!v||v.schema_version!=='automatic-routing-trace-v1'||!Array.isArray(v.records)||!Array.isArray(v.errors))
    throw new Error('核心与插件的轨迹合同不匹配，请重新加载 DSH 服务；不会重发原任务')
  return v
}
interface Node {kind:string;turn?:number;interrupted?:boolean;message?:string;provenance?:{provider:string};blocks?:readonly {kind:string;text?:string}[]}
export interface TraceSnapshot {legacy:{nodes:readonly Node[];partial:{turn?:number;blocks:readonly {kind:string;text?:string}[]}|null}}
export interface ChatTraceProps {useChat?<T>(select:(snapshot:TraceSnapshot)=>T):T}
export interface AutomaticRef {id:string;turn?:number;state:'settled'|'running'|'interrupted';error?:string}
const ID='\\d{8}T\\d{6}Z-[0-9a-f]{12}'
export function automaticRefs(snapshot:TraceSnapshot):AutomaticRef[]{
  const refs=new Map<string,AutomaticRef>()
  const add=(node:Node,state:AutomaticRef['state'])=>{
    if(node.provenance&&node.provenance.provider!=='refractagent')return
    const text=node.blocks?.filter(b=>b.kind==='reasoning').map(b=>b.text??'').join('\n')??''
    if(!/^(正在预检并执行真实自动路由。|正在预览自动拆分流程。)/.test(text))return
    const matches=[...text.matchAll(new RegExp(`【自动路由记录】(${ID})|记录：[^\\n]*[\\/\\\\](${ID})[\\/\\\\](?:result|summary)\\.json`,'g'))]
    for(const match of matches){const id=match[1]??match[2];if(id)refs.set(id,{id,turn:node.turn,state})}
  }
  for(const node of snapshot.legacy.nodes)if(node.kind==='assistant')add(node,node.interrupted?'interrupted':'settled')
  if(snapshot.legacy.partial)add({kind:'assistant',...snapshot.legacy.partial},'running')
  for(const node of snapshot.legacy.nodes)if(node.kind==='turn-error')for(const ref of refs.values())if(ref.turn===node.turn){ref.state='interrupted';ref.error=node.message}
  return [...refs.values()].slice(-20).reverse()
}
const NAMES:Record<string,string>={
  direct:'整任务直接执行',dag:'DAG 拆分执行',completed:'已完成',preview:'零调用预览',running:'运行中',
  started:'已开始（尚未结束）',pending:'等待执行',skipped:'按策略跳过',
  'blocked-deterministic-check':'固定事实检查未通过，未派发评审',
  'not-dispatched-insufficient-time':'剩余时间不足，未派发',
  'known-answer-contract-failed':'已知事实不符合验收合同',
  'review-time-exhausted':'剩余时间不足，最终答复未审定',
  'final-judge-insufficient-time':'未满足评审时间预留，未派发评审',
  'planning-would-consume-review-reserve':'任务时间不足以保留评审，未派发规划',
  'execution-would-consume-review-reserve':'剩余时间不足以保留评审，未派发执行',
  'quality-failed':'质量未通过','no-feasible-route':'没有可执行路线','tool-requirement-failed':'工具证据未通过',
  'data-domain-not-authorized':'数据域未获授权','quality-below-minimum':'质量先验低于门槛',
  'input-or-output-capacity':'输入或输出容量不足','missing-profile':'缺少匹配画像',eligible:'通过画像、容量及数据域检查',
  'not-recorded':'该次运行未记录',dominated:'被同提供方、同预测时延的更优候选覆盖',selected:'选中',
  'not-selected':'未选中',billed:'用量已结算',reserved:'尚未派发，保留预留','unknown-usage':'已派发，用量待核对',
  released:'未派发预留已释放',production:'生产',evaluation:'评审',
  'cancelled-before-dispatch':'未派发预留已释放','privacy-route-blocked':'数据域准入阻断',
  'output-constraint-failed':'输出约束未通过',failed:'执行失败',
  'quality-qualified-then-cash-then-reference':'先满足质量与准入，优先减少新增现金，再比较参考成本',
  'direct-estimated-cost-not-worse':'直接执行的预计成本不高于拆分路线',
  'generated-single-node':'规划器只生成一个节点，未形成多节点拆分',
  'coupled-sequential-work':'工作存在顺序依赖，保留直接执行',
  'local-separable':'工作可独立开始，进入规划后再比较两条路线',
  'uncertain-direct-with-review':'拆分证据不足，直接执行并保留评审',
  'single-work-no-planner':'单项工作直接执行', 'trivial-workload-no-planner':'微型任务直接执行',
  'rules-only':'按结构规则处理', 'local-unknown-rules-preserved':'Judge 无法确定，保留规则结论',
  'known-calls-only-unbounded-tool-continuations':'只估计已知调用，后续工具续调费用没有完整上界',
  'declared-model-profile-prior':'模型画像先验',
  'worker-schedule-plus-observed-planner; shared-judge-latency-unforecast':'执行调度预测加已发生的规划耗时；未预测共用评审耗时',
}
const label=(v:unknown)=>typeof v==='string'?NAMES[v]??v:'未记录'
export const traceNumber=(v:unknown)=>typeof v==='number'&&Number.isFinite(v)
  ?new Intl.NumberFormat('zh-CN',{maximumFractionDigits:10}).format(v):'未记录'
const money=(v:unknown)=>`${traceNumber(v)} CNY`
const route=(v:Row|undefined)=>v?.provider&&v.model?`${v.provider} / ${v.model}`:'来源未记录'
const timing=(v:unknown)=>typeof v==='number'?`${traceNumber(v)} ms`:'未记录'
const cellStyle={textAlign:'left' as const,padding:'10px 12px',borderBottom:'1px solid var(--border-color, #8884)',verticalAlign:'top' as const}
function Table({heads,children}:{heads:string[];children:ReactNode}){return <div style={{overflowX:'auto'}}><table style={{width:'100%',borderCollapse:'collapse',fontSize:13}}><thead><tr>{heads.map(h=><th key={h} style={cellStyle}>{h}</th>)}</tr></thead><tbody>{children}</tbody></table></div>}
export function AutomaticRecord({record:r,reference}:{record:Row;reference:AutomaticRef}){
  const gate=r.structure??{},judge=gate.judge??{},comparison=r.comparison??{}
  return <article style={{border:'1px solid var(--border-color, #8884)',borderRadius:12,padding:18,marginBottom:18}}>
    <h3>自动路由 · {reference.state==='interrupted'?'宿主已中断':label(r.status)}{r.simulated?'（模拟）':''}</h3>
    <small>记录 {r.run_id}；宿主轮次 {reference.turn??'未记录'}；端到端 {timing(r.wall_time_ms)}</small>
    {reference.state==='running'&&<p role="status">宿主任务运行中；以下为最近持久化的证据，尚未完成的步骤不代表通过。</p>}
    {reference.state==='interrupted'&&<p role="status">{reference.error??'宿主已停止；核心状态以最后保存的证据为准。'} 不自动重发待核对调用。</p>}
    <h4>任务判别与最终执行路线</h4>
    <p>结构规则：{label(gate.rule_decision)} → Judge 合并后：{label(gate.decision)}。{label(gate.combination)}。</p>
    <p>最终执行：{comparison.route?label(comparison.route):label(gate.decision)}；{comparison.reason?label(comparison.reason):`计划来源 ${r.plan_origin??'未记录'}`}。
      {comparison.generated_node_count!==undefined?`候选计划 ${comparison.generated_node_count} 个节点；选中 ${comparison.selected_node_count??'未记录'} 个节点。`:''}</p>
    {judge.model?<><p>Judge：{route(judge)}；原始分类 {judge.rawVerdict??'未记录'}；规则合并分类 {judge.verdict??'未记录'}；耗时 {timing(judge.latencyMs)}；排队 {timing(judge.queueMs)}。{judge.experimental?'此判别路线标为实验。':''}</p>
      {judge.rawAnswers&&<details><summary>Judge 原始答案</summary>
        <Table heads={['问题','类型','原始答案']}>
          {Object.entries(judge.rawAnswers).map(([id,value])=>{const v=value as Row;return <tr key={id}>
            <td style={cellStyle}>{({requires_previous_output:'是否依赖前一步输出',can_start_independently:'是否可独立开始',single_work_unit:'是否只有一项实质工作'} as Record<string,string>)[id]??id}</td>
            <td style={cellStyle}>{v.type??'未记录'}</td><td style={cellStyle}>{v.type==='noul'?traceNumber(v.noul):JSON.stringify(v)}</td></tr>})}
        </Table><p>Noul 是问题成立的概率。{judge.probabilityBasis==='derived-not-model'?'分类概率由规则合成，不是模型直接给出的 Choice probability 或 confidence。':''}不表示任务成功率。</p></details>}
      <small>合同 {judge.contract??'未记录'}；规则 {judge.ruleVersion??gate.policy_version??'未记录'}；版本 {judge.revision??'未记录'}</small></>:<p>本次未记录 Judge 调用；不能据此认定进行了模型判别。</p>}
    {comparison.direct||comparison.dag?<details><summary>路线预测与适用范围</summary>
      <p>直接路线预测：{traceNumber(comparison.direct?.total_estimated_cost)} {comparison.billing_unit??'单位未记录'}；DAG 候选预测：{traceNumber(comparison.dag?.total_estimated_cost)} {comparison.billing_unit??'单位未记录'}。</p>
      <p>预测范围：{label(comparison.estimate_scope)}；完整任务费用上界：{comparison.complete_task_cost_bound===false||comparison.complete_task_cost_bound===null?'没有完整上界':comparison.complete_task_cost_bound===true?'已记录':traceNumber(comparison.complete_task_cost_bound)}；工具调用上限：{comparison.tool_call_limit==='unlimited'?'不限制':comparison.tool_call_limit??'未记录'}。</p>
      <p>未选择的候选路线没有被执行；预测差额不能当作实测收益。质量依据：{label(comparison.decision_factors?.quality_basis)}；本任务拆分质量增益{comparison.decision_factors?.task_specific_dag_quality_gain_verified===true?'已有验证证据':'尚未验证'}。</p>
      <p>时延依据：{label(comparison.latency_scope)}；模型配置的时延先验不等于实测等待时间。</p>
    </details>:null}
    <h4>候选模型与选择依据</h4><p>{label(r.selection_rule)}。该次质量门槛 {traceNumber(r.quality_min)}；质量画像与本次最终评审分别展示。</p>
    {r.candidates?.length?<Table heads={['模型／参数','数据域与计费','准入证据','分配及预算检查']}>
      {r.candidates.map((c:Row)=><tr key={c.id}><td style={cellStyle}>{route(c)}<br/><small>推理等级：{c.reasoning_effort??'提供方默认'}</small></td>
        <td style={cellStyle}>{c.deployment==='trusted-cloud'?'可信云':c.deployment??'未记录'}<br/>{c.billing_mode==='subscription'?'订阅（参考估值）':'按量'} · {c.billing_unit??'未记录'}</td>
        <td style={cellStyle}><p>{[...new Set<string>(c.admission.map((a:Row)=>a.reason))].map(label).join('；')||'未记录'}</p>
          <details><summary>逐节点证据（{c.admission.length} 项）</summary>{c.admission.map((a:Row)=><p key={`${a.path}-${a.node}`}>{a.path} / {a.node}：{label(a.reason)}</p>)}</details></td>
        <td style={cellStyle}>{c.selected_nodes.length?`实际分配：${c.selected_nodes.join('、')}`:'未分配'}
          {Object.entries(c.assignment_checks??{}).map(([nid,value])=>{const v=value as Row;return <p key={nid}>{nid}：{label(v.status)}；可行分配 {v.feasible_assignments} 个；质量先验 {traceNumber(v.quality_prior)}；参考预测 {traceNumber(v.reference_forecast)}；现金预测 {traceNumber(v.cash_forecast)}。
            {Object.entries(v.rejected_assignments??{}).map(([k,n])=>` ${k==='cash'?'现金预算':k==='cost'?'参考成本预算':k==='latency'?'期限':k==='quality'?'质量':k}排除 ${n} 个组合；`).join('')}</p>})}
          {!Object.keys(c.assignment_checks??{}).length&&<p>旧记录未保存逐模型预算检查；“通过准入”不等于“预算可执行”。</p>}</td></tr>)}
    </Table>:<p>旧记录没有冻结候选目录，无法用当前设置补写。</p>}
    {r.routing_diagnostics?.remaining_cash!==undefined&&<p>选模时可用现金额度：{r.routing_diagnostics.remaining_cash===null?'不限制':money(r.routing_diagnostics.remaining_cash)}；这是当时的额度。</p>}
    <h4>费用与预算</h4>
    {r.accounting_basis==='public-reference-valuation'?<><p>参考成本包含按量模型，不与现金占用相加。订阅模型按公开价格估值，不代表订阅实际扣费。按量金额按用量和价格计算，未经提供方账单确认。</p>
      <Table heads={['用途','参考成本占用','现金用量结算／待核对','当时现金预算／剩余']}>
        {r.ledger.map((v:Row)=><tr key={v.category}><td style={cellStyle}>{label(v.category)}</td><td style={cellStyle}>{money(v.reference_occupied_cny)}</td>
          <td style={cellStyle}>已结算 {money(v.billed_cash_cny)}<br/>待核对／预留 {money(v.pending_cash_cny)}（{v.pending_count} 个调用含订阅预留）</td>
          <td style={cellStyle}>{v.unlimited_cash?'不限制':money(v.cash_limit_cny)} / {v.unlimited_cash?'不限制':money(v.remaining_cash_cny)}</td></tr>)}
      </Table></>:<p>历史记录采用原计费合同，以下调用按原单位列示，不自动换算或重算。</p>}
    {r.external_judge_called&&<p>独立 Jev 判别：{r.external_judge_cost_cny===null?'费用待核对':money(r.external_judge_cost_cny)}；单独记账，未计入上述主任务现金余额。</p>}
    <details><summary>实际调用顺序与用量（{r.calls?.length??0} 次）</summary>
      <p>按账本预留顺序列示；并发派发时不等同于完成顺序。未派发的记录不是实际模型调用。</p>
      <Table heads={['顺序／用途／模型','状态与金额','输入／缓存／输出 tokens','首字／调用总耗时']}>
        {r.calls.map((c:Row,i:number)=><tr key={`${c.label}-${i}`}><td style={cellStyle}>{i+1}. {c.label} · {label(c.category)}<br/>{route(c.route)}<br/><small>推理等级：{c.route?.reasoning_effort??'提供方默认'}</small></td>
          <td style={cellStyle}>{label(c.status)}<br/>{c.billing_mode==='subscription'?'订阅参考估值':'按量计算／原合同'} {traceNumber(c.charged)} {c.billing_unit??c.unit??'单位未记录'}<br/><small>派发前预留 {traceNumber(c.reserved)}；状态待核对的金额不是已确认消费。</small></td>
          <td style={cellStyle}>{traceNumber(c.input_tokens)} / {traceNumber(c.cached_input_tokens)} / {traceNumber(c.output_tokens)}</td>
          <td style={cellStyle}>{timing(c.ttft_ms)} / {timing(c.latency_ms)}</td></tr>)}
      </Table><p>首字时间为底层模型数据；自动路由交付还包含工具、规划及评审等待，不能等同于用户首字等待。</p>
    </details>
    <h4>工具证据、评审与停止原因</h4>
    {r.planning_budget?.version&&<p>规划开始时告知的执行时间包络：{r.planning_budget.execution_after_planner_ms===null?'任务不限时间':timing(r.planning_budget.execution_after_planner_ms)}（已扣评审预留与规划额度）。{r.planning_budget.max_nodes!==undefined&&<>本次最多 {r.planning_budget.max_nodes} 个节点（含最终交付）。</>}时延先验不是速度保证；计划仍须通过准入。</p>}
    {r.review?.limits_version&&<p>评审预留时间 {timing(r.review.time_reserve_ms)}；评审输出上限 {traceNumber(r.review.output_cap)} tokens。此限制独立于执行模型输出容量。</p>}
    {r.review?.limits_version==='automatic-review-envelope-v2'&&<p>审核模型：{r.review.model?.provider} / {r.review.model?.model}；推理等级：{r.review.reasoning_effort}；审核等待上限：{r.review.timeout_ms===null?'不额外限制':traceNumber(r.review.timeout_ms)+' ms'}；任务总期限：{r.review.task_timeout_ms===null?'不限时':traceNumber(r.review.task_timeout_ms)+' ms'}；实际可用审核等待：{r.review.effective_wait_ms===null?'不限时':traceNumber(r.review.effective_wait_ms)+' ms'}。</p>}
    {['proposal-constraints-v1','proposal-constraints-v2','proposal-constraints-v3','proposal-constraints-v4','proposal-constraints-v5','proposal-constraints-v6','proposal-constraints-v7'].includes(r.review?.contract_version)&&<p>审核同时检查答案、修正建议与恢复步骤；关键约束不满足时，数字正确或高分也不能放行。</p>}
    {['proposal-constraints-v3','proposal-constraints-v4','proposal-constraints-v5','proposal-constraints-v6','proposal-constraints-v7'].includes(r.review?.contract_version)&&<p>材料未提供的实现细节保持未知；风险推测须标明前提，不以不同用途的数值不同直接认定冲突。</p>}
    {r.final_correction&&<section aria-label="最终答复纠正记录">
      <h4>最终答复纠正（最多 {r.final_correction.maximum} 次）</h4>
      <p>状态：{({pending:'等待纠正',correcting:'纠正中','waiting-review':'等待复审',accepted:'复审通过',rejected:'未通过',failed:'停止',cancelled:'已取消','not-dispatched':'未派发'} as Record<string,string>)[r.final_correction.status]??r.final_correction.status}；已派发纠正 {r.final_correction.attempt} 次。</p>
      <p>首次检查：{traceNumber(r.final_correction.initial_evaluation?.score)} 分，{r.final_correction.initial_evaluation?.rationale??'未记录理由'}</p>
      {r.final_correction.evaluation&&<p>复审：{traceNumber(r.final_correction.evaluation.score)} 分，{r.final_correction.evaluation.rationale}</p>}
      {r.final_correction.reason&&<p>停止原因：{r.final_correction.reason}</p>}
      <p>未交付的旧候选仅保留审计；工具和已完成节点不重复执行。纠正及复审费用分别列在调用账本。</p>
    </section>}
    {r.quality?.response_normalization?.changes?.length>0&&<details><summary>审核返回格式规范化（{r.quality.response_normalization.changes.length} 处）</summary>
      <p>原始回执保留；仅按已知规则修正字段拼写，判定、分数和引用不变，没有增加审核调用。</p>
      <p>规则：{r.quality.response_normalization.version}</p>
      <ul>{r.quality.response_normalization.changes.map((change:Row)=><li key={change.check_id}>{change.check_id}：{change.from} → {change.to==='removed-empty-alias'?'删除多余空字段':change.to}</li>)}</ul>
    </details>}
    {r.quality?.evidence_references&&<p>引用由核心绑定原文：{r.quality.evidence_references.version}。编号仅定位证据，不代表审核通过。</p>}
    {r.quality?.trusted_deterministic_receipt&&<p>独立校验已确认答案字段：{r.quality.trusted_deterministic_receipt.checked_fields.join('、')}。正文与建议仍须通过语义审核。</p>}
    {r.quality?.grounding_checks?.length>0&&<details><summary>来源与因果核对（同一次审核）</summary>
      <Table heads={['核对项','判定','候选原句','材料引用','理由']}>
        {r.quality.grounding_checks.map((check:Row)=><tr key={check.check_id}>
          <td style={cellStyle}>{check.check_id==='source-state'?'事实状态来源':check.check_id==='time-causality'?'时间与因果':check.check_id?.startsWith('source-claim-')?'事实句 '+check.check_id.slice(13):check.check_id}{check.claim_kind&&<small> · {({FACT:'系统状态断言',CONDITIONAL:'条件假设',SELF_REPORT:'本次行为说明',QUOTED_OR_WARNING:'引用或警告'} as Record<string,string>)[check.claim_kind]??check.claim_kind}</small>}</td>
          <td style={cellStyle}>{({PASS:'通过',FAIL:'未通过',UNCERTAIN:'无法判断',NOT_APPLICABLE:'不适用'} as Record<string,string>)[check.status]??check.status}</td>
          <td style={cellStyle}>{check.answer_quote??(check.target_scope==='whole-candidate'&&check.status!=='NOT_APPLICABLE'?'整份回复（绑定候选哈希）':'无适用原句')}</td>
          <td style={cellStyle}>{check.source_quote??'未提供来源引用'}</td>
          <td style={cellStyle}>{check.rationale??'审核器未提供本项补充说明；请查看总体评审理由。'}</td></tr>)}
      </Table><p>引用是否存在由 Python 核对；语义由审核模型判断，不代表已独立证明结论正确。</p>
    </details>}
    {typeof r.deterministic_validation?.passed==='boolean'&&<p>固定事实检查：{r.deterministic_validation.passed?'通过':'未通过'}；已知事实不符时，模型高分不能覆盖该结果。</p>}
    {r.planner_normalizations?.length>0&&<details><summary>规划格式兼容记录</summary><pre>{JSON.stringify(r.planner_normalizations,null,2)}</pre></details>}
    <p>工具证据：{r.tools?.message??'未记录'}；评审：{r.review?.required===false?'按策略未要求':label(r.review?.status)}，分数 {traceNumber(r.review?.score??r.quality?.score)}，原始结论{r.review?.passed===true?'通过':r.review?.passed===false?'未通过':'未记录'}。
      门槛验收：{r.quality_gate==='passed'?'达到':r.quality_gate==='failed'?'未达到':r.quality_gate==='not-required'?'本次未要求':'未记录'}。最终运行状态与质量验收并非同一概念。</p>
    {r.tools?.records?.length?<details><summary>宿主工具回执（{r.tools.records.length} 条）</summary><ol>{r.tools.records.map((t:Row,i:number)=><li key={`${t.call_id}-${i}`}>{t.node} / {t.tool}：{t.outcome}；回执 {t.call_id}</li>)}</ol><p>completed 表示回执已返回，不自动证明测试成功或命令退出为零。</p></details>:null}
    {r.quality?.rationale&&<details><summary>评审说明</summary><p>{r.quality.rationale}</p><p>这是模型评审记录，不替代独立测试或人工验收。</p></details>}
    {r.issues?.length?<ul>{r.issues.map((v:unknown,i:number)=><li key={i}>{typeof v==='string'?v:JSON.stringify(v)}</li>)}</ul>:<p>该记录未报告运行错误。</p>}
    <details><summary>范围与缺失证据</summary><p>仅覆盖 Router 受管模型调用；宿主其他工具、独立子 Agent 及订阅月费未归入本次按调用现金成本。</p>
      {r.profile_scope&&<p>画像范围：{r.profile_scope}</p>}
      {r.limitations?.map((v:string,i:number)=><p key={i}>{v}</p>)}{r.missing_evidence?.length?<p>缺失字段：{r.missing_evidence.join('、')}。缺失不表示已通过或零费用。</p>:null}</details>
  </article>
}
export function AutomaticTrace({references,load}:{references:AutomaticRef[];load:(ids:string[])=>Promise<AutomaticHistory>}){
  const [data,setData]=useState<AutomaticHistory>(),[error,setError]=useState('')
  const key=references.map(r=>`${r.id}:${r.state}`).join(',')
  useEffect(()=>{let active=true,inflight=false
    setData(undefined);setError('')
    const refresh=async()=>{if(inflight||!references.length)return;inflight=true
      try{const value=await load(references.map(r=>r.id));if(active){setData(value);setError('')}}
      catch(e){if(active)setError(e instanceof Error?e.message:String(e))}finally{inflight=false}}
    void refresh();const timer=references.some(r=>r.state==='running')?setInterval(()=>void refresh(),2500):undefined
    return()=>{active=false;if(timer)clearInterval(timer)}
  },[load,key])
  if(!references.length)return null
  return <section><h2>自动路由</h2><p>只展示当前已加载会话引用的最近 20 条记录；历史预算、模型与结论来自当时的冻结证据。</p>
    {error&&<p role="alert">轨迹读取失败：{error}。不会重新执行任务。</p>}
    {!data&&!error&&<p role="status">正在读取已有运行证据，不调用模型…</p>}
    {data?.errors.filter(e=>references.some(ref=>ref.id===e.run_id)).map(e=><p key={e.run_id} role="status">{e.run_id}：{e.message}</p>)}
    {data?.records.map(r=>{const reference=references.find(ref=>ref.id===r.run_id)
      return reference?<AutomaticRecord key={r.run_id} record={r} reference={reference}/>:null})}</section>
}
