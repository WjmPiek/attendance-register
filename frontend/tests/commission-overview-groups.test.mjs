import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import React from 'react'
import * as jsxRuntime from 'react/jsx-runtime'
import TestRenderer,{act} from 'react-test-renderer'
import {transformSync} from 'esbuild'
import {commissionGroups,commissionBranches,commissionMfFiles,readCommissionView} from '../src/utils/commission-groups.mjs'

const base={earning_branch_id:1,branch_name:'Northcliff',employee_user_id:11,commission_type:'removals',status:'approved',payment_eligible:true,calculated_amount:'100',reference:'MF1001'}
const rows=[{...base,id:1},{...base,id:2,reference:'MF1002',status:'pending',expected_amount:'50'},
  {...base,id:3,earning_branch_id:2,branch_name:'Rivonia',calculated_amount:'200',reference:'MF2001'},
  {...base,id:4,commission_type:'grave_service',calculated_amount:'25',reference:'MF1003'}]
const key=JSON.stringify([1,'removals'])
const detailUrl=person=>`https://attendance.example/?commission_view_person=${person}&commission_view_month=2026-11&commission_view_group=${encodeURIComponent(key)}`

function browser(href) {
  let location=new URL(href),stack=[location.href],index=0
  const listeners=new Set()
  return {location:{get href(){return location.href},get search(){return location.search}},
    history:{pushState:(_a,_b,url)=>{location=new URL(url);stack=stack.slice(0,index+1);stack.push(location.href);index++},replaceState:(_a,_b,url)=>{location=new URL(url);stack[index]=location.href},back:()=>{if(index){location=new URL(stack[--index]);for(const listener of listeners)listener()}}},
    addEventListener:(name,fn)=>{if(name==='popstate')listeners.add(fn)},removeEventListener:(name,fn)=>listeners.delete(fn),scrollTo:()=>{}}
}

async function mount(url='https://attendance.example/',items=rows) {
  const modules={},reviews=[],requests=[]
  function compile(file) {
    const code=transformSync(fs.readFileSync(new URL(`../src/components/${file}.jsx`,import.meta.url),'utf8'),{loader:'jsx',format:'cjs',jsx:'automatic'}).code
    const module={exports:{}}
    new Function('require','module','exports',code)(name=>{
      if(name==='react')return React
      if(name==='react/jsx-runtime')return jsxRuntime
      if(name==='../utils/useCommissionMonth')return {useCommissionMonth:()=>React.useState('2026-11')}
      if(name==='../utils/commission-groups.mjs')return {commissionGroups,commissionBranches,commissionMfFiles,readCommissionView}
      if(name==='./CommissionClaimDetails')return modules.cards
      if(name==='./CommissionMfDocuments')return modules.documents
      if(name==='./CommissionCheckboxes')return {commissionLabels:{removals:'Removals',grave_service:'Grave Service'}}
      if(name==='../api/client')return {getCommissionEntries:async()=>({items,pending_imports:[]}),apiRequest:async path=>{requests.push(path);const ref=new URL(path,'https://example.com').searchParams.get('reference');return {case:{ready:false,reason:'Waiting for documents'},documents:[{id:10,kind:'invoice',original_available:false,record:{reference:`MF${ref}`,invoice_number:'INV1'}}]}}}
      throw new Error(name)
    },module,module.exports)
    return module.exports.default
  }
  modules.cards=compile('CommissionClaimDetails')
  modules.documents=compile('CommissionMfDocuments')
  const Component=compile('StaffCommissionOverview')
  global.window=browser(url)
  let view
  await act(async()=>{view=TestRenderer.create(React.createElement(Component,{employeeId:11,me:{id:1,roles:['FranchiseUser']},onReview:row=>reviews.push(row.id)}))})
  return {view,reviews,requests,cleanup:()=>{act(()=>view.unmount());delete global.window}}
}

test('branches appear once and retain independently grouped categories and waiting estimates',()=>{
  const groups=commissionGroups([...rows,{...base,id:5,status:'cancelled',calculated_amount:'999'}])
  const branches=commissionBranches(groups)
  assert.deepEqual(branches.map(branch=>[branch.name,branch.groups.length]),[['Northcliff',2],['Rivonia',1]])
  const removal=groups.find(group=>group.key===key)
  assert.deepEqual([removal.approved,removal.pending,removal.approvedCount,removal.pendingCount],[100,50,1,1])
  assert.equal(commissionGroups([...rows,{...base,id:5,status:'cancelled'}],true).find(group=>group.key===key).rows.length,3)
})

test('branch and type lead to an MF list, then each MF opens its own document page',async()=>{
  const ui=await mount(),{view}=ui
  try {
    assert.equal(view.root.findAllByType('table').length,0)
    assert.equal(view.root.findAllByType('article').length,0)
    const branches=()=>view.root.findAllByProps({className:'commission-branch-toggle'})
    assert.equal(branches().length,2)
    assert.equal(view.root.findAllByProps({className:'commission-type-link'}).length,0)
    act(()=>branches()[0].props.onClick())
    const types=view.root.findAllByProps({className:'commission-type-link'})
    assert.equal(types.length,2)
    act(()=>types.find(button=>button.children.join('').includes('Removals')).props.onClick())
    assert.match(window.location.search,/commission_view_group=/)
    assert.equal(view.root.findAllByProps({className:'commission-branch-toggle'}).length,0)
    assert.equal(view.root.findAllByType('article').length,0)
    assert.deepEqual(view.root.findAllByProps({className:'commission-mf-link'}).map(node=>node.children.join('')),['MF1001 →','MF1002 →'])
    assert.match(view.root.findByType('h2').children[0],/Northcliff.*Removals/)
    await act(async()=>{view.root.findAllByProps({className:'commission-mf-link'})[1].props.onClick()})
    assert.match(window.location.search,/commission_view_mf=1002/)
    assert.match(view.root.findByType('h2').children[0],/Northcliff.*MF1002/)
    assert.match(ui.requests[0],/reference=1002/)
    assert.match(ui.requests[0],/earning_branch_id=1/)
    assert.equal(view.root.findByProps({className:'claim-status-list'}).findByType('h3').children[0],'MF1002')
    act(()=>view.root.findAllByType('button').find(button=>button.children.join('').includes('Review or correct')).props.onClick())
    assert.deepEqual(ui.reviews,[2])
    act(()=>view.root.findAllByType('button').find(button=>button.children.join('').includes('Back to MF files')).props.onClick())
    assert.equal(view.root.findAllByProps({className:'commission-mf-link'}).length,2)
    act(()=>window.history.back())
    assert.equal(branches().length,2)
    assert.equal(view.root.findAllByType('article').length,0)
    assert.equal(branches()[0].props['aria-expanded'],true)
    act(()=>branches()[1].props.onClick())
    act(()=>view.root.findAllByProps({className:'commission-type-link'}).filter(button=>button.children.join('').includes('Removals'))[1].props.onClick())
    assert.equal(view.root.findAllByProps({className:'commission-mf-link'})[0].children.join(''),'MF2001 →')
    act(()=>view.root.findAllByType('button').find(button=>button.children.join('').includes('Back to branches')).props.onClick())
    assert.equal(branches().length,2)
  } finally {ui.cleanup()}
})

test('refresh opens the same category, while another staff scope cannot reuse that detail route',async()=>{
  let ui=await mount(detailUrl(11))
  try {
    assert.equal(ui.view.root.findAllByProps({className:'commission-mf-link'}).length,2)
    act(()=>ui.view.root.findAllByType('button').find(button=>button.children.join('').includes('Back to branches')).props.onClick())
    assert.equal(ui.view.root.findAllByProps({className:'commission-branch-toggle'}).length,2)
  } finally {ui.cleanup()}
  ui=await mount(detailUrl(12))
  try {assert.equal(ui.view.root.findAllByType('article').length,0);assert.equal(ui.view.root.findAllByProps({className:'commission-branch-toggle'}).length,2)} finally {ui.cleanup()}
})

test('MF aliases collapse to one link and refreshed MF pages keep their branch and file',async()=>{
  const files=commissionMfFiles([rows[0],{...rows[0],id:9,reference:' 1001 / Invoice 466 '},rows[1]])
  assert.deepEqual(files.map(file=>file.reference),['MF1001','MF1002'])
  assert.equal(files[0].rows.length,2)
  const ui=await mount(detailUrl(11)+'&commission_view_mf=1001')
  try {
    assert.match(ui.view.root.findByType('h2').children[0],/Northcliff.*MF1001/)
    assert.match(ui.requests[0],/reference=1001/)
    act(()=>ui.view.root.findAllByType('button').find(button=>button.children.join('').includes('Back to MF files')).props.onClick())
    assert.equal(ui.view.root.findAllByProps({className:'commission-mf-link'}).length,2)
    assert.doesNotMatch(window.location.search,/commission_view_mf=/)
  } finally {ui.cleanup()}
})

test('removed or unavailable categories show an empty detail page without stale claims',async()=>{
  const ui=await mount(detailUrl(11),[])
  try {assert.equal(ui.view.root.findAllByType('article').length,0);assert.match(JSON.stringify(ui.view.toJSON()),/No commissions are available/)} finally {ui.cleanup()}
})
