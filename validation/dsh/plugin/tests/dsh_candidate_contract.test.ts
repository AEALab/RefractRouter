import assert from 'node:assert/strict'
import test from 'node:test'
import { dshCandidate } from '../dist/dsh-candidate.js'
import { readFileSync } from 'node:fs'
const fixtures=JSON.parse(readFileSync('src/dsh-assembly-fixtures.json','utf8'))

test('规范候选与固定原生SDK的组装结果逐项一致',()=>{
  assert.equal(fixtures.package,'@deepseek-ai/dsh-llm')
  for(const fixture of fixtures.fixtures)assert.deepEqual(dshCandidate(fixture.chunks,fixture.finish),fixture.expected,fixture.name)
})
