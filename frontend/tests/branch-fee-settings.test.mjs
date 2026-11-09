import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import React from 'react'
import * as jsxRuntime from 'react/jsx-runtime'
import TestRenderer,{act} from 'react-test-renderer'
import {transformSync} from 'esbuild'

const compiled=transformSync(fs.readFileSync(new URL('../src/components/RemovalSettings.jsx',import.meta.url),'utf8'),{loader:'jsx',format:'cjs',jsx:'automatic'}).code
const week=Array.from({length:6},()=>({start:'08:00',end:'17:00'}))
const defaults={week,rates:{driver_out:'200'},extra_holidays:[]}
async function mount({legacy=false}={}) {
  const calls=[],module={exports:{}}
  const apiRequest=async(path,options)=>{
    calls.push({path,options})
    if(options)return {saved:true}
    if(path.startsWith('/receipt-commissions'))return {settings:{receipt_percentage:'1'}}
    const bid=new URL(path,'https://example.com').searchParams.get('branch_id')
    return {branch_id:legacy?undefined:bid?Number(bid):null,default:defaults,main_default:defaults,branch_rates:bid==='101'?{driver_out:'250'}:bid==='102'?{driver_out:'400'}:{},overrides:{},employees:[{user_id:11,full_name:'Example Staff'}],branches:[{id:101,name:'Northcliff'},{id:102,name:'Rivonia'}]}
  }
  new Function('require','module','exports',compiled)(name=>{
    if(name==='react')return React
    if(name==='react/jsx-runtime')return jsxRuntime
    if(name==='../api/client')return {apiRequest,getCommissionStructures:async()=>[]}
    if(name==='../api/branchContext')return {getStaffBranchId:()=>101}
    if(name.endsWith('.css'))return {}
    throw new Error(name)
  },module,module.exports)
  let view
  await act(async()=>{view=TestRenderer.create(React.createElement(module.exports.default,{}))})
  return {view,calls}
}

test('branch settings use the main-system branch, load each fee independently and save only that branch',async()=>{
  const {view,calls}=await mount()
  try {
    const input=()=>view.root.findByProps({'aria-label':'After-hours removal · Employee'})
    assert.equal(view.root.findAllByType('select')[0].props.value,'101')
    assert.equal(input().props.value,'250')
    await act(async()=>{view.root.findAllByType('select')[0].props.onChange({target:{value:'102'}})})
    assert.equal(input().props.value,'400')
    act(()=>input().props.onChange({target:{value:'450'}}))
    await act(async()=>{await view.root.findByType('form').props.onSubmit({preventDefault(){}})})
    const writes=calls.filter(call=>call.options)
    assert.equal(writes.length,1)
    const body=JSON.parse(writes[0].options.body)
    assert.equal(body.branch_id,102)
    assert.equal(body.employee_user_id,0)
    assert.equal(body.rates.driver_out,'450')
  } finally {view.unmount()}
})

test('clearing a branch fee sends null for inheritance without switching to main defaults',async()=>{
  const {view,calls}=await mount()
  try {
    act(()=>view.root.findByProps({'aria-label':'After-hours removal · Employee'}).props.onChange({target:{value:''}}))
    await act(async()=>{await view.root.findByType('form').props.onSubmit({preventDefault(){}})})
    const body=JSON.parse(calls.find(call=>call.options).options.body)
    assert.equal(body.branch_id,101)
    assert.equal(body.rates.driver_out,null)
  } finally {view.unmount()}
})

test('a backend that does not confirm branch scope cannot expose a branch save form',async()=>{
  const {view,calls}=await mount({legacy:true})
  try {
    assert.equal(view.root.findAllByType('form').length,0)
    assert.match(JSON.stringify(view.toJSON()),/Branch fee settings are updating/)
    assert.equal(calls.filter(call=>call.options).length,0)
  } finally {view.unmount()}
})
