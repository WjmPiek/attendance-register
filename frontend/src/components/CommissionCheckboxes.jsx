import './MortuaryBook.css'
export const commissionLabels = {
  removals: 'Removals', invoice_commission: 'MF File Receipts', grave_service: 'Grave Service',
  full_funeral_service: 'Full Funeral Service', cremation_service: 'Cremation Service',
  church_service: 'Church Service', joinings: 'Joinings', overtime: 'Overtime',
}
export default function CommissionCheckboxes({ value = [], onChange, percentage, onPercentageChange }) {
  return <fieldset className="employee-commission-picker"><legend>Employee commission categories</legend>
    <p>Tick only the items this employee may earn. Removals and MF File Receipts also require matching documents.</p>
    <div className="commission-checkbox-grid">{Object.entries(commissionLabels).map(([key, label]) => <label key={key}><input type="checkbox" checked={(value || []).includes(key)} onChange={e => onChange(e.target.checked ? [...(value || []), key] : value.filter(x => x !== key))}/><span>{label}</span></label>)}</div>
    {(value || []).includes('invoice_commission') && <label>MF File Receipt commission (%)<input type="number" min="0" max="100" step="0.0001" placeholder="Use franchise default" value={percentage ?? ''} onChange={e => onPercentageChange(e.target.value)}/><small>Blank uses the franchise default percentage.</small></label>}
  </fieldset>
}
