import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import React from 'react'
import * as jsxRuntime from 'react/jsx-runtime'
import TestRenderer,{act} from 'react-test-renderer'
import {transformSync} from 'esbuild'

const code=transformSync(fs.readFileSync(new URL('../src/components/CommissionMfDocuments.jsx',import.meta.url),'utf8'),{loader:'jsx',format:'cjs',jsx:'automatic'}).code
async function mount({empty=false}={}) {
  const calls=[],module={exports:{}}
  new Function('require','module','exports',code)(name=>{
    if(name==='react')return React
    if(name==='react/jsx-runtime')return jsxRuntime
    if(name==='../api/client')return {apiRequest:async path=>{
      calls.push(path);const ref=new URL(path,'https://example.com').searchParams.get('reference')
      return {case:{ready:!empty,reason:empty?'Matching documents are missing.':'Documents match.'},documents:empty?[]:['mortuary','invoice','receipt'].map((kind,index)=>({id:index+1,kind,original_available:true,record:{reference:`MF${ref}`,invoice_number:kind==='invoice'?'1321':null,receipt_number:kind==='receipt'?'1502':null}}))}
    },apiBlob:async path=>{calls.push(path);return new Blob(['%PDF sample'],{type:'application/pdf'})}}
    throw new Error(name)
  },module,module.exports)
  const Component=module.exports.default
  const props={branchId:4,reference:'111137',personId:24,category:'invoice_commission'}
  let view
  await act(async()=>{view=TestRenderer.create(React.createElement(Component,props))})
  return {view,calls,change:next=>act(async()=>{view.update(React.createElement(Component,{...props,...next}))}),cleanup:()=>act(()=>view.unmount())}
}

test('MF page lists all imported kinds and opens the scoped PDF without correction controls',async()=>{
  const ui=await mount()
  try {
    assert.deepEqual(ui.view.root.findAllByType('h4').map(node=>node.children[0]),['Mortuary Book','MF Invoice','MF File Receipts'])
    const buttons=()=>ui.view.root.findAllByType('button')
    assert.equal(buttons().filter(button=>button.children.join('').includes('View PDF')).length,3)
    assert.equal(buttons().filter(button=>/Delete|Restore|Upload/.test(button.children.join(''))).length,0)
    await act(async()=>{await buttons().find(button=>button.children.join('')==='View PDF').props.onClick()})
    assert.equal(ui.view.root.findAllByType('iframe').length,1)
    assert.match(ui.calls[1],/case-documents\/1\/file/)
    assert.match(ui.calls[1],/earning_branch_id=4/)
    assert.match(ui.calls[1],/reference=111137/)
    await ui.change({branchId:11,reference:'111105'})
    assert.equal(ui.view.root.findAllByType('iframe').length,0)
    assert.match(ui.calls.at(-1),/earning_branch_id=11/)
    assert.match(ui.calls.at(-1),/reference=111105/)
    assert.doesNotMatch(JSON.stringify(ui.view.toJSON()),/MF111137/)
  } finally {ui.cleanup()}
})

test('an MF claim without uploads shows the three missing document types without blocking',async()=>{
  const ui=await mount({empty:true})
  try {
    assert.equal(ui.view.root.findAllByType('p').filter(node=>node.children.join('')==='Not imported yet.').length,3)
    assert.equal(ui.view.root.findAllByType('iframe').length,0)
    assert.equal(ui.view.root.findAllByType('button').length,0)
  } finally {ui.cleanup()}
})
