/** DSH 客户端贡献：展示宿主进度与核心只读证据，不派发模型或重新推断路由。 */
import {automaticRefs,loadAutomaticHistory,useAutomaticHistory,type AutomaticHistory,type AutomaticRef,type TraceSnapshot} from './automatic-trace.js'
import {TraceRecord,automaticStartedAt} from './trace-record.js'
import {decodeDag,dagNodePresentation} from '../dag-progress.js'
import type {ClientContext} from './types.js'
interface GraphNode { id: string; objective: string; parents: string[]; model: string; state: string; type: string; difficulty: string; risk: string }
interface GraphData { nodes: GraphNode[]; phase: string; interrupted: boolean }
interface GraphProps { useChat<T>(select: (snapshot: TraceSnapshot) => T): T; loadAutomatic?:(ids:string[])=>Promise<AutomaticHistory> }
interface GraphRecord {key:string;runId?:string;turn?:number;data:GraphData|null;startedAt?:string;elapsedMs?:number;
  state:AutomaticRef['state'];error?:string;order:number}
type ElementFactory = (tag: string | ((props: any) => unknown), props: Record<string, unknown> | null, ...children: unknown[]) => unknown
interface GraphContext { remote?:ClientContext['remote'];slots: { inject(name: string, callback: () => Generator<unknown>): void; register(options: Record<string, unknown>, component: (props: GraphProps) => unknown): unknown } }
export function graphModule(h: ElementFactory) {
  const catalog = [
    ['planning', '规划', '分解问题、制定分析路径与步骤。'],
    ['extraction', '提取', '从已有材料提取事实、数据、约束和证据。'],
    ['synthesis', '综合', '整合多份输入，比较趋势、解释驱动因素并处理冲突。'],
    ['generation', '生成', '撰写分析、预测、建议或最终交付正文。'],
    ['verification', '验证', '核对事实、逻辑、覆盖范围与输出要求；不同于最终独立评审。'],
  ]
  const roles: Record<string, { label: string; description: string; fill: string }> = {
    'role-classifier': { label: '规划前输入分级', description: '规划模型调用前检查任务输入的敏感级别与部署许可。', fill: '#3b2f1b' },
    'role-placement': { label: '节点放置准入', description: '规划完成后逐节点检查敏感级别与可用部署路线；按策略可使用分类器。', fill: '#49351b' },
    'role-planner': { label: '规划器', description: '由规划模型生成任务 DAG 与依赖。', fill: '#30264c' },
    'role-reviewer': { label: '独立评审器', description: '检查最终交付；自适应策略可能明确跳过。', fill: '#163d3c' },
  }
  // 解析本插件受契约测试保护的纯文本展示格式；不从任务内容猜类型、模型或边。
  // 流式末尾的不完整条目被忽略，完整条目到达后再显示；无效拓扑不绘制。
  function parse(text: string): GraphData | null {
    if (!text.startsWith('正在快速拆分任务，')
      && !text.startsWith('正在预览自动拆分流程。')
      && !text.startsWith('正在预检并执行真实自动路由。')
      && !text.startsWith('已获一次性授权，正在执行真实自动路由。')) return null
    const nodes = new Map<string, GraphNode>()
    let phase = '规划任务'
    for (const match of text.matchAll(/^【([^\n】]+)】|^([^\n]+?) · ([^\n]*)\n(?:  类型：([^\n；]+)；难度：([^\n；]+)；风险：([^\n]+)\n)?  依赖：([^\n]+)\n  模型：([^\n]+)\n  状态：([^\n]+)\n|^- ([^\n：]+)：([^\n；]+)；模型 ([^\n；]+)；依赖 ([^\n]+)\n/gm)) {
      if (match[1]) { if (match[1] === '节点清单') nodes.clear(); else if (match[1] !== '任务摘要') phase = match[1]; continue }
      if (match[2]) nodes.set(match[2], { id: match[2], objective: match[3], type: match[4] ?? '未提供', difficulty: match[5] ?? '未提供', risk: match[6] ?? '未提供', parents: match[7] === '无' ? [] : match[7].split('、'), model: match[8], state: match[9] })
      else {
        const node = nodes.get(match[10])
        if (node) { node.state = match[11]; node.model = match[12]; node.parents = match[13] === '无' ? [] : match[13].split('、') }
      }
    }
    const result = { nodes: [...nodes.values()], phase, interrupted: text.includes('执行已中断；') }
    if (result.nodes.length > 12 || result.nodes.some(n => n.parents.some(p => !nodes.has(p)))) return null
    return layout(result.nodes) ? result : null
  }
  function layout(nodes: GraphNode[]): Map<string, { x: number; y: number }> | null {
    const levels = new Map<string, number>()
    for (let pass = 0; pass < nodes.length; pass++) for (const n of nodes) {
      if (!levels.has(n.id) && n.parents.every(p => levels.has(p))) levels.set(n.id, n.parents.length ? Math.max(...n.parents.map(p => levels.get(p)!)) + 1 : 0)
    }
    if (levels.size !== nodes.length) return null
    const columns = new Map<number, number>()
    const counts = new Map<number, number>()
    for (const level of levels.values()) counts.set(level, (counts.get(level) ?? 0) + 1)
    const widest = Math.max(1, ...counts.values())
    return new Map(nodes.map(n => {
      const level = levels.get(n.id)!, column = columns.get(level) ?? 0
      columns.set(level, column + 1)
      return [n.id, { x: 24 + (widest - counts.get(level)!) * 155 + column * 310, y: 24 + level * 200 }]
    }))
  }
  function records(snapshot:TraceSnapshot):GraphRecord[]{
    const found=new Map<string,GraphRecord>()
    const add=(text:string,turn:number|undefined,state:AutomaticRef['state'],order:number)=>{
      const data=parse(text)
      if(!data)return
      const match=/【自动路由记录】(\d{8}T\d{6}Z-[0-9a-f]{12})|^记录：[^\n]*[\/\\](\d{8}T\d{6}Z-[0-9a-f]{12})[\/\\](?:result|summary)\.json/m.exec(text)
      const id=match?.[1]??match?.[2],key=id??`legacy-${turn??'unknown'}-${order}`
      const duration=[...text.matchAll(/^耗时：(\d+(?:\.\d+)?) 秒\s*$/gm)].at(-1)
      found.set(key,{key,runId:id,turn,data,state: data.interrupted?'interrupted':state,order,
        startedAt:id?automaticStartedAt(id):undefined,elapsedMs:duration?Number(duration[1])*1000:undefined})
    }
    snapshot.legacy.nodes.forEach((node,index)=>{
      if(node.kind==='assistant'&&(!node.provenance||node.provenance.provider==='refractagent'))
        add(node.blocks?.filter(b=>b.kind==='reasoning').map(b=>b.text??'').join('\n')??'',node.turn,
          node.interrupted?'interrupted':'settled',index)
    })
    if(snapshot.legacy.partial)add(snapshot.legacy.partial.blocks.filter(b=>b.kind==='reasoning').map(b=>b.text??'').join('\n'),
      snapshot.legacy.partial.turn,'running',snapshot.legacy.nodes.length)
    for(const ref of automaticRefs(snapshot)){
      const previous=found.get(ref.id)
      found.set(ref.id,{...(previous??{key:ref.id,runId:ref.id,data:null,order:-1,startedAt:automaticStartedAt(ref.id)}),
        turn:ref.turn,state:ref.state,error:ref.error})
    }
    return [...found.values()].sort((a,b)=>
      (b.startedAt?.localeCompare(a.startedAt??'')??(a.startedAt?-1:0))
      ||(b.turn??b.order)-(a.turn??a.order)||b.order-a.order).slice(0,20)
  }
  function color(state: string, role = false): string {
    if (state.startsWith('已完成')) return '#34d399'
    if (state.includes('失败')) return '#fb7185'
    if (role && (state === 'blocked' || state.includes('阻断'))) return '#fb7185'
    if (state.startsWith('运行中')) return '#60a5fa'
    if (state.startsWith('排队')) return '#fbbf24'
    return '#94a3b8'
  }
  function graph(data: GraphData,key:string) {
    const positions = layout(data.nodes)!
    const points = [...positions.values()]
    const width = Math.max(360, ...points.map(p => p.x + 302)), height = Math.max(160, ...points.map(p => p.y + 170))
    const marker=`refract-dag-arrow-${key.replace(/[^a-zA-Z0-9-]/g,'-')}`
    const edges = data.nodes.flatMap(n => n.parents.map(parent => {
      const a = positions.get(parent)!, b = positions.get(n.id)!
      return h('path', { key: `${parent}:${n.id}`, d: `M ${a.x+140} ${a.y+148} C ${a.x+140} ${a.y+172}, ${b.x+140} ${b.y-24}, ${b.x+140} ${b.y-6}`, fill: 'none', stroke: '#94a3b8', strokeWidth: 2, markerEnd: `url(#${marker})` })
    }))
    return h('div', { style: { overflowX: 'auto', borderRadius: 16, background: '#111827', padding: 8 } },
      h('svg', { role: 'img', 'aria-label': '任务 DAG 依赖图，箭头从上游指向下游', viewBox: `0 0 ${width} ${height}`, width, height, style: { display: 'block', minWidth: '100%' } },
        h('title', null, '任务 DAG：箭头表示下游消费上游结果'),
        h('defs', null, h('marker', { id: marker, viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: 'auto' }, h('path', { d: 'M 0 0 L 10 5 L 0 10 z', fill: '#94a3b8' }))),
        ...edges, ...data.nodes.map(n => {
          const p = positions.get(n.id)!, role = roles[n.type]
          const label = role?.label ?? catalog.find(row => row[0] === n.type)?.[1] ?? n.type
          return h('g', { key: n.id, transform: `translate(${p.x},${p.y})` },
            h('title', null, `${n.id}：${n.objective}\n${n.model}\n依赖：${n.parents.join('、') || '无'}`),
            h('rect', { width: 280, height: 148, rx: role ? 22 : 12, fill: role?.fill ?? '#1e293b', stroke: color(n.state, Boolean(role)), strokeWidth: role ? 3 : 2, strokeDasharray: role ? '8 5' : undefined }),
            h('text', { x: 14, y: 26, fill: '#f8fafc', fontSize: 16, fontWeight: 600 }, n.id.slice(0, 28)),
            h('text', { x: 14, y: 50, fill: '#cbd5e1', fontSize: 12 }, role ? `${label} · 流程角色` : `${label} · 难度 ${n.difficulty} · 风险 ${n.risk}`),
            h('text', { x: 14, y: 76, fill: '#e2e8f0', fontSize: 13 }, n.objective.slice(0, 18) + (n.objective.length > 18 ? '…' : '')),
            h('text', { x: 14, y: 102, fill: '#cbd5e1', fontSize: 11 }, n.model.slice(0, 37) + (n.model.length > 37 ? '…' : '')),
            h('text', { x: 14, y: 130, fill: color(n.state, Boolean(role)), fontSize: 13 }, n.state.slice(0, 28)))
        })))
  }
  function View({ useChat,loadAutomatic }: GraphProps) {
    // conversation.view 的会话正文由 DSH Chat 标准 hook 提供；useSession 只包含
    // Session 元数据。legacy 是 DSH 为完整消息序列与流式 partial 保留的兼容投影。
    const snapshot = useChat(s => s)
    const history=records(snapshot)
    const references=history.flatMap(r=>r.runId?[{id:r.runId,turn:r.turn,state:r.state,error:r.error}]:[])
    const {data: saved,error}=useAutomaticHistory(references,loadAutomatic)
    const phases:Record<string,string>={classifying:'数据分级与部署准入',planning:'规划任务',routing:'计划就绪／模型分配',
      executing:'执行节点',evaluating:'独立评审',finished:'执行结束'}
    return h('section', { style: { padding: '20px 24px', color: 'var(--dsw-alias-label-primary)', maxWidth: 1100, margin: 'auto', width: '100%', boxSizing: 'border-box' } },
      h('h2', null, '任务 DAG'),
      h('p', null, '当前会话最近 20 条任务流程按时间由新到旧排列，默认收合；点击标题查看节点和连线。标题显示本地开始时间与总耗时，运行中自动更新。'),
      error?h('p',{role:'alert'},`历史图读取失败：${error}。保留宿主已保存的图，不重发任务。`):null,
      !history.length?h('p',{role:'status'},'尚无任务流程图。提交新任务后，会显示实际发生的规划、执行、数据准入与评审环节。'):null,
      ...history.map(record=>{
        const result=saved?.records.find(r=>r.run_id===record.runId)
        const readError=saved?.errors.find(r=>r.run_id===record.runId)
        let data=record.data
        let graphError=''
        if((record.state!=='running'||!data?.nodes.length)&&result?.dag?.nodes?.length){
          // 结构化历史直接展示，不再序列化为文本后解析；客户端 bundle 的缩进
          // 会改变多行模板里的空白，不能把这种字符串往返作为回放合同。
          try{const dag=decodeDag(result.dag),nodes=dag.nodes.map(dagNodePresentation)
            if(layout(nodes))data={nodes,phase:phases[dag.phase]??dag.phase,interrupted:record.state==='interrupted'}
            else graphError='节点或依赖格式无法回放'}catch(e){graphError=e instanceof Error?e.message:String(e)}
        }
        const status=record.state==='interrupted'?'宿主已中断':record.state==='running'?'运行中':
          result?.status==='completed'?'已完成':result?.status==='preview'?'零调用预览':result?.status?`已停止：${result.status}`:data?.phase??'状态未记录'
        return h(TraceRecord,{key:record.key,title:`任务 DAG · ${status}${data?.nodes.length?` · ${data.nodes.length} 个流程节点`:''}`,
          identity:`宿主轮次 ${record.turn??'未记录'}${record.runId?` · 记录 ${record.runId}`:''}`,
          startedAt:record.startedAt,elapsedMs:result?.wall_time_ms??record.elapsedMs,running:record.state==='running'},
          h('p',{role:'status'},record.error??`${data?.phase??'尚无完整节点进度'}${record.state==='interrupted'?' · 保留最后保存的状态，不自动重发。':''}`),
          readError?h('p',{role:'status'},`历史证据读取失败：${readError.message}。`):null,
          graphError?h('p',{role:'status'},`历史图校验未通过：${graphError}。保留宿主已保存的节点。`):null,
          data?.nodes.length?graph(data,record.key):h('p',null,'该次记录尚无可回放的节点图；缺少图不表示任务已完成。'),
          data?.nodes.length?h('details',null,h('summary',null,'节点完整说明与依赖'),...data.nodes.map(n=>h('p',{key:n.id},
            `${n.id} · ${n.objective}｜类型 ${n.type}｜模型 ${n.model}｜状态 ${n.state}｜依赖 ${n.parents.join('、')||'无'}`))):null)
      }),
      h('details',null,h('summary',null,'流程角色与任务分类说明'),
      h('p',null,'实线方框是实际执行任务，带色虚线框是规划、数据分级／部署准入或评审等流程角色；箭头表示先后依赖，不代表相邻节点一定串行。'),
      h('h3', null, '流程角色节点'),
      h('p', null, '角色节点表示 DAG 的控制与质量环节，不是普通交付节点；它们使用虚线边框，并按核心进度显示运行、完成、阻断或跳过状态。'),
      h('table', { style: { width: '100%', borderCollapse: 'collapse', lineHeight: 1.8 } }, h('thead', null, h('tr', null, h('th', { style: { textAlign: 'left' } }, '角色'), h('th', { style: { textAlign: 'left' } }, '作用与出现条件'))),
        h('tbody', null, ...Object.entries(roles).map(([id, row]) => h('tr', { key: id }, h('td', { style: { padding: '8px 12px 8px 0', verticalAlign: 'top' } }, `${row.label} · ${id}`), h('td', null, row.description))))),
      h('p', null, '简单直答可能不调用规划器；安全策略启用时，规划前输入分级与规划后的节点放置准入会分开显示；自适应评审跳过时仍显示评审节点及“按策略跳过”，不会伪装成已评审。'),
      h('h3', null, '任务分类清单'),
      h('p', null, 'forecast（预测）、drivers（驱动因素）、trend（趋势）、answer（最终回答）是自由命名的节点 ID，没有固定清单；名称不能决定正式类型。'),
      h('table', { style: { width: '100%', borderCollapse: 'collapse', lineHeight: 1.8 } }, h('thead', null, h('tr', null, h('th', { style: { textAlign: 'left' } }, '正式类型'), h('th', { style: { textAlign: 'left' } }, '说明'))),
        h('tbody', null, ...catalog.map(([id, label, description]) => h('tr', { key: id }, h('td', { style: { padding: '8px 12px 8px 0', verticalAlign: 'top' } }, `${label} · ${id}`), h('td', null, description))))),
      h('p', null, '上表只说明实际执行节点的正式类型，不包含规划、分类和评审等流程角色。难度 difficulty、风险 risk 均为 low / medium / high，由规划器估计；模型分配还考虑预算、上下文与输出需求及核心配置，不由节点名称直接决定。')))
  }
  return { inject: ['slots'], apply(ctx: GraphContext) {
    const loadAutomatic=loadAutomaticHistory(ctx)
    ctx.slots.inject('conversation.view', function* () { yield ctx.slots.register({ name: 'conversation.view', id: 'refractagent-dag', order: 15, label: () => '任务 DAG',inject:()=>({loadAutomatic}) }, View) })
  }, parse, layout, records }
}
