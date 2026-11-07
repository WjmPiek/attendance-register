import test from 'node:test'
import assert from 'node:assert/strict'
import { currentCommissionMonth } from '../src/utils/commission-cycle.mjs'

test('open commission month changes exactly at 17:00 South African time on the 25th', () => {
  assert.equal(currentCommissionMonth(new Date('2026-11-25T14:59:59Z')), '2026-11')
  assert.equal(currentCommissionMonth(new Date('2026-11-25T15:00:00Z')), '2026-12')
  assert.equal(currentCommissionMonth(new Date('2026-11-26T08:00:00Z')), '2026-12')
  assert.equal(currentCommissionMonth(new Date('2026-12-01T00:00:00Z')), '2026-12')
})
test('December cutoff advances to January without depending on the browser timezone', () => {
  assert.equal(currentCommissionMonth(new Date('2026-12-25T15:00:00Z')), '2027-01')
})
