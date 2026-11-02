import { useEffect, useState } from 'react'
import { apiRequest } from '../api/client'

const currentMonth = () => new Date(Date.now() + 7200000).toISOString().slice(0, 7)
export default function CommissionDeliverySettings({ franchiseId }) {
  const [month, setMonth] = useState(currentMonth), [data, setData] = useState(null), [form, setForm] = useState(null)
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('')
  const load = async () => {
    const query = new URLSearchParams({ month })
    if (franchiseId) query.set('franchise_user_id', franchiseId)
    const result = await apiRequest(`/commission/delivery-settings?${query}`)
    setData(result); setForm({ recipient_email: result.recipient_email || '', period_start: result.report.period_start, period_end: result.report.period_end, send_on: result.report.send_on.slice(0, 16) })
  }
  useEffect(() => { let active = true; if (/^\d{4}-\d{2}$/.test(month)) load().catch(e => { if (active) setError(e.message) }); return () => { active = false } }, [month, franchiseId])
  const save = async e => {
    e.preventDefault(); setBusy(true); setError(''); setNotice('')
    try {
      await apiRequest('/commission/delivery-settings', { method: 'PUT', body: JSON.stringify({ ...form, recipient_email: form.recipient_email || null, month_key: month, franchise_user_id: franchiseId ? Number(franchiseId) : null }) })
      await load(); setNotice('Finance recipient and monthly dates saved. Only document-verified approved commissions are emailed.')
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const locked = ['sent', 'sending', 'uncertain'].includes(data?.report.status)
  return <section className="form-card"><h2>Monthly commission email</h2><p>Nominate the finance person who processes commissions in your payroll system. Matching, fully paid claims approve automatically. This system emails a commission statement and does not run payroll or transfer money.</p><p className="muted">Defaults: a 25th-to-25th cycle, sent on the 27th at 08:00 South African time. Adjust this month’s cutoff and send date before sending if documents are delayed. Each commission is included once; late qualifying claims carry forward as earlier-period adjustments.</p><label>Report month<input type="month" required value={month} onChange={e => { setMonth(e.target.value); setNotice('') }}/></label>{form && <form className="form-grid" onSubmit={save}><label>Finance email address<input type="email" value={form.recipient_email} disabled={locked} onChange={e => setForm(f => ({ ...f, recipient_email: e.target.value }))}/><small>Leave blank to pause email delivery.</small></label><label>Cycle starts<input type="date" required disabled={locked} value={form.period_start} onChange={e => setForm(f => ({ ...f, period_start: e.target.value }))}/></label><label>Cutoff date<input type="date" required disabled={locked} value={form.period_end} onChange={e => setForm(f => ({ ...f, period_end: e.target.value }))}/></label><label>Send date and time (South Africa)<input type="datetime-local" required disabled={locked} value={form.send_on} onChange={e => setForm(f => ({ ...f, send_on: e.target.value }))}/></label><button className="primary-button" disabled={busy || locked}>Save monthly email settings</button></form>}{locked && <p>This report’s delivery has started. Its dates are retained; later approvals go into the next unsent summary.</p>}{data && !data.email_configured && <p className="error-message">Email delivery is awaiting the system’s email connection. Approved commissions remain saved; delivery status will show any send error.</p>}{error && <p role="alert" className="error-message">{error}</p>}{notice && <p role="status" className="success-message">{notice}</p>}{data?.history.length > 0 && <div className="table-wrap"><table><thead><tr><th>Report</th><th>Cycle</th><th>Send date</th><th>Delivery</th></tr></thead><tbody>{data.history.map(report => <tr key={report.id}><td>#{report.id} · {report.month_key}</td><td>{report.period_start} to {report.period_end}</td><td>{report.send_on?.replace('T', ' ')} SA</td><td>{report.status}{report.sent_at && <small> · {report.sent_at.replace('T', ' ')} SA</small>}{report.error_message && <p className="error-message">{report.error_message}</p>}{['sending', 'uncertain'].includes(report.status) && <p>Check delivery with finance before retrying; automatic resending is paused to avoid duplicates.</p>}</td></tr>)}</tbody></table></div>}</section>
}
