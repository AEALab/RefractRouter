import type { ToolSchema } from './native-tools.js'
import type { Readable, Writable } from 'node:stream'
import type { FormatValidation } from './output-constraints.js'

/** The host surface consumed by this bundle, matched to DSH 0.1.5-rc.1.
 * These structural ports keep DSH supplied by the host, with no runtime npm dependencies.
 * Changes must also pass the clean-profile lifecycle and service contract tests.
 */
export type BillingUnit = 'USD' | 'CNY' | 'AFP'
export type SelectionPolicy = 'all-candidates-required-v1' | 'exclude-known-contract-rejections-v2'
export type Phase = 'dry-run' | 'pilot' | 'final' | 'contract-replay' | 'execution-modes' | 'k3-baseline'
export type SandboxMode = 'read-only' | 'workspace-write' | 'danger-full-access'
export type SandboxEnforcement = 'full' | 'partial'

export interface PluginConfig {
  allowPaidRuns: boolean
  maxProductionCost: number
  maxEvaluationCost: number
  billingUnit: BillingUnit
  maxRetries: number
  uvExecutable: string
  uvCacheDir: string
  runnerPath: string
  taskProfilePath: string
  datasetPath: string
  manifestPath: string
  credentialEnv: string
  timeoutMs: number
  processGraceMs: number
  outputCaptureBytes: number
  maxEvidenceBytes: number
}

export interface ToolArguments {
  phase: Phase
  repeats?: number
  stage?: 'baseline' | 'resume' | 'prepare' | 'compose'
  inputDir?: string
  reviewsPath?: string
  selectionPolicy?: SelectionPolicy
  executePaidRun?: boolean
  maxProductionCost?: number
  maxEvaluationCost?: number
}

export type ValidationRequest = { phase: Phase; repeats: number; selectionPolicy: SelectionPolicy; stage?: 'baseline' | 'resume' | 'prepare' | 'compose'; inputDir?: string; reviewsPath?: string } & (
  { paid: false } | { paid: true; productionLimit: number; evaluationLimit: number }
)

export interface ToolExecution {
  signal: AbortSignal
  agent?: { session: { header: { cwd?: string } } }
}

export interface ProcessOutcome { exitCode: number | null; signal: string | null }
export interface CapturedOutput { text: string; lossy: boolean }
export interface OutputReader { readFrom(offset: number): CapturedOutput }
export interface SpawnSpec {
  argv: string[]
  cwd: string
  env: Record<string, string>
  stdio: {
    stdin: 'pipe' | 'ignore'
    stdout: 'pipe' | { maxBytes: number }
    stderr: { maxBytes: number }
  }
  graceMs: number
  signal: AbortSignal
}
export interface ProcessHandle {
  stdin?: Writable
  stdout?: Readable
  done: Promise<ProcessOutcome>
  waitForExit(): Promise<unknown>
  terminate?(): void
  collected: { stdout?: OutputReader; stderr?: OutputReader }
}
export interface SandboxPolicy { mode: SandboxMode; workspaceRoot: string }
export interface ModelRoute { provider: string; model: string }

export interface LlmOptions extends ModelRoute {
  messages: Array<{
    readonly id: string
    readonly role: 'user' | 'assistant'
    readonly content: readonly { readonly type: string; readonly text?: string; readonly [key: string]: unknown }[]
    readonly source: { readonly kind: string; readonly [key: string]: unknown }
  }>
  tools?: ToolSchema[]
  system?: string
  temperature: number
  maxTokens: number
  signal: AbortSignal
  reasoningEffort?: string
}
export interface TokenUsage {
  inputTokens?: number
  outputTokens?: number
  cacheReadTokens?: number
  cacheWriteTokens?: number
  reasoningTokens?: number
}
export interface FinishChunk {
  type: 'finish'
  reason?: {
    kind: string
    failure?: { code?: string; message?: string; requestId?: string }
  }
  replayState?: { response?: unknown }
}
export type StreamChunk =
  | { type: 'text-delta'; text: string; index?: number }
  | { type: 'usage'; usage?: TokenUsage }
  | FinishChunk
  | { type: 'block-start' | 'block-end' | 'reasoning-delta' | 'tool-call-delta'; index?: number; id?: string; name?: string; argumentsDelta?: string; block?: { type: string; id?: string; name?: string; arguments?: string } }
export interface LlmService {
  stream(options: LlmOptions): AsyncIterable<StreamChunk>
  listProviders(): Array<{ id: string; name?: string }>
  listModels?(provider: string): Promise<Array<{ id: string; name?: string; description?: string }>>
  providerRetryPolicy(provider: string): { mode: string; maxRetries?: number }
  resolveModelInfo(provider: string, model: string): Promise<unknown>
  registerModelDiscovery?(settingsNs: string, discover: (request: {
    provider?: string; baseURL?: string; api?: string; apiKey?: string
  }, signal?: AbortSignal) => Promise<readonly {
    id: string; name?: string; contextWindow?: number; maxTokens?: number
  }[]>): () => void
}
export interface BridgeResponseBase { protocol: string; type: 'response'; id: string }
export type BridgeResponse = BridgeResponseBase & (
  | { ok: true; content: string; tool_calls?: unknown[]; replay_state?: unknown; usage: {
      input_tokens: number; output_tokens: number
      cached_input_tokens: number; reasoning_tokens: number
    }; finish_reason?: string; request_id?: string }
  | { ok: false; failure_type: string; message: string; request_id?: string }
)

export interface TaskSummary {
  executionMode: 'serial' | 'bounded-parallel'
  maxConcurrency: number
  peakActiveNodes: number | null
  predictedLatencyMs: number | null
  status: string
  mode: string
  planOrigin: string
  nodes: Array<{ nodeId: string; nodeType: string; parents: string[]; modelId: string }>
  qualityScore: number | null
  evaluationPassed: boolean | null
  generationStatus?: string
  formatValidation?: FormatValidation
  outputPreview: string
  resultPath: string
  productionCost: number
  evaluationCost: number
  unconfirmedCost: number
  costIsSimulated: boolean
  wallTimeMs: number
}

export interface ValidationResult extends ProcessOutcome {
  task?: TaskSummary
  status: 'pass' | 'fail'
  mode: 'preflight' | 'paid'
  phase: Phase
  timedOut: boolean
  aborted: boolean
  evidencePath: string
  outputDir: string
  credentialConfigured: boolean
  modelProviderConfigured: boolean
  billingUnit: BillingUnit
  sandboxMode: SandboxMode
  sandboxEnforcement?: SandboxEnforcement
  issues: string[]
  callPlan?: {
    trainingModelCalls: number; productionModelCalls: number
    judgeModelCalls: number; totalModelCalls: number
  }
  costEstimate?: { billingUnit: BillingUnit; production: number; evaluation: number; total: number }
  inputHashes: { dataset: string; manifest: string; corpus: string; code: string }
  artifactHashes: Array<{ artifact: string; sha256: string }>
  stdoutTail?: string
  stderrTail?: string
}
export type EvidenceFallback = Omit<ValidationResult,
  'status' | 'mode' | 'callPlan' | 'costEstimate' | 'inputHashes' | 'artifactHashes'
> & { stdoutTail: string; stderrTail: string }

export interface JsonSchema {
  type?: string
  additionalProperties?: boolean
  required?: string[]
  properties?: Record<string, JsonSchema>
  enum?: string[]
  oneOf?: JsonSchema[]
  items?: JsonSchema
  description?: string
}
export interface ValidationTool {
  name: string
  description: string
  parameters: JsonSchema
  output: {
    schema: JsonSchema
    render(args: ToolArguments, value: ValidationResult): Array<{ type: 'text'; text: string }>
  }
  // Host input is untrusted even when a caller is type checked.
  execute(args: unknown, exec: ToolExecution): Promise<ValidationResult>
}
export interface DshContext {
  tools: { register(tool: ValidationTool): void }
  credentials: {
    describe(reference: string): Promise<{ configured: boolean }>
    resolve(reference: string): Promise<{ value: string } | undefined>
  }
  llm: LlmService
  sandboxPolicy: { resolve(options: { session?: { header: { cwd?: string } } }): SandboxPolicy }
  sandbox: { confine(argv: string[], policy: SandboxPolicy): {
    argv: string[]; enforcement: SandboxEnforcement
  } }
  subprocess: {
    resolveExecutable(command: string, env: Record<string, string>, signal: AbortSignal): Promise<string>
    spawn(spec: SpawnSpec): ProcessHandle
  }
}
