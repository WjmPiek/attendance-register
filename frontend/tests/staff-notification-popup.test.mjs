import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import React from 'react'
import * as jsxRuntime from 'react/jsx-runtime'
import TestRenderer, { act } from 'react-test-renderer'
import { transformSync } from 'esbuild'
import { unreadStaffNotifications } from '../src/utils/staff-portal.mjs'

const compiled=transformSync(fs.readFileSync(new URL('../src/components/StaffNotificationPopup.jsx',import.meta.url),'utf8'),{loader:'jsx',format:'cjs',jsx:'automatic'}).code
const reminder=id=>({id,recipient_user_id:24,subject:'Document uploads required',message:'MF 111137: Upload the matching documents.'})
async function mount(items,{paused=false,failId}={}) {
  const acknowledged=[],module={exports:{}}
  let poll
  const require=name=>{
    if(name==='react')return React
    if(name==='react/jsx-runtime')return jsxRuntime
    if(name==='../api/client')return {getNotifications:async()=>items,markNotificationRead:async id=>{if(id===failId)throw new Error('offline');acknowledged.push(id)}}
    if(name==='../utils/staff-portal.mjs')return {unreadStaffNotifications}
    throw new Error(name)
  }
  global.window={setInterval:callback=>{poll=callback;return 1},clearInterval:()=>{}}
  new Function('require','module','exports',compiled)(require,module,module.exports)
  let view
  await act(async()=>{view=TestRenderer.create(React.createElement(module.exports.default,{me:{id:24},paused}))})
  return {view,acknowledged,poll:()=>act(async()=>{await poll()}),cleanup:()=>{act(()=>view.unmount());delete global.window}}
}

test('eight upload reminders become one inline notice and dismiss together without reappearing on poll',async()=>{
  const ui=await mount(Array.from({length:8},(_,index)=>reminder(index+1)))
  try {
    assert.equal(ui.view.root.findAllByProps({role:'alertdialog'}).length,0)
    assert.equal(ui.view.root.findAllByType('aside').length,1)
    assert.match(JSON.stringify(ui.view.toJSON()),/continue using the system/)
    await act(async()=>{await ui.view.root.findByType('button').props.onClick()})
    assert.deepEqual(ui.acknowledged,[1,2,3,4,5,6,7,8])
    await ui.poll()
    assert.equal(ui.view.root.findAllByType('aside').length,0)
  } finally {ui.cleanup()}
})

test('failed acknowledgements and other personal updates stay inline without blocking navigation',async()=>{
  const ui=await mount([reminder(1),reminder(2),{id:3,recipient_user_id:24,subject:'Leave approved'},{...reminder(4),recipient_user_id:99}],{failId:2})
  try {
    assert.equal(ui.view.root.findAllByProps({role:'alertdialog'}).length,0)
    await act(async()=>{await ui.view.root.findByProps({'aria-label':'Commission document reminders'}).findByType('button').props.onClick()})
    assert.deepEqual(ui.acknowledged,[1])
    assert.match(JSON.stringify(ui.view.toJSON()),/continue and try again later/)
    await act(async()=>{await ui.view.root.findByProps({'aria-label':'Staff updates'}).findByType('button').props.onClick()})
    assert.deepEqual(ui.acknowledged,[1,3])
    assert.equal(ui.view.root.findAllByProps({role:'alertdialog'}).length,0)
  } finally {ui.cleanup()}
})

test('six identical approvals appear once and one dismissal acknowledges all six',async()=>{
  const notices=Array.from({length:6},(_,index)=>({id:index+1,recipient_user_id:24,subject:'Commission automatically approved',message:'MF MF111137: approved.'}))
  const ui=await mount(notices)
  try {
    assert.equal(ui.view.root.findAllByProps({role:'alertdialog'}).length,0)
    assert.equal(ui.view.root.findAllByType('li').length,1)
    assert.match(JSON.stringify(ui.view.toJSON()),/6/)
    await act(async()=>{await ui.view.root.findByType('button').props.onClick()})
    assert.deepEqual(ui.acknowledged,[1,2,3,4,5,6])
    await ui.poll()
    assert.equal(ui.view.root.findAllByType('aside').length,0)
  } finally {ui.cleanup()}
})

test('failed approval dismissal leaves a retryable notice instead of trapping the user in a popup',async()=>{
  const ui=await mount([{id:1,recipient_user_id:24,subject:'Commission automatically approved',message:'MF MF111137: approved.'}],{failId:1})
  try {
    await act(async()=>{await ui.view.root.findByType('button').props.onClick()})
    assert.equal(ui.view.root.findAllByProps({role:'alertdialog'}).length,0)
    assert.equal(ui.view.root.findByType('button').props.disabled,false)
    assert.match(JSON.stringify(ui.view.toJSON()),/continue using the system and try again later/)
    assert.deepEqual(ui.acknowledged,[])
  } finally {ui.cleanup()}
})

test('request forms keep all notification notices paused',async()=>{
  const ui=await mount([reminder(1)],{paused:true})
  try {assert.equal(ui.view.toJSON(),null);assert.deepEqual(ui.acknowledged,[])} finally {ui.cleanup()}
})
