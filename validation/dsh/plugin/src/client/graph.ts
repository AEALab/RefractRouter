/** DSH 客户端贡献：只投影插件已展示的进度，不读取文件、不执行请求或重新推断路由。 */
interface GraphNode { id: string; objective: string; parents: string[]; model: string; state: string; type: string; difficulty: string; risk: string }
interface GraphData { nodes: GraphNode[]; phase: string; interrupted: boolean }
interface Block { kind: string; text?: string }
interface Snapshot { nodes: Array<{ kind: string; blocks?: Block[]; turn?: number }>; partial: { blocks: Block[] } | null }
interface ChatSnapshot { legacy: Snapshot }
interface GraphProps { useChat<T>(select: (snapshot: ChatSnapshot) => T): T }
type ElementFactory = (tag: string | ((props: GraphProps) => unknown), props: Record<string, unknown> | null, ...children: unknown[]) => unknown
interface GraphContext { slots: { inject(name: string, callback: () => Generator<unknown>): void; register(options: Record<string, unknown>, component: (props: GraphProps) => unknown): unknown } }
export function graphModule(h: ElementFactory) {
  const catalog = [
    ['planning', '规划', '分解问题、制定分析路径与步骤。'],
    ['extraction', '提取', '从已有材料提取事实、数据、约束和证据。'],
    ['synthesis', '综合', '整合多份输入，比较趋势、解释驱动因素并处理冲突。'],
    ['generation', '生成', '撰写分析、预测、建议或最终交付正文。'],
    ['verification', '验证', '核对事实、逻辑、覆盖范围与输出要求；不同于最终独立评审。'],
  ]
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
    if (result.nodes.length > 8 || result.nodes.some(n => n.parents.some(p => !nodes.has(p)))) return null
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
  function color(state: string): string {
    if (state.startsWith('已完成')) return '#34d399'
    if (state.includes('失败')) return '#fb7185'
    if (state.startsWith('运行中')) return '#60a5fa'
    if (state.startsWith('排队')) return '#fbbf24'
    return '#94a3b8'
  }
  function graph(data: GraphData) {
    const positions = layout(data.nodes)!
    const points = [...positions.values()]
    const width = Math.max(360, ...points.map(p => p.x + 302)), height = Math.max(160, ...points.map(p => p.y + 170))
    const edges = data.nodes.flatMap(n => n.parents.map(parent => {
      const a = positions.get(parent)!, b = positions.get(n.id)!
      return h('path', { key: `${parent}:${n.id}`, d: `M ${a.x+140} ${a.y+148} C ${a.x+140} ${a.y+172}, ${b.x+140} ${b.y-24}, ${b.x+140} ${b.y-6}`, fill: 'none', stroke: '#94a3b8', strokeWidth: 2, markerEnd: 'url(#refract-dag-arrow)' })
    }))
    return h('div', { style: { overflowX: 'auto', borderRadius: 16, background: '#111827', padding: 8 } },
      h('svg', { role: 'img', 'aria-label': '任务 DAG 依赖图，箭头从上游指向下游', viewBox: `0 0 ${width} ${height}`, width, height, style: { display: 'block', minWidth: '100%' } },
        h('title', null, '任务 DAG：箭头表示下游消费上游结果'),
        h('defs', null, h('marker', { id: 'refract-dag-arrow', viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: 'auto' }, h('path', { d: 'M 0 0 L 10 5 L 0 10 z', fill: '#94a3b8' }))),
        ...edges, ...data.nodes.map(n => {
          const p = positions.get(n.id)!, label = catalog.find(row => row[0] === n.type)?.[1] ?? n.type
          return h('g', { key: n.id, transform: `translate(${p.x},${p.y})` },
            h('title', null, `${n.id}：${n.objective}\n${n.model}\n依赖：${n.parents.join('、') || '无'}`),
            h('rect', { width: 280, height: 148, rx: 12, fill: '#1e293b', stroke: color(n.state), strokeWidth: 2 }),
            h('text', { x: 14, y: 26, fill: '#f8fafc', fontSize: 16, fontWeight: 600 }, n.id.slice(0, 28)),
            h('text', { x: 14, y: 50, fill: '#cbd5e1', fontSize: 12 }, `${label} · 难度 ${n.difficulty} · 风险 ${n.risk}`),
            h('text', { x: 14, y: 76, fill: '#e2e8f0', fontSize: 13 }, n.objective.slice(0, 18) + (n.objective.length > 18 ? '…' : '')),
            h('text', { x: 14, y: 102, fill: '#cbd5e1', fontSize: 11 }, n.model.slice(0, 37) + (n.model.length > 37 ? '…' : '')),
            h('text', { x: 14, y: 130, fill: color(n.state), fontSize: 13 }, n.state.slice(0, 28)))
        })))
  }
  function View({ useChat }: GraphProps) {
    // conversation.view 的会话正文由 DSH Chat 标准 hook 提供；useSession 只包含
    // Session 元数据。legacy 是 DSH 为完整消息序列与流式 partial 保留的兼容投影。
    const snapshot = useChat(s => s.legacy)
    const blocks = [...snapshot.nodes.filter(n => n.kind === 'assistant').map(n => n.blocks ?? []), ...(snapshot.partial ? [snapshot.partial.blocks] : [])]
    let data: GraphData | null = null
    for (const list of blocks) for (const b of list) if (b.kind === 'reasoning' && b.text) { const candidate = parse(b.text); if (candidate) data = candidate }
    return h('section', { style: { padding: '20px 24px', color: 'var(--dsw-alias-label-primary)', maxWidth: 1100, margin: 'auto', width: '100%', boxSizing: 'border-box' } },
      h('h2', null, '任务 DAG'),
      h('p', null, '展示当前已加载会话中最近一次自动拆分。箭头表示下游需要上游结果；同层无依赖节点可以并行。'),
      h('p', { role: 'status' }, data ? `${data.phase}${data.interrupted ? ' · 已中断，图中保留最后收到的状态' : ''}` : '尚无自动 DAG。提交新任务后，规划完成时会在这里显示。'),
      data?.nodes.length ? graph(data) : null,
      data?.nodes.length ? h('details', null, h('summary', null, '节点完整说明与依赖'), ...data.nodes.map(n => h('p', { key: n.id }, `${n.id} · ${n.objective}｜类型 ${n.type}｜模型 ${n.model}｜状态 ${n.state}｜依赖 ${n.parents.join('、') || '无'}`))) : null,
      h('h3', null, '任务分类清单'),
      h('p', null, 'forecast（预测）、drivers（驱动因素）、trend（趋势）、answer（最终回答）是自由命名的节点 ID，没有固定清单；名称不能决定正式类型。'),
      h('table', { style: { width: '100%', borderCollapse: 'collapse', lineHeight: 1.8 } }, h('thead', null, h('tr', null, h('th', { style: { textAlign: 'left' } }, '正式类型'), h('th', { style: { textAlign: 'left' } }, '说明'))),
        h('tbody', null, ...catalog.map(([id, label, description]) => h('tr', { key: id }, h('td', { style: { padding: '8px 12px 8px 0', verticalAlign: 'top' } }, `${label} · ${id}`), h('td', null, description))))),
      h('p', null, '难度 difficulty、风险 risk 均为 low / medium / high，由规划器估计。模型分配还考虑预算、上下文与输出需求及配置中的能力、质量和时延预测，不由节点名称直接决定。'))
  }
  return { inject: ['slots'], apply(ctx: GraphContext) {
    ctx.slots.inject('conversation.view', function* () { yield ctx.slots.register({ name: 'conversation.view', id: 'refractagent-dag', order: 15, label: () => '任务 DAG' }, View) })
  }, parse, layout }
}
