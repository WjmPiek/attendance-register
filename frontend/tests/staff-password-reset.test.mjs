import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { createRequire } from 'node:module'
import React from 'react'
import TestRenderer, { act } from 'react-test-renderer'
import { transformSync } from 'esbuild'

const source = fs.readFileSync(new URL('../src/components/StaffPasswordReset.jsx', import.meta.url), 'utf8')
const compiled = transformSync(source, { loader: 'jsx', format: 'cjs' }).code
const componentModule = { exports: {} }
new Function('require', 'module', 'exports', compiled)(createRequire(import.meta.url), componentModule, componentModule.exports)
const StaffPasswordReset = componentModule.exports.default

function render(props = {}) {
  let view
  act(() => { view = TestRenderer.create(React.createElement(StaffPasswordReset, { label: 'Example Staff', onReset: async () => {}, onCancel: () => {}, ...props })) })
  return view
}
function enter(view, first, second = first) {
  act(() => {
    const fields = view.root.findAllByType('input')
    fields[0].props.onChange({ target: { value: first } })
    fields[1].props.onChange({ target: { value: second } })
  })
}
const submit = view => view.root.findByType('form').props.onSubmit({ preventDefault() {} })

test('reset is an on-page masked form and cancel does not change a password', () => {
  let cancelled = 0, calls = 0
  const view = render({ onCancel: () => cancelled++, onReset: async () => calls++ })
  assert.equal(view.root.findAllByType('input').every(field => field.props.type === 'password' && field.props.autoComplete === 'new-password'), true)
  act(() => view.root.findAllByType('button').find(button => button.props.type === 'button').props.onClick())
  assert.equal(cancelled, 1); assert.equal(calls, 0)
  act(() => view.unmount())
})
test('short and mismatched passwords never call the reset endpoint', async () => {
  let calls = 0
  const view = render({ onReset: async () => calls++ })
  enter(view, 'short')
  await act(async () => { await submit(view) })
  assert.match(view.root.findByProps({ role: 'alert' }).children.join(''), /8 characters/)
  enter(view, 'ExamplePassword1', 'DifferentPassword1')
  await act(async () => { await submit(view) })
  assert.match(view.root.findByProps({ role: 'alert' }).children.join(''), /do not match/)
  assert.equal(calls, 0)
  act(() => view.unmount())
})
test('submit sends the entered password once and clears it after success', async () => {
  const received = []
  let finish
  const view = render({ onReset: password => { received.push(password); return new Promise(resolve => { finish = resolve }) } })
  enter(view, 'ExamplePassword1')
  let pending
  act(() => { pending = submit(view) })
  assert.equal(view.root.findAllByType('input').every(field => field.props.disabled), true)
  await act(async () => { await submit(view) })
  assert.deepEqual(received, ['ExamplePassword1'])
  await act(async () => { finish(); await pending })
  assert.equal(view.root.findAllByType('input').every(field => field.props.value === ''), true)
  act(() => view.unmount())
})
test('a failed reset displays the server error and permits retry', async () => {
  let calls = 0
  const view = render({ onReset: async () => { if (++calls === 1) throw new Error('Selected staff member is unavailable.') } })
  enter(view, 'ExamplePassword1')
  await act(async () => { await submit(view) })
  assert.match(view.root.findByProps({ role: 'alert' }).children.join(''), /staff member is unavailable/)
  assert.equal(view.root.findAllByType('input').some(field => field.props.disabled), false)
  await act(async () => { await submit(view) })
  assert.equal(calls, 2)
  act(() => view.unmount())
})
