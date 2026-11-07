import test from 'node:test'
import assert from 'node:assert/strict'
import { allowedClaimTypes, allowedClaimBranches } from '../src/utils/claim-permissions.mjs'

const preferences = {
  assignment: { branch_id: 101 },
  branches: [{ id: 101 }, { id: 102 }, { id: 103, is_active: false }],
  options: { full_funeral_service: { enabled: true }, church_service: { enabled: true }, invoice_commission: { enabled: false }, service_other_branch: { enabled: true } },
  commission_branches: { 101: { enabled_types: ['full_funeral_service', 'invoice_commission', 'service_other_branch'] }, 102: { enabled_types: ['church_service'] }, 103: { enabled_types: ['church_service'] } },
}

test('a branch lists only the person’s enabled commission items for that branch', () => {
  assert.deepEqual(allowedClaimTypes(preferences, 101), ['full_funeral_service'])
  assert.deepEqual(allowedClaimTypes(preferences, 102), ['church_service'])
})
test('unselected, unknown and inactive branches expose no claim items', () => {
  for (const branch of ['', 999, 103]) assert.deepEqual(allowedClaimTypes(preferences, branch), [])
  assert.deepEqual(allowedClaimTypes(null, 101), [])
})
test('outside service uses the claimant’s home-branch permissions', () => {
  assert.deepEqual(allowedClaimTypes(preferences, 201, [{ id: 201 }]), ['full_funeral_service'])
})
test('branches with no claimable items and automatic additional fees stay out of the form', () => {
  assert.deepEqual(allowedClaimBranches(preferences).map(branch => branch.id), [101, 102])
  const disabled = { ...preferences, commission_branches: { 101: { enabled_types: ['service_other_branch'] } } }
  assert.deepEqual(allowedClaimBranches(disabled), [])
})
