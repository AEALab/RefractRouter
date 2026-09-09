/** 边界类型和展示；计数、约束规则与通过判定全部由 Python 负责。 */
import type { JsonSchema } from './contracts.js'

export interface OutputConstraints {
  maxLength: number
  unit: 'unicode-code-points' | 'utf8-bytes'
  countWhitespace: boolean
}
export interface FormatValidation {
  schema_version: 'output-length-check-v1'
  status: 'not-requested' | 'not-evaluated' | 'passed' | 'failed'
  constraints: OutputConstraints | null
  passed: boolean | null
  actual_length: number | null
  output_sha256: string | null
}
function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}
export function decodeOutputConstraints(raw: unknown): OutputConstraints {
  if (!object(raw) || Object.keys(raw).sort().join(',') !== 'countWhitespace,maxLength,unit'
    || typeof raw.maxLength !== 'number' || !Number.isFinite(raw.maxLength)
    || (raw.unit !== 'unicode-code-points' && raw.unit !== 'utf8-bytes')
    || typeof raw.countWhitespace !== 'boolean') throw new Error('invalid outputConstraints fields')
  return { maxLength: raw.maxLength, unit: raw.unit, countWhitespace: raw.countWhitespace }
}
export function decodeFormatValidation(raw: unknown): FormatValidation {
  if (!object(raw) || raw.schema_version !== 'output-length-check-v1'
    || !['not-requested', 'not-evaluated', 'passed', 'failed'].includes(String(raw.status))
    || (raw.passed !== null && typeof raw.passed !== 'boolean')
    || (raw.actual_length !== null && (typeof raw.actual_length !== 'number'
      || !Number.isSafeInteger(raw.actual_length) || raw.actual_length < 0))
    || (raw.output_sha256 !== null && (typeof raw.output_sha256 !== 'string'
      || !/^[a-f0-9]{64}$/.test(raw.output_sha256)))) throw new Error('invalid format validation result')
  return { schema_version: 'output-length-check-v1', status: raw.status as FormatValidation['status'],
    constraints: raw.constraints === null ? null : decodeOutputConstraints(raw.constraints),
    passed: raw.passed as boolean | null, actual_length: raw.actual_length as number | null,
    output_sha256: raw.output_sha256 as string | null }
}
export function formatValidationSummary(value: unknown): string {
  if (value === undefined) return '未提供'
  const check = decodeFormatValidation(value)
  const labels = { 'not-requested': '未设置', 'not-evaluated': '未检查', passed: '通过', failed: '未通过' }
  if (check.actual_length === null || check.constraints === null) return labels[check.status]
  return `${labels[check.status]}，${check.actual_length}/${check.constraints.maxLength} `
    + `${check.constraints.unit === 'utf8-bytes' ? 'UTF-8 字节' : 'Unicode 码点'}`
    + `（${check.constraints.countWhitespace ? '计入' : '不计'}空白）`
}
export const OUTPUT_CONSTRAINTS_SCHEMA: JsonSchema = {
  type: 'object', additionalProperties: false, required: ['maxLength', 'unit', 'countWhitespace'],
  properties: { maxLength: { type: 'number' }, unit: { type: 'string', enum: ['unicode-code-points', 'utf8-bytes'] },
    countWhitespace: { type: 'boolean' } },
}
export const FORMAT_VALIDATION_SCHEMA: JsonSchema = {
  type: 'object', additionalProperties: false,
  required: ['schema_version', 'status', 'constraints', 'passed', 'actual_length', 'output_sha256'],
  properties: {
    schema_version: { type: 'string', enum: ['output-length-check-v1'] },
    status: { type: 'string', enum: ['not-requested', 'not-evaluated', 'passed', 'failed'] },
    constraints: { oneOf: [OUTPUT_CONSTRAINTS_SCHEMA, { type: 'null' }] },
    passed: { oneOf: [{ type: 'boolean' }, { type: 'null' }] },
    actual_length: { oneOf: [{ type: 'number' }, { type: 'null' }] },
    output_sha256: { oneOf: [{ type: 'string' }, { type: 'null' }] },
  },
}
