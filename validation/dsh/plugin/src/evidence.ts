import type { BillingUnit } from './contracts.js'

/** Only the Python evidence fields projected into the host tool result.
 * Scoring, hash verification, and benchmark decisions remain in Python.
 */
export interface RunnerEvidence {
  status?: string
  mode?: string
  issues?: string[]
  artifacts?: Record<string, unknown>
  inputs?: Partial<Record<'dataset' | 'model_manifest' | 'corpus' | 'code', { sha256?: string }>>
  preflight?: {
    billing_unit?: BillingUnit
    call_plan?: {
      training_model_calls: number
      production_model_calls: number
      judge_model_calls: number
      total_model_calls: number
    }
    cost_estimates?: {
      billing_unit: BillingUnit
      production_upper_estimate: number
      evaluation_upper_estimate: number
      total_upper_estimate: number
    }
  }
}

function object(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('evidence field must be an object')
  }
  return value as Record<string, unknown>
}
function text(value: unknown): string {
  if (typeof value !== 'string') throw new Error('evidence field must be a string')
  return value
}
function number(value: unknown): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error('evidence field must be a finite number')
  }
  return value
}
function unit(value: unknown): BillingUnit {
  if (value !== 'USD' && value !== 'AFP') throw new Error('evidence billing unit must be USD or AFP')
  return value
}

/** Decode the external JSON boundary; a TypeScript annotation alone cannot validate JSON. */
export function decodeEvidence(value: unknown): RunnerEvidence {
  const raw = object(value)
  const result: RunnerEvidence = {}
  if (raw.status != null) result.status = text(raw.status)
  if (raw.mode != null) result.mode = text(raw.mode)
  if (Array.isArray(raw.issues)) {
    result.issues = raw.issues.filter((issue: unknown): issue is string => typeof issue === 'string')
  }
  if (raw.artifacts != null) result.artifacts = object(raw.artifacts)
  if (raw.inputs != null) {
    const inputs = object(raw.inputs)
    result.inputs = {}
    for (const key of ['dataset', 'model_manifest', 'corpus', 'code'] as const) {
      if (inputs[key] != null) {
        const hash = object(inputs[key]).sha256
        result.inputs[key] = hash == null ? {} : { sha256: text(hash) }
      }
    }
  }
  if (raw.preflight != null) {
    const preflight = object(raw.preflight)
    result.preflight = {}
    if (preflight.billing_unit != null) result.preflight.billing_unit = unit(preflight.billing_unit)
    if (preflight.call_plan != null) {
      const plan = object(preflight.call_plan)
      result.preflight.call_plan = {
        training_model_calls: number(plan.training_model_calls),
        production_model_calls: number(plan.production_model_calls),
        judge_model_calls: number(plan.judge_model_calls),
        total_model_calls: number(plan.total_model_calls),
      }
    }
    if (preflight.cost_estimates != null) {
      const costs = object(preflight.cost_estimates)
      result.preflight.cost_estimates = {
        billing_unit: unit(costs.billing_unit),
        production_upper_estimate: number(costs.production_upper_estimate),
        evaluation_upper_estimate: number(costs.evaluation_upper_estimate),
        total_upper_estimate: number(costs.total_upper_estimate),
      }
    }
  }
  return result
}
