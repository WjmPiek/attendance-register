import { useEffect, useState } from 'react'
import { getCommissionEntries, downloadCommissionForm, downloadCommissionReport, deleteCommissionEntry } from '../api/client'
import { commissionLabels } from './CommissionCheckboxes'

const currentMonth = () => new Date(Date.now() + 7200000).toISOString().slice(0, 7)
const money = value => `R ${Number(value || 0).toLocaleString('en-ZA', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const metadata = row => { try { return JSON.parse(row.source_metadata || '{}') } catch { return {} } }
const saveBlob = (blob, name) => {
  const url = URL.createObjectURL(blob), link = document.createElement('a')
  link.href = url; link.download = name; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export default function StaffCommissionOverview({ employeeId, franchiseId, refreshKey, me, onReview, onHistory }) {
  const [month, setMonth] = useState(currentMonth), [rows, setRows] = useState([]), [showClosed, setShowClosed] = useState(false)
  const [error, setError] = useState(''), [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [revision, setRevision] = useState(0)
  const [categoryTotals, setCategoryTotals] = useState([])
  const canManage = me.roles.some(role => ['FranchiseUser', 'SuperUser'].includes(role))
  const [year, number] = month.split('-').map(Number)
  const filters = { employeeUserId: employeeId, franchiseUserId: franchiseId, fromDate: /^\d{4}-\d{2}$/.test(month) ? new Date(Date.UTC(year, number - 2, 26)).toISOString().slice(0, 10) : '', toDate: `${month}-25` }
  useEffect(() => {
    if (!/^\d{4}-\d{2}$/.test(month)) return undefined
    let active = true
    setRows([]); setCategoryTotals([]); setLoading(true); setError('')
    const load = () => getCommissionEntries(filters).then(data => { if (active) { setRows([...data.items,...(data.pending_imports||[])]); setCategoryTotals(data.branch_category_totals || []); setError(''); setLoading(false) } }).catch(e => { if (active) { setError(e.message); setLoading(false) } })
    load()
    const timer = setInterval(load, 20000)
    return () => { active = false; clearInterval(timer) }
  }, [employeeId, franchiseId, month, refreshKey, revision])
  const run = async action => { setBusy(true); setError(''); try { await action() } catch (e) { setError(e.message) } finally { setBusy(false) } }
  const active = rows.filter(row => ['pending', 'approved'].includes(row.status))
  const approved = active.filter(row => row.status === 'approved' && row.payment_eligible).reduce((sum, row) => sum + Number(row.calculated_amount), 0)
  const blocked = active.filter(row => !row.payment_eligible)
  const awaitingDocuments = blocked.reduce((sum, row) => sum + Number(row.expected_amount ?? row.calculated_amount ?? 0), 0)
  const visible = rows.filter(row => showClosed || ['pending', 'approved'].includes(row.status))
  const closedCount = rows.length - active.length
  const cancel = row => run(async () => {
    if (window.confirm('Cancel this claim? Its audit history will be retained.')) { await deleteCommissionEntry(row.id); setRevision(value => value + 1) }
  })
  return <section className="form-card staff-commission-overview">
    <h2>Monthly commissions</h2>
    <label>Commission cycle ending<input type="month" required value={month} onChange={e => { if (e.target.value) setMonth(e.target.value) }}/></label>
    <p className="muted">{filters.fromDate} to {filters.toDate}. Late verified claims are carried forward in the finance statement.</p>
    <p className="muted">Green means the documents match and the invoice is fully paid. Red means uploads or corrections are required.</p>
    {loading ? <p role="status">Loading commissions…</p> : !error && <>
      <div className="claim-validated"><span>Approved total</span><strong>{money(approved)}</strong></div>
      <div className="claim-blocked commission-awaiting-total"><span>Total awaiting document checks</span><strong>{money(awaitingDocuments)}</strong><p>{blocked.length} commission item{blocked.length === 1 ? '' : 's'} awaiting documents or correction. Includes service claims and calculated removal and invoice commissions. Not approved for payment.</p></div>
    </>}
    {error && <p role="alert" className="error-message">{error}</p>}
    {!loading && !error && categoryTotals.length > 0 && <div className="table-wrap"><table><thead><tr><th>Service branch</th><th>Commission category</th><th>Approved</th><th>Pending estimate</th></tr></thead><tbody>{categoryTotals.map(group => <tr key={`${group.branch_id}:${group.commission_type}`}><td>{group.branch_name}</td><td>{commissionLabels[group.commission_type] || group.commission_type}</td><td className="success-message">{group.approved_count} item(s) · {money(group.approved_total)}</td><td className="error-message">{group.pending_count} item(s) · {money(group.pending_total)}</td></tr>)}</tbody></table></div>}
    <button type="button" className="glass-button" disabled={busy || loading || !rows.length} onClick={() => run(async () => saveBlob(await downloadCommissionReport(filters), `commissions-${month}.pdf`))}>Download monthly PDF</button>
    {closedCount > 0 && <label className="mortuary-confirm"><input type="checkbox" checked={showClosed} onChange={e => setShowClosed(e.target.checked)}/>Show rejected and cancelled claims ({closedCount})</label>}
    <div className="claim-status-list">{visible.map(row => {
      const meta = metadata(row), isActive = ['pending', 'approved'].includes(row.status)
      return <article key={row.id} className={isActive ? row.payment_eligible ? 'claim-validated' : 'claim-blocked' : 'commission-closed-claim'}>
        <h3>{commissionLabels[row.commission_type] || row.commission_type.replaceAll('_', ' ')}</h3>
        {(row.fee_label||meta.fee_label)&&<p>{row.fee_label||meta.fee_label}</p>}
        <strong>{row.estimate_available === false ? 'Amount awaiting document checks' : money(row.expected_amount ?? row.calculated_amount)}</strong>
        <p>{row.service_date} · MF {row.reference}</p>
        {row.branch_name && <p>{row.branch_name}</p>}
        <p>{!isActive ? row.status === 'cancelled' ? 'Cancelled' : 'Rejected' : !row.payment_eligible ? `Document uploads or corrections required: ${row.payment_block_reason}` : row.status === 'approved' ? meta.automatic_approval ? 'Automatically approved' : 'Approved' : 'Documents validated — automatic approval queued'}</p>
        <details className="commission-entry-details"><summary>Details and documents</summary>
          {(row.claim_deceased || meta.deceased) && <p>Deceased: {row.claim_deceased || meta.deceased}</p>}
          <p>{row.commission_role === 'assistant' || meta.role === 'assistant' ? 'Assistant' : 'Employee'}</p>
          <p>Configured {row.commission_type === 'invoice_commission' ? `rate: ${row.applied_rate}%` : row.commission_type === 'overtime' && meta.calculation_type !== 'fixed' ? `overtime multiplier: ${row.applied_rate}×` : `fee: ${money(row.applied_rate)}`}</p>
          {row.commission_type === 'invoice_commission' && row.invoice_value_before_tax != null && <p>Invoice commission base: {money(row.invoice_value_before_tax)}{meta.vat_registered === true ? ' (excluding VAT)' : meta.vat_registered === false ? ' (not VAT registered)' : ''}</p>}
          {meta.claim_deceased && row.notes && <p className="commission-entry-notes">{row.notes}</p>}
          {!row.document_estimate&&<><button type="button" className="glass-button" disabled={busy} onClick={() => run(async () => saveBlob(await downloadCommissionForm(row.id), `commission-${row.id}.pdf`))}>Download claim PDF</button>
          <button type="button" className="glass-button" disabled={busy} onClick={() => run(() => onHistory(row))}>Audit history</button>
          {canManage && row.status === 'pending' && Number(row.employee_user_id) !== Number(me.id) && <button type="button" className="glass-button" disabled={busy} onClick={() => onReview(row)}>Review or correct claim</button>}
          {canManage && !['approved', 'cancelled'].includes(row.status) && <button type="button" className="danger-button" disabled={busy} onClick={() => cancel(row)}>Cancel claim</button>}</>}
          {row.document_estimate&&<p>Calculated from the saved {row.commission_type==='invoice_commission'?'invoice and allocated staff':'Mortuary Book'}. Correct the source document or commission permissions to change this estimate. Included in the monthly PDF.</p>}
        </details>
      </article>
    })}</div>
    {!loading && !error && !visible.length && <p>No commissions for the selected month.</p>}
  </section>
}

