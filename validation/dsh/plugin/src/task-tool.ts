import type { DshContext, JsonSchema, TaskSummary, ToolExecution, ValidationResult } from './contracts.js'

export interface TaskArguments {
  task: string
  mode: 'preflight' | 'demo' | 'plan' | 'run'
  method: 'A' | 'B'
  qualityMin: number
  costMax: number
  latencyMaxMs: number
  weights?: { quality: number; cost: number; latency: number }
  plan?: Record<string, unknown>
  maxConcurrency?: number
  providerConcurrency?: Record<string, number>
  providerMinIntervalMs?: Record<string, number>
  acceptanceCriteria?: string[]
  plannerModelId?: string
  maxProductionCost?: number
  maxEvaluationCost?: number
}

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}
function finite(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) throw new Error(`invalid ${field}`)
  return value
}
export function taskArguments(raw: unknown): TaskArguments {
  if (!record(raw)) throw new Error('task arguments must be an object')
  const allowed = new Set(['task', 'mode', 'method', 'qualityMin', 'costMax', 'latencyMaxMs',
    'weights', 'plan', 'plannerModelId', 'maxProductionCost', 'maxEvaluationCost', 'acceptanceCriteria', 'maxConcurrency', 'providerConcurrency', 'providerMinIntervalMs'])
  if (Object.keys(raw).some(key => !allowed.has(key))) throw new Error('unknown task argument')
  if (typeof raw.task !== 'string' || !raw.task.trim() || raw.task.length > 12000) throw new Error('task must contain 1..12000 characters')
  const mode = raw.mode ?? 'preflight'
  if (mode !== 'preflight' && mode !== 'demo' && mode !== 'plan' && mode !== 'run') throw new Error('invalid task mode')
  if (raw.method !== 'A' && raw.method !== 'B') throw new Error('method must be A or B')
  const args: TaskArguments = { task: raw.task, mode, method: raw.method,
    qualityMin: finite(raw.qualityMin, 'qualityMin'), costMax: finite(raw.costMax, 'costMax'),
    latencyMaxMs: finite(raw.latencyMaxMs, 'latencyMaxMs') }
  if (args.qualityMin > 100 || args.latencyMaxMs <= 0) throw new Error('invalid quality/latency constraints')
  if (raw.method === 'B') {
    if (!record(raw.weights) || Object.keys(raw.weights).sort().join(',') !== 'cost,latency,quality') {
      throw new Error('B requires three explicit weights')
    }
    args.weights = { quality: finite(raw.weights.quality, 'quality weight'),
      cost: finite(raw.weights.cost, 'cost weight'), latency: finite(raw.weights.latency, 'latency weight') }
    const sum = args.weights.quality + args.weights.cost + args.weights.latency
    if (!Number.isFinite(sum) || sum <= 0) throw new Error('invalid weight sum')
  } else if (raw.weights !== undefined) throw new Error('A does not accept weights')
  if (raw.maxConcurrency !== undefined) {
    const value = finite(raw.maxConcurrency, 'maxConcurrency')
    if (!Number.isInteger(value) || value < 1 || value > 8) throw new Error('invalid maxConcurrency')
    args.maxConcurrency = value
  }
  for (const key of ['providerConcurrency', 'providerMinIntervalMs'] as const) {
    if (raw[key] === undefined) continue
    const values = raw[key]
    if (!record(values) || Object.keys(values).length > 16) throw new Error(`invalid ${key}`)
    const mapped: Record<string, number> = {}
    for (const [provider, value] of Object.entries(values)) {
      if (!provider.trim() || provider.length > 100) throw new Error(`invalid ${key}`)
      const n = finite(value, key)
      if (!Number.isInteger(n) || n < (key === 'providerConcurrency' ? 1 : 0)
        || n > (key === 'providerConcurrency' ? 8 : 60000)) throw new Error(`invalid ${key}`)
      mapped[provider] = n
    }
    args[key] = mapped
  }
  if (raw.acceptanceCriteria !== undefined) {
    const criteria = raw.acceptanceCriteria
    if (!Array.isArray(criteria) || criteria.length < 1 || criteria.length > 10
      || criteria.some((c: unknown) => typeof c !== 'string' || !c.trim() || c.length > 1000)
      || new Set(criteria).size !== criteria.length) throw new Error('invalid acceptanceCriteria')
    args.acceptanceCriteria = criteria as string[]
  }
  if (raw.plan !== undefined) {
    if (!record(raw.plan)) throw new Error('plan must be an object')
    args.plan = raw.plan // Python is the owner of DAG validation.
  }
  if (raw.plannerModelId !== undefined) {
    if (typeof raw.plannerModelId !== 'string' || !raw.plannerModelId.trim()) throw new Error('invalid plannerModelId')
    args.plannerModelId = raw.plannerModelId
  }
  for (const key of ['maxProductionCost', 'maxEvaluationCost'] as const) {
    if (raw[key] !== undefined) args[key] = finite(raw[key], key)
  }
  if (Buffer.byteLength(JSON.stringify(args)) > 131072) throw new Error('task request too large')
  return args
}

export const TASK_SUMMARY_SCHEMA: JsonSchema = {
  type: 'object', additionalProperties: false,
  required: ['status', 'mode', 'planOrigin', 'nodes', 'qualityScore', 'evaluationPassed',
    'outputPreview', 'resultPath', 'productionCost', 'evaluationCost', 'unconfirmedCost', 'costIsSimulated', 'wallTimeMs', 'executionMode', 'maxConcurrency', 'peakActiveNodes', 'predictedLatencyMs'],
  properties: {
    executionMode: { type: 'string', enum: ['serial', 'bounded-parallel'] }, maxConcurrency: { type: 'number' },
    peakActiveNodes: { oneOf: [{ type: 'number' }, { type: 'null' }] },
    predictedLatencyMs: { oneOf: [{ type: 'number' }, { type: 'null' }] },
    status: { type: 'string' }, mode: { type: 'string' }, planOrigin: { type: 'string' },
    nodes: { type: 'array', items: { type: 'object', additionalProperties: false,
      required: ['nodeId', 'nodeType', 'parents', 'modelId'], properties: {
        nodeId: { type: 'string' }, nodeType: { type: 'string' }, modelId: { type: 'string' },
        parents: { type: 'array', items: { type: 'string' } },
      } } },
    qualityScore: { oneOf: [{ type: 'number' }, { type: 'null' }] },
    evaluationPassed: { oneOf: [{ type: 'boolean' }, { type: 'null' }] },
    outputPreview: { type: 'string' }, resultPath: { type: 'string' },
    productionCost: { type: 'number' }, evaluationCost: { type: 'number' },
    unconfirmedCost: { type: 'number' }, costIsSimulated: { type: 'boolean' }, wallTimeMs: { type: 'number' },
  },
}

export function decodeTaskSummary(raw: unknown): TaskSummary {
  if (!record(raw) || !Array.isArray(raw.nodes)) throw new Error('invalid task summary')
  function str(key: string): string {
    if (typeof rawValue[key] !== 'string') throw new Error(`invalid task ${key}`)
    return rawValue[key]
  }
  const rawValue = raw
  if (raw.qualityScore !== null) finite(raw.qualityScore, 'qualityScore')
  if (raw.evaluationPassed !== null && typeof raw.evaluationPassed !== 'boolean') throw new Error('invalid evaluationPassed')
  if (typeof raw.costIsSimulated !== 'boolean') throw new Error('invalid costIsSimulated')
  if (raw.executionMode !== 'serial' && raw.executionMode !== 'bounded-parallel') throw new Error('invalid executionMode')
  const concurrency = finite(raw.maxConcurrency, 'maxConcurrency')
  if (!Number.isInteger(concurrency) || concurrency < 1 || concurrency > 8) throw new Error('invalid maxConcurrency')
  const peak = raw.peakActiveNodes === null ? null : finite(raw.peakActiveNodes, 'peakActiveNodes')
  if (peak !== null && (!Number.isInteger(peak) || peak > concurrency)) throw new Error('invalid peakActiveNodes')
  return { executionMode: raw.executionMode, maxConcurrency: concurrency, peakActiveNodes: peak,
    predictedLatencyMs: raw.predictedLatencyMs === null ? null : finite(raw.predictedLatencyMs, 'predictedLatencyMs'),
    status: str('status'), mode: str('mode'), planOrigin: str('planOrigin'),
    nodes: raw.nodes.map((node: unknown) => {
      if (!record(node) || typeof node.nodeId !== 'string' || typeof node.nodeType !== 'string'
          || typeof node.modelId !== 'string' || !Array.isArray(node.parents)
          || !node.parents.every((p: unknown) => typeof p === 'string')) throw new Error('invalid task node')
      return { nodeId: node.nodeId, nodeType: node.nodeType, parents: node.parents as string[], modelId: node.modelId }
    }), qualityScore: raw.qualityScore === null ? null : finite(raw.qualityScore, 'qualityScore'),
    evaluationPassed: raw.evaluationPassed, outputPreview: str('outputPreview'), resultPath: str('resultPath'),
    productionCost: finite(raw.productionCost, 'productionCost'), evaluationCost: finite(raw.evaluationCost, 'evaluationCost'),
    unconfirmedCost: finite(raw.unconfirmedCost, 'unconfirmedCost'), costIsSimulated: raw.costIsSimulated, wallTimeMs: finite(raw.wallTimeMs, 'wallTimeMs'),
  }
}

export function registerTaskTool(ctx: DshContext, outputSchema: JsonSchema,
  execute: (args: TaskArguments, exec: ToolExecution) => Promise<ValidationResult>): void {
  ctx.tools.register({
    name: 'refractrouter_task',
    description: '通过 Python 核心规划带交接契约的文本 DAG 并按节点选模。'
      + '规划器识别真实独立分支、解释拆分收益，简单任务可保留单节点；支持显式有界并发及 Provider 派发间隔。'
      + 'preflight 使用单节点预览；demo 返回模拟产物；plan 付费规划；run 执行并独立评审。'
      + 'acceptanceCriteria 可固定验收条件；详细契约和结构诊断保存在任务产物中。'
      + 'plan/run 需要部署开关和双预算。迁移 profile 不保证质量；不执行外部工具动作。',
    parameters: { type: 'object', additionalProperties: false,
      required: ['task', 'method', 'qualityMin', 'costMax', 'latencyMaxMs'], properties: {
        task: { type: 'string' }, mode: { type: 'string', enum: ['preflight', 'demo', 'plan', 'run'] },
        method: { type: 'string', enum: ['A', 'B'] }, qualityMin: { type: 'number' },
        costMax: { type: 'number' }, latencyMaxMs: { type: 'number' },
        weights: { type: 'object', additionalProperties: false, required: ['quality', 'cost', 'latency'],
          properties: { quality: { type: 'number' }, cost: { type: 'number' }, latency: { type: 'number' } } },
        maxConcurrency: { type: 'number' }, providerConcurrency: { type: 'object', additionalProperties: true },
        providerMinIntervalMs: { type: 'object', additionalProperties: true },
        acceptanceCriteria: { type: 'array', items: { type: 'string' } },
        plan: { type: 'object', additionalProperties: true }, plannerModelId: { type: 'string' },
        maxProductionCost: { type: 'number' }, maxEvaluationCost: { type: 'number' },
      } },
    output: { schema: outputSchema, render: (_args, value) => [{ type: 'text', text: JSON.stringify(value) }] },
    execute: async (args, exec) => execute(taskArguments(args), exec),
  })
}
