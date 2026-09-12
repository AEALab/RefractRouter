/** 把浏览器半边打包成 DSH client 模块格式（lazy-CJS factory 注册）。
 * 官方 clientBundle 预设未发布为包，此处按 dsh-client-modules 的格式约定复刻：
 * bundle 只 REGISTERS factory，React 由 shell 外部化提供。
 */
import { build } from 'esbuild'
import { mkdir, readFile, writeFile } from 'node:fs/promises'

const pkg = JSON.parse(await readFile(new URL('../package.json', import.meta.url), 'utf8'))

const result = await build({
  entryPoints: ['src/client/index.tsx'],
  bundle: true,
  format: 'cjs',
  platform: 'browser',
  target: 'es2023',
  external: ['react', 'react/jsx-runtime'],
  jsx: 'automatic',
  write: false,
  sourcemap: false,
  minify: false,
  legalComments: 'none',
  logLevel: 'warning',
})

const code = result.outputFiles[0].text
const indented = code.split('\n').map(line => (line === '' ? '' : '\t\t' + line)).join('\n')
const bundle = [
  'window.__ModuleLoader__.load({',
  '\tid: ' + JSON.stringify(pkg.name) + ',',
  '\tfactory: (require) => {',
  '\t\tvar module = { exports: {} };',
  '\t\tvar exports = module.exports;',
  '\t\tObject.defineProperty(exports, Symbol.toStringTag, { value: "Module" });',
  indented,
  '\t\treturn module.exports;',
  '\t}',
  '});',
  '',
].join('\n')

await mkdir(new URL('../dist/', import.meta.url), { recursive: true })
await writeFile(new URL('../dist/client.js', import.meta.url), bundle)
