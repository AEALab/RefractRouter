// 有限实验的宿主适配器：只读取现有配置并转发模型调用，不实现选模或账本。
import {readFileSync, appendFileSync} from 'node:fs'
import {homedir} from 'node:os'
import {createInterface} from 'node:readline'
import {pathToFileURL} from 'node:url'
import {hostDiagnostic} from './applicability_audit.ts'
import {createHash} from 'node:crypto'
import {installResponsesWireAudit} from './responses_wire_audit.ts'

if (process.env.REFRACT_APPLICABILITY_WIRE_AUDIT) {
  installResponsesWireAudit(process.env.REFRACT_APPLICABILITY_WIRE_AUDIT)
}

const moduleRoot = process.env.REFRACT_DSH_MODULE_ROOT
if (!moduleRoot) throw new Error('必须明确提供已安装 DSH 的依赖目录')
const load = (name: string) => import(pathToFileURL(`${moduleRoot}/@deepseek-ai/${name}/lib/index.js`).href)
const runtimeFiles = ['@deepseek-ai/dsh-llm-pi-ai/package.json', '@deepseek-ai/dsh-llm-pi-ai/lib/index.js',
  '@deepseek-ai/dsh-llm-deepseek/package.json', '@deepseek-ai/dsh-llm-deepseek/lib/index.js',
  '@earendil-works/pi-ai/package.json', '@earendil-works/pi-ai/dist/api/openai-responses-shared.js']
const runtimeHashes = Object.fromEntries(runtimeFiles.map(path => [path,
  createHash('sha256').update(readFileSync(`${moduleRoot}/${path}`)).digest('hex')]))
const {parse} = await import(pathToFileURL(`${moduleRoot}/yaml/dist/index.js`).href)
const settings = parse(readFileSync(`${homedir()}/.dsh/settings.yaml`, 'utf8'))
const secrets = parse(readFileSync(`${homedir()}/.dsh/.credentials.yaml`, 'utf8'))
const {callDshLlm, pumpDshBridge} = await import(pathToFileURL(`${process.cwd()}/validation/dsh/plugin/dist/index.js`).href)
const {apply} = await load('dsh-llm-pi-ai')
let adapter: any
const credentials = {resolve: async (ref: string) => ({value: secrets.refs[ref]}),
  readRecord: async () => undefined, listRecords: async () => []}
// 实验快照的传输重试固定为零；不写回用户配置。
const piSettings = structuredClone(settings['llm-pi-ai'])
for (const provider of Object.values(piSettings.providers) as any[]) {
  provider.retryPolicy = {mode: 'normal', maxRetries: 0}
}
apply({get: (name: string) => name === 'credentials' ? credentials : undefined,
  inject: () => {}, logger: {warn: () => {}},
  llm: {registerConfigurableProviders: () => ({replace: () => {}}),
    registerModelDiscovery: () => {}, registerAdapter: (_routes: any, value: any) => {
      adapter = value; return {replace: () => {}}
    }}}, piSettings)

const {DeepSeekAdapter, resolveAdapterOptions} = await load('dsh-llm-deepseek')
const official = resolveAdapterOptions({baseURL: 'https://api.deepseek.com', maxTokens: 8192,
  retryPolicy: {mode: 'normal', maxRetries: 0}})
const deepseek = new DeepSeekAdapter({options: () => official,
  resolveApiKey: async () => secrets.refs.DEEPSEEK_API_KEY, resolveUserId: () => undefined,
  prepareExtensions: async () => ({fields: {}, accept: async () => {}})})
// 原实验仍冻结 8192；新批次明确请求目录容量，不写回宿主设置。
const nativeOfficial = resolveAdapterOptions({baseURL: 'https://api.deepseek.com',
  retryPolicy: {mode: 'normal', maxRetries: 0}})
const nativeDeepseek = new DeepSeekAdapter({options: () => nativeOfficial,
  resolveApiKey: async () => secrets.refs.DEEPSEEK_API_KEY, resolveUserId: () => undefined,
  prepareExtensions: async () => ({fields: {}, accept: async () => {}})})

if(process.env.REFRACT_AUTOMATIC_MULTIPLEX==='1'){
  // 只验证宿主转发：并发派发、模型选择和费用均由 Python 调用方控制。
  const routes=settings.refractagent.dshModelPool.routes.filter((r:any)=>r.enabled!==false)
    .map((r:any)=>({provider:r.provider,model:r.model}))
  const handle={stdin:process.stdout,stdout:process.stdin,
    done:Promise.resolve({exitCode:0,signal:null}),waitForExit:async()=>{},collected:{}}
  await pumpDshBridge({llm:{async *stream(options:any){
    const current=options.provider==='deepseek-official'?nativeDeepseek:adapter
    yield* current.stream(options)
  }}},handle,new AbortController().signal,routes,16*1024*1024)
}else for await (const line of createInterface({input: process.stdin})) {
  const request = JSON.parse(line)
  let result: any
  if (request.op === 'catalog') {
    if (request.outputMode !== undefined && request.outputMode !== 'model-capacity') throw new Error('未知输出容量模式')
    if (request.flashReasoning !== undefined && !['high','low'].includes(request.flashReasoning)) throw new Error('未知实验推理档位')
    const pool = structuredClone(settings.refractagent.dshModelPool)
    if (request.flashReasoning !== undefined) {
      const flash = pool.routes.find((r: any) => r.provider === 'ark' && r.model === 'deepseek-v4-flash' && r.enabled)
      if (!flash) throw new Error('实验缺少 Ark Flash')
      flash.reasoningEffort = request.flashReasoning
    }
    const routes = []
    for (const row of pool.routes.filter((r: any) => r.enabled)) {
      const current = row.provider === 'deepseek-official'
        ? (request.outputMode === 'model-capacity' ? nativeDeepseek : deepseek) : adapter
      const model = await current.resolveModel(row.provider, row.model)
      routes.push({provider: row.provider, model: row.model,
        contextWindow: model.context.contextWindow,
        maxOutputTokens: request.outputMode === 'model-capacity' ? model.defaultMaxTokens : 8192,
        providerBaseURL: row.provider === 'deepseek-official' ? 'https://api.deepseek.com'
          : piSettings.providers[row.provider].baseURL, reasoning: model.reasoning})
    }
    result = {pool, routes, runtimeHashes,
      ...(request.outputMode ? {catalogRequest: request} : {})}
  } else {
    const started = performance.now()
    const chunks: Record<string, number> = {}
    const lengths = {delta:0, completedText:0, reasoning:0}
    result = await callDshLlm({llm: {async *stream(options: any) {
      for await (const chunk of (options.provider === 'deepseek-official' ? deepseek : adapter).stream(options)) {
        chunks[chunk.type] = (chunks[chunk.type] ?? 0) + 1
        if (chunk.type === 'text-delta') lengths.delta += chunk.text.length
        if (chunk.type === 'reasoning-delta') lengths.reasoning += (chunk.text ?? '').length
        if (chunk.type === 'block-end' && chunk.block?.type === 'text') lengths.completedText += (chunk.block.text ?? '').length
        yield chunk
      }
    }}}, request)
    const auditPath = process.env.REFRACT_APPLICABILITY_AUDIT
    if (auditPath) appendFileSync(auditPath,
      JSON.stringify({...hostDiagnostic(request, result, secrets.refs, performance.now() - started),
        chunks, lengths, bridgeContentChars:result.content?.length ?? 0}) + '\n',
      {mode: 0o600})
  }
  process.stdout.write(JSON.stringify(result) + '\n')
}
