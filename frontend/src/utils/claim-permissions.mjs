export const claimTypes = ['removals', 'invoice_commission', 'full_funeral_service', 'church_service', 'grave_service', 'cremation_service', 'joinings', 'overtime']

export function allowedClaimTypes(preferences, branchId, outsideBranches = []) {
  if (!preferences || !branchId) return []
  const external = outsideBranches.some(branch => String(branch.id) === String(branchId) && branch.is_active !== false)
  const linked = preferences.branches?.some(branch => String(branch.id) === String(branchId) && branch.is_active !== false)
  if (!external && !linked) return []
  const scopeId = external ? preferences.assignment?.branch_id : branchId
  const enabled = preferences.commission_branches?.[String(scopeId)]?.enabled_types || []
  return claimTypes.filter(type => preferences.options?.[type]?.enabled && enabled.includes(type))
}

export function allowedClaimBranches(preferences, outsideBranches = []) {
  if (!preferences) return []
  return [...(preferences.branches || []), ...outsideBranches.map(branch => ({ ...branch, outside: true }))]
    .filter(branch => branch.is_active !== false && allowedClaimTypes(preferences, branch.id, outsideBranches).length > 0)
}
