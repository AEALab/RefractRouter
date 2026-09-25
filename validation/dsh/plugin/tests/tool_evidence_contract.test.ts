import assert from 'node:assert/strict'
import test from 'node:test'
import { ToolEvidenceCapture } from '../dist/tool-evidence.js'

test('DSH 规范 Bash 结果作为宿主事实进入下一轮事件',()=>{
  const capture=new ToolEvidenceCapture()
  const agent={session:{header:{id:'session-a'}}}
  capture.observe({callId:'call-a',name:'bash',agent},{isError:false,value:{
    kind:'foreground',exitCode:7,signal:null,timedOut:false,aborted:false,
    sandbox:{mode:'workspace-write',denied:false,runnerFailed:false}}})
  const events=capture.enrich('session-a',[{type:'tool/result',data:{message:{
    source:{kind:'tool',callId:'call-a'},content:[]}}}])
  assert.deepEqual(events[0]?.data.hostResult,{exitCode:7,signal:null,timedOut:false,aborted:false,
    sandbox:{mode:'workspace-write',denied:false,runnerFailed:false}})
})

test('不采信渲染正文或其他会话的结果',()=>{
  const capture=new ToolEvidenceCapture()
  const agent={session:{header:{id:'session-a'}}}
  capture.observe({callId:'call-a',name:'bash',agent},{isError:false,value:{
    kind:'foreground',exitCode:0,signal:null,timedOut:false,aborted:false}})
  const rendered={type:'tool/result',data:{message:{source:{kind:'tool',callId:'missing'},
    content:[{type:'text',text:'[exit code: 7]'}]}}}
  assert.equal(capture.enrich('session-a',[rendered])[0]?.data.hostResult,undefined)
  assert.equal(capture.enrich('session-b',[rendered])[0]?.data.hostResult,undefined)
})
