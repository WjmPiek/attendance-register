import './MortuaryBook.css'
export const commissionLabels = {
  removals: 'Removals', invoice_commission: 'MF File Receipts', grave_service: 'Grave Service',
  full_funeral_service: 'Full Funeral Service', cremation_service: 'Cremation Service',
  church_service: 'Church Service', joinings: 'Joinings', overtime: 'Overtime', service_other_branch: 'Service for Other Branch (additional fee)',
}
export default function CommissionCheckboxes({ branches = [], branchOptions = {}, onBranchOptionsChange }) {
  const change = (branch, category, checked) => {
    const current = branchOptions[String(branch.id)] || { enabled_types: [], receipt_percentage: '' }
    const enabled = checked ? [...current.enabled_types, category] : current.enabled_types.filter(x => x !== category)
    onBranchOptionsChange({ ...branchOptions, [branch.id]: { ...current, enabled_types: enabled } })
  }
  return <fieldset className="employee-commission-picker"><legend>Commission permissions per branch</legend>
    <p>Each linked branch has its own commission choices for this employee or manager. Only tick the commissions they may earn for that branch.</p>
    {!branches.length && <p>No linked branches available. Reopen Attendance from the main system to refresh the holder’s branch group.</p>}
    {branches.map(branch => {
      const selected = branchOptions[String(branch.id)] || { enabled_types: [], receipt_percentage: '' }
      return <section className="commission-branch-card" key={branch.id} aria-label={`${branch.name} commission permissions`}>
        <h3>{branch.name}</h3>
        <div className="commission-checkbox-grid">{Object.entries(commissionLabels).map(([key,label]) => <label key={key}><input type="checkbox" aria-label={`${branch.name} · ${label}`} checked={selected.enabled_types.includes(key)} onChange={e => change(branch,key,e.target.checked)}/><span>{label}</span></label>)}</div>

      </section>
    })}
  </fieldset>
}
