import './MortuaryBook.css'
export const commissionLabels = {
  removals: 'Removals', invoice_commission: 'MF File Receipts', grave_service: 'Grave Service',
  full_funeral_service: 'Full Funeral Service', cremation_service: 'Cremation Service',
  church_service: 'Church Service', joinings: 'Joinings', overtime: 'Overtime', service_other_branch: 'Service for Other Branch (additional fee)',
}
export default function CommissionCheckboxes({ branches = [], branchOptions = {}, onBranchOptionsChange, homeBranchId }) {
  const home=String(homeBranchId || Object.values(branchOptions).find(v=>v.home_branch_id)?.home_branch_id || '')
  const homeOptions=branchOptions[home] || {enabled_types:[],rates:{}}
  const change = (branch, category, checked) => {
    const current = branchOptions[String(branch.id)] || { enabled_types: [], receipt_percentage: '' }
    const enabled = checked ? [...current.enabled_types, category] : current.enabled_types.filter(x => x !== category)
    onBranchOptionsChange({ ...branchOptions, [branch.id]: { ...current, enabled_types: enabled } })
  }
  return <fieldset className="employee-commission-picker"><legend>Commission permissions per branch</legend>
    <p>Home-branch settings apply to linked branches by default. Turn off inheritance for a branch to set its own permissions and fees. Earnings remain listed under the branch where the work was done.</p>
    {!branches.length && <p>No linked branches available. Reopen Attendance from the main system to refresh the holder’s branch group.</p>}
    {branches.map(branch => {
      const selected = branchOptions[String(branch.id)] || { enabled_types: [], receipt_percentage: '' }
      const isHome=String(branch.id)===home
      const inherited=Boolean(home && !isHome && (selected.inherit_home ?? !branchOptions[String(branch.id)]))
      const shown=inherited ? homeOptions : selected
      const changeRate=(key,value)=>onBranchOptionsChange({...branchOptions,[branch.id]:{...selected,rates:{...selected.rates,[key]:value===''?null:value}}})
      const rateFields=[]
      if(shown.enabled_types.includes('removals')) for(const role of ['driver','assistant']) for(const [band,label] of [['in','business hours'],['out','out of hours'],['sunday_holiday','Sunday / public holiday']]) rateFields.push([`${role}_${band}`,`${role==='driver'?'Employee':'Assistant'} removal · ${label}`,false])
      for(const type of shown.enabled_types.filter(t=>t!=='removals')) for(const role of ['driver','assistant']) rateFields.push([`${role}_${type==='service_other_branch'?'other_branch':type}`,`${role==='driver'?'Employee':'Assistant'} · ${commissionLabels[type]}`,type==='invoice_commission'])
      return <section className="commission-branch-card" key={branch.id} aria-label={`${branch.name} commission permissions`}>
        <h3>{branch.name}{isHome?' · Home branch':''}</h3>
        {home && !isHome && <label className="mortuary-confirm"><input type="checkbox" aria-label={`${branch.name} · Use home-branch settings`} checked={inherited} onChange={e=>onBranchOptionsChange({...branchOptions,[branch.id]:e.target.checked?{enabled_types:[],inherit_home:true,rates:{}}:{...homeOptions,inherit_home:false}})}/>Use home-branch commission settings</label>}
        <div className="commission-checkbox-grid">{Object.entries(commissionLabels).map(([key,label]) => <label key={key}><input type="checkbox" aria-label={`${branch.name} · ${label}`} disabled={inherited} checked={shown.enabled_types.includes(key)} onChange={e => change(branch,key,e.target.checked)}/><span>{label}</span></label>)}</div>
        {!inherited && rateFields.length>0 && <details className="commission-rate-details"><summary>Branch fees and rates (optional)</summary><p>Blank fees use home-branch fees, then the employee’s configured rates. Enter a branch override to calculate different amounts here.</p><div className="mortuary-rates">{rateFields.map(([key,label,percent])=><label key={key}>{label} ({percent?'%':'R'})<input type="number" min="0" max={percent?100:1000000} step={percent?'0.0001':'0.01'} value={selected.rates?.[key]??''} placeholder="Use configured employee fee" onChange={e=>changeRate(key,e.target.value)}/></label>)}</div></details>}

      </section>
    })}
  </fieldset>
}
