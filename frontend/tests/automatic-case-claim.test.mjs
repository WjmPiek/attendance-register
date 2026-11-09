import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import React from 'react'
import * as jsxRuntime from 'react/jsx-runtime'
import TestRenderer, { act } from 'react-test-renderer'
import { transformSync } from 'esbuild'
import { allowedClaimBranches } from '../src/utils/claim-permissions.mjs'

const compiled=transformSync(fs.readFileSync(new URL('../src/components/AutomaticCaseClaim.jsx',import.meta.url),'utf8'),{loader:'jsx',format:'cjs',jsx:'automatic'}).code
const preferences={branches:[{id:101,name:'Main'},{id:102,name:'Linked'}],assignment:{branch_id:101},
  options:{grave_service:{enabled:true}},commission_branches:{101:{enabled_types:['grave_service']},102:{enabled_types:['grave_service']}}}

async function mount(result) {
  const calls=[],saved=[]
  const module={exports:{}}
  const request=async(path,options)=>{
    calls.push({path,options})
    if(path.includes('/options/'))return preferences
    if(path.includes('external-branches'))return {branches:[]}
    return result
  }
  const require=name=>{
    if(name==='react')return React
    if(name==='react/jsx-runtime')return jsxRuntime
    if(name==='../api/client')return {apiRequest:request}
    if(name==='../utils/claim-permissions.mjs')return {allowedClaimBranches}
    if(name==='./CommissionCheckboxes')return {commissionLabels:{grave_service:'Grave Service',removals:'Removals'}}
    throw new Error(name)
  }
  new Function('require','module','exports',compiled)(require,module,module.exports)
  let view
  await act(async()=>{view=TestRenderer.create(React.createElement(module.exports.default,{me:{id:11},onSaved:message=>saved.push(message)}))})
  return {view,calls,saved}
}
function fill(view) {
  act(()=>{
    view.root.findByType('select').props.onChange({target:{value:'102'}})
    view.root.findByType('input').props.onChange({target:{value:' MF123 '}})
  })
}
const submit=view=>view.root.findByType('form').props.onSubmit({preventDefault(){}})

test('staff enter only branch and MF number; server chooses commission details',async()=>{
  const {view,calls,saved}=await mount({reference:'MF123',documents_valid:true,created:1,total:'75.00',items:[{category:'grave_service',state:'approved',amount:'75.00'}]})
  assert.equal(view.root.findAllByType('select').length,1)
  assert.equal(view.root.findAllByType('input').length,1)
  fill(view);await act(async()=>{await submit(view)})
  const sent=calls.find(call=>call.path==='/commission/case-claim')
  assert.deepEqual(JSON.parse(sent.options.body),{earning_branch_id:102,reference:'MF123'})
  assert.match(saved[0],/automatically allocated/)
  act(()=>view.unmount())
})
test('missing documents show the reason without navigating away or claiming success',async()=>{
  const {view,saved}=await mount({reference:'MF123',documents_valid:false,created:0,total:'0.00',items:[],notice:'Invoice not fully paid.'})
  fill(view);await act(async()=>{await submit(view)})
  assert.equal(saved.length,0)
  assert.match(JSON.stringify(view.toJSON()),/Invoice not fully paid/)
  assert.match(JSON.stringify(view.toJSON()),/No new commission/)
  act(()=>view.unmount())
})
test('an ineligible removal remains visible while other enabled fees are allocated',async()=>{
  const {view,saved}=await mount({documents_valid:true,created:1,total:'75.00',items:[{category:'grave_service',state:'approved',amount:'75.00'},{category:'removals',state:'blocked',notice:'The claimant is not identified in the Mortuary Book.'}]})
  fill(view);await act(async()=>{await submit(view)})
  assert.equal(saved.length,0)
  assert.match(JSON.stringify(view.toJSON()),/not identified/)
  act(()=>view.unmount())
})
test('repeated MF claims say already recorded instead of reporting a new allocation',async()=>{
  const {view,saved}=await mount({reference:'MF123',documents_valid:true,created:0,total:'0.00',items:[{category:'grave_service',state:'existing',status:'approved',amount:'75.00'}]})
  fill(view);await act(async()=>{await submit(view)})
  assert.match(saved[0],/already recorded/)
  act(()=>view.unmount())
})
