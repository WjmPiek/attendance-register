import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import React from 'react'
import * as jsxRuntime from 'react/jsx-runtime'
import TestRenderer,{act} from 'react-test-renderer'
import {transformSync} from 'esbuild'
import {commissionGroups} from '../src/utils/commission-groups.mjs'

const base={earning_branch_id:1,branch_name:'Northcliff',employee_user_id:11,commission_type:'removals',status:'approved',payment_eligible:true,calculated_amount:'100',reference:'MF1001'}
const rows=[{...base,id:1},{...base,id:2,reference:'MF1002',status:'pending',expected_amount:'50'},
  {...base,id:3,earning_branch_id:2,branch_name:'Rivonia',calculated_amount:'200',reference:'MF2001'}]

test('groups keep branches and categories separate and count every waiting estimate',()=>{
  const groups=commissionGroups([...rows,{...base,id:4,status:'cancelled',calculated_amount:'999'}])
  assert.equal(groups.length,2)
  assert.deepEqual(groups.map(group=>[group.branch,group.approved,group.pending,group.approvedCount,group.pendingCount]),[['Northcliff',100,50,1,1],['Rivonia',200,0,1,0]])
  assert.equal(commissionGroups([...rows,{...base,id:4,status:'cancelled'}],true)[0].rows.length,3)
})

test('claim cards appear only inside the selected expanded branch/category row',async()=>{
  const compiled=transformSync(fs.readFileSync(new URL('../src/components/StaffCommissionOverview.jsx',import.meta.url),'utf8'),{loader:'jsx',format:'cjs',jsx:'automatic'}).code
  const module={exports:{}}
  new Function('require','module','exports',compiled)(name=>{
    if(name==='react')return React
    if(name==='react/jsx-runtime')return jsxRuntime
    if(name==='../utils/useCommissionMonth')return {useCommissionMonth:()=>['2026-11',()=>{}]}
    if(name==='../utils/commission-groups.mjs')return {commissionGroups}
    if(name==='./CommissionCheckboxes')return {commissionLabels:{removals:'Removals'}}
    if(name==='../api/client')return {getCommissionEntries:async()=>({items:rows,pending_imports:[]})}
    throw new Error(name)
  },module,module.exports)
  let view
  await act(async()=>{view=TestRenderer.create(React.createElement(module.exports.default,{employeeId:11,me:{id:1,roles:['FranchiseUser']}}))})
  try {
    assert.equal(view.root.findAllByType('article').length,0)
    assert.deepEqual(view.root.findAllByType('th').map(node=>node.children[0]),['Service branch','Commission category','Approved','Pending estimate'])
    const toggles=()=>view.root.findAllByType('button').filter(node=>node.props['aria-expanded']!==undefined)
    act(()=>toggles()[0].props.onClick())
    assert.equal(view.root.findAllByType('article').length,2)
    assert.deepEqual(view.root.findAllByType('h3').map(node=>node.children[0]),['MF1001','MF1002'])
    assert.equal(toggles()[0].props['aria-expanded'],true)
    act(()=>toggles()[0].props.onClick())
    assert.equal(view.root.findAllByType('article').length,0)
    act(()=>toggles()[1].props.onClick())
    assert.equal(view.root.findAllByType('article').length,1)
    assert.equal(view.root.findByType('h3').children[0],'MF2001')
  } finally {act(()=>view.unmount())}
})
