import ImportBranchScope from './ImportBranchScope'
import { useEffect, useState } from 'react'
import { apiRequest, uploadMFReceipts } from '../api/client'
import './MortuaryBook.css'

const money = n => n == null ? '—' : `R ${Number(n).toFixed(2)}`
const labels = { removals: 'Removals', invoice_commission: 'MF File Receipts', service_other_branch: 'Service for Other Branch (additional fee)' }
export default function MFFileReceipt({ franchiseId }) {
  const [externalBranchId, setExternalBranchId] = useState('')
  const [data, setData] = useState(null), [docs, setDocs] = useState([])
  const [files, setFiles] = useState([]), [preview, setPreview] = useState(null), [allocations, setAllocations] = useState([])
  const [confirmed, setConfirmed] = useState(false), [plan, setPlan] = useState(null), [ids, setIds] = useState([])
  const [approve, setApprove] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('')
  const suffix = franchiseId ? `?franchise_user_id=${franchiseId}` : ''
  const load = async () => {
    const [d, list] = await Promise.all([apiRequest(`/receipt-commissions/settings${suffix}`), apiRequest(`/receipt-commissions/documents${suffix}`)])
    setData(d); setDocs(list)
  }
  useEffect(() => { load().catch(e => setError(e.message)) }, [suffix])
  const run = async action => { setBusy(true); setError(''); try { await action() } catch (e) { setError(e.message) } finally { setBusy(false) } }
  const upload = e => { e.preventDefault(); run(async () => {
    const result = await uploadMFReceipts(files, franchiseId, externalBranchId)
    setPreview(result); setAllocations(result.records.map((_, record) => ({ record, employee_user_ids: [], employee_roles: {} }))); setConfirmed(false); setPlan(null); setNotice('')
  }) }
  const selectEmployee = (record, uid, checked) => {
    setAllocations(old => old.map(a => a.record === record ? { ...a, employee_user_ids: checked ? [...a.employee_user_ids, uid] : a.employee_user_ids.filter(id => id !== uid) } : a)); setConfirmed(false)
  }
  const calculate = async documentIds => {
    const result = await apiRequest('/receipt-commissions/calculate', { method: 'POST', body: JSON.stringify({ franchise_user_id: franchiseId ? Number(franchiseId) : null, document_ids: documentIds }) })
    setPlan(result); setIds(documentIds); setApprove(false)
  }
  const stage = () => run(async () => {
    const result = await apiRequest('/receipt-commissions/stage', { method: 'POST', body: JSON.stringify({ preview_token: preview.preview_token, allocations, confirmed_franchise: confirmed }) })
    setPreview(null); await load(); setNotice(`${result.saved} receipts saved; ${result.duplicates} repeated receipts recognised. Documents alone earn no commission.`)
    if (result.document_ids.length) await calculate(result.document_ids)
  })
  const settle = () => run(async () => {
    const result = await apiRequest('/receipt-commissions/settle', { method: 'POST', body: JSON.stringify({ franchise_user_id: franchiseId ? Number(franchiseId) : null, document_ids: ids, quote_token: plan.quote_token }) })
    setNotice(`${result.created} approved commission entries added. Unmatched or disabled items earned no commission.`); setPlan(null); setApprove(false); await load()
  })
  const allowedFor = (employee, record) => employee.commission_branches?.[String(record.external_branch_id ? employee.branch_id : record.earning_branch_id)]?.enabled_types.includes('invoice_commission')
  const setRole = (record, uid, role) => { setAllocations(old => old.map(a => a.record === record ? { ...a, employee_roles: { ...a.employee_roles, [uid]: role } } : a)); setConfirmed(false) }
  const eligible = data?.employees.filter(e => e.commission_options.invoice_commission?.enabled) || []
  const totals = (plan?.items || []).filter(r => r.state === 'ready').reduce((acc, row) => {
    const key = `${row.employee_user_id}:${row.category}`
    const group = acc[key] ||= { name: row.employee_name, branch: row.employee_branch_name, category: row.category, total: 0 }
    group.total += Number(row.amount); return acc
  }, {})
  return <section className="mortuary-book">
    <ImportBranchScope franchiseId={franchiseId} value={externalBranchId} onChange={value => { setExternalBranchId(value); setPreview(null) }}/>
    <div className="form-card"><h2>MF File Receipt</h2><p>Import receipt payments, select eligible employees across the holder’s branches, and review commissions only when the Mortuary Book, MF Invoice and receipts match branch, deceased name and surname, and MF number, and the invoice is fully paid.</p><p className="muted">Different MF numbers remain unmatched. Receipts are added once by receipt number. The invoice must be fully paid; commission is calculated once from its total, using the branch VAT registration checked in the system.</p></div>
    {error && <p role="alert" className="error-message">{error}</p>}{notice && <p role="status" className="success-message">{notice}</p>}
    <form className="form-card" onSubmit={upload}><h3>1. Select receipt PDFs</h3><label>MF File Receipt PDFs<input type="file" accept=".pdf,application/pdf" multiple required disabled={busy} onChange={e => { setFiles(Array.from(e.target.files)); setPreview(null); setPlan(null) }}/></label><p className="muted">Up to 30 original searchable PDFs, 10 MB each and 50 MB total. Staff eligible for MF File Receipts are enabled in Edit Staff.</p><button className="primary-button" disabled={busy || !files.length}>Read MF File Receipts</button></form>
    {preview && <div className="form-card"><h3>2. Check receipts and select recipients</h3>{preview.errors.length > 0 && <div role="alert" className="error-message"><strong>Excluded pages</strong><ul>{preview.errors.map((e, i) => <li key={i}>{e.filename} · {e.page || ''}: {e.error}</li>)}</ul></div>}
      {preview.records.map((r, i) => <article className="mortuary-record" key={i}><h4>{r.branch} · MF {r.reference} · Receipt {r.receipt_number}</h4><p>Deceased: {r.deceased}<br/>ID Num: {r.id_number || 'Not provided'}<br/>Date: {r.service_date}<br/>Amount Received: {money(r.gross_received)}</p><p>Select each employee who should receive this receipt commission. You may leave all unticked if the receipt is only needed to qualify removals.</p><div className="commission-checkbox-grid">{eligible.filter(e => allowedFor(e, r)).map(e => <label key={e.user_id}><input type="checkbox" checked={allocations[i]?.employee_user_ids.includes(e.user_id) || false} onChange={event => selectEmployee(i, e.user_id, event.target.checked)}/>{e.full_name} · {e.branch_name}{allocations[i]?.employee_user_ids.includes(e.user_id) && <select aria-label={`Commission role for ${e.full_name}`} value={allocations[i]?.employee_roles?.[e.user_id] || 'driver'} onChange={event => setRole(i, e.user_id, event.target.value)}><option value="driver">Employee</option><option value="assistant">Assistant</option></select>}</label>)}</div>{!eligible.some(e => allowedFor(e, r)) && <p>No employees have MF File Receipt commissions enabled for this receipt’s branch.</p>}</article>)}
      <label className="mortuary-confirm"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)}/>I confirm the franchise, payment details and selected employees, and have reviewed any excluded pages. Saving receipts does not itself earn commission.</label><button type="button" disabled={busy || !confirmed || !preview.records.length} onClick={stage}>Save receipts and check matches</button></div>}
    <div className="form-card"><h3>Saved documents and waiting matches</h3><p>Use this after importing a missing book, enabling an employee’s category or correcting settings.</p><button type="button" className="glass-button" disabled={busy || !docs.length} onClick={() => run(() => calculate(docs.map(d => d.id)))}>Review matched commissions for recent documents</button><div className="table-wrap"><table><thead><tr><th>Document</th><th>Branch / MF</th><th>Deceased</th><th>Invoice or Receipt / Date</th></tr></thead><tbody>{docs.map(d => <tr key={d.id}><td>{d.kind === 'mortuary' ? 'Mortuary Book' : d.kind === 'invoice' ? 'MF Invoice' : 'MF File Receipt'}</td><td>{d.record.branch}<br/>{d.record.reference}</td><td>{d.record.deceased || 'Historical book'}</td><td>{(d.kind === 'invoice' ? d.record.invoice_number : d.record.receipt_number) || '—'}<br/>{d.record.service_date}</td></tr>)}</tbody></table></div></div>
    {plan && <div className="form-card"><h3>3. Matched commission review</h3><div className="table-wrap"><table><thead><tr><th>Branch / MF / Invoice</th><th>Employee / Home branch</th><th>Category / Deceased</th><th>Commissionable amount / Rate</th><th>Commission / Status</th></tr></thead><tbody>{plan.items.map((r, i) => <tr key={i}><td>{r.branch}<br/>{r.mf}<br/>{r.invoice_number || ''}<br/>{r.invoice_total && `Invoice: ${money(r.invoice_total)}`}<br/>{r.total_received && `Received: ${money(r.total_received)}`}</td><td>{r.employee_name || '—'}<br/>{r.employee_branch_name || ''}</td><td>{labels[r.category] || 'Document match'}<br/>{r.deceased || ''}<br/>{r.id_number || ''}</td><td>{r.category === 'invoice_commission' ? <>{money(r.base_amount)}<br/>{r.rate ?? 'Not configured'}%<br/>{r.vat_registered === true ? `Excluding ${r.vat_rate}% VAT` : r.vat_registered === false ? 'Not VAT registered' : 'VAT status unconfirmed'}<br/><small>{r.vat_source}</small>{r.vat_notice && <p className="muted">{r.vat_notice}</p>}</> : r.band ? <>{r.role === 'driver' ? 'Employee' : 'Assistant'} · {r.fee_label || (r.band === 'in' ? 'Business hours' : 'After hours')}{Number(r.additional_fee) > 0 && <small className="commission-branch-summary">Base: {money(r.removal_base_fee)} + Other branch: {money(r.additional_fee)}</small>}</> : '—'}</td><td><strong>{r.state === 'ready' ? money(r.amount) : 'R 0.00 earned'}</strong><br/>{r.state === 'ready' ? 'Ready for approval' : r.reason}</td></tr>)}</tbody></table></div>
      <h4>Ready totals per employee and category</h4>{Object.entries(totals).map(([key, r]) => <p key={key}>{r.name} · {r.branch} · {labels[r.category]}: <strong>{money(r.total)}</strong></p>)}<strong>Total ready: {money(plan.total)}</strong>{data?.can_approve && <><label className="mortuary-confirm"><input type="checkbox" checked={approve} onChange={e => setApprove(e.target.checked)}/>Approve only the ready entries shown. Blocked and previously recorded items will earn nothing further.</label><button type="button" className="primary-button" disabled={busy || !approve || !Object.keys(totals).length} onClick={settle}>Add reviewed commissions to employee statements</button></>}{!data?.can_approve && <p>Documents saved. The franchise holder reviews and approves the calculated commissions.</p>}</div>}
  </section>
}
