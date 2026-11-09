import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import React from 'react'
import * as jsxRuntime from 'react/jsx-runtime'
import TestRenderer from 'react-test-renderer'
import { transformSync } from 'esbuild'
import { commissionBranchTotals } from '../src/utils/staff-portal.mjs'

const compiled=transformSync(fs.readFileSync(new URL('../src/components/BranchCommissionBreakdown.jsx',import.meta.url),'utf8'),{loader:'jsx',format:'cjs',jsx:'automatic'}).code
const module={exports:{}}
new Function('require','module','exports',compiled)(name=>{
  if(name==='react')return React
  if(name==='react/jsx-runtime')return jsxRuntime
  if(name==='./CommissionCheckboxes')return {commissionLabels:{grave_service:'Grave Service',removals:'Removals'}}
  throw new Error(name)
},module,module.exports)
const Component=module.exports.default

test('branch blocks disclose only MF numbers before their individual commission breakdowns',()=>{
  const base={employee_user_id:24,earning_branch_id:4,branch_name:'Northcliff',reference:'MF111137',commission_type:'grave_service',calculated_amount:'75.00'}
  const [branch]=commissionBranchTotals([{...base,id:1,status:'approved',payment_eligible:true},
    {...base,id:2,status:'pending',reference:'MF111105',commission_type:'removals',estimate_available:false,expected_amount:'0',payment_block_reason:'The claimant is not identified in the Mortuary Book.'}],24)
  const view=TestRenderer.create(React.createElement(Component,{branch}))
  try {
    const blocks=view.root.findAllByType('details').filter(node=>['approved','waiting'].includes(node.props.className))
    assert.equal(blocks.length,2)
    for(const [index,label] of ['Approved','Waiting to be finalised'].entries()) {
      const block=blocks[index]
      assert.equal(block.props.open,undefined)
      const summary=block.findAllByType('summary')[0]
      assert.equal(summary.props['aria-label'],`Northcliff: ${label}`)
      const file=block.findByProps({className:'staff-mf-file'})
      assert.equal(file.props.open,undefined)
      assert.equal(file.findByType('summary').children[0],index===0?'MF111137':'MF111105')
      const lines=file.findAllByType('li')
      assert.equal(lines.length,1)
      assert.match(lines[0].findAllByType('span').map(span=>span.children.join('')).join(' '),index===0?/Grave Service/:/Awaiting calculation/)
      if(index===1)assert.equal(lines[0].findByType('small').children[0],'The claimant is not identified in the Mortuary Book.')
    }
  } finally {view.unmount()}
})

test('empty approved and waiting blocks explain that no MF files are recorded',()=>{
  const view=TestRenderer.create(React.createElement(Component,{branch:{branchName:'Rivonia',approved:0,waiting:0,files:{approved:[],waiting:[]}}}))
  try {assert.equal(view.root.findAllByType('p').filter(node=>node.children.includes('No MF files in this block.')).length,2)} finally {view.unmount()}
})
