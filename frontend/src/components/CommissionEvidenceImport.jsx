import { useState } from 'react'
import { apiRequest, uploadMortuaryBooks, uploadMFInvoices, uploadMFReceipts } from '../api/client'
import ImportFeedback, { scrollImportTop } from './ImportFeedback'
import './MortuaryBook.css'

const kinds = {
  mortuary: { title: 'Mortuary Book', upload: uploadMortuaryBooks, endpoint: '/mortuary/stage' },
  invoice: { title: 'MF Invoice', upload: uploadMFInvoices, endpoint: '/receipt-commissions/invoices/stage' },
  receipt: { title: 'MF File Receipt', upload: uploadMFReceipts, endpoint: '/receipt-commissions/stage' },
}
const money = value => `R ${Number(value).toLocaleString('en-ZA', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

export default function CommissionEvidenceImport({ kind, franchiseId }) {
  const config = kinds[kind]
  const [preview, setPreview] = useState(null), [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('')
  const run = async action => { setBusy(true); setError(''); try { await action() } catch (e) { setError(e.message) } finally { setBusy(false) } }
  const read = files => run(async () => {
    setPreview(null); setConfirmed(false); setNotice('')
    setPreview(await config.upload(files, franchiseId, ''))
  })
  const save = () => run(async () => {
    const result = await apiRequest(config.endpoint, { method: 'POST', body: JSON.stringify({ preview_token: preview.preview_token, confirmed_franchise: confirmed }) })
    setNotice(`${result.saved} document(s) saved; ${result.duplicates} duplicate(s) recognised. Documents were allocated to their printed branches. Matching staff claims are recalculated automatically.`)
    setPreview(null); setConfirmed(false); scrollImportTop()
  })
  return <section className="mortuary-book">
    <ImportFeedback error={error} warnings={preview?.errors} notice={notice}/>
    <section className="form-card"><h2>{config.title}</h2>
      <p>The printed branch name determines the service branch automatically. Documents are matched by branch, MF File number and deceased name. There is no employee or commission recipient selection during uploads.</p>
      <p>Staff submit their own MF File claims. Enabled branch rates are calculated automatically after matching Mortuary Book, Invoice and receipts are present and the invoice is fully paid.</p>
      <label>Import PDF files<input key={notice} type="file" multiple accept="application/pdf,.pdf" disabled={busy} onChange={e => { const files = Array.from(e.target.files || []); if (files.length) read(files) }}/></label>
      <p className="muted">Up to 30 searchable PDFs; 10 MB per file and 50 MB per batch. Unknown, ambiguous or inactive branches are excluded with a notice for correction. Outside branches must first be registered in the holder’s branch records.</p>
      {busy && <p role="status">Reading or saving documents…</p>}
    </section>
    {preview && <section className="form-card"><h3>Check detected branches and file details</h3>
      {preview.records.map((record, index) => <article className="mortuary-record" key={index}>
        <h4>{record.branch} · MF {record.reference}</h4><p>Deceased: {record.deceased}<br/>Service date: {record.service_date}</p>
        {kind === 'mortuary' && <p>Removal staff as printed: {record.driver_in}<br/>Date / time in: {record.date_in} · {record.time_in}</p>}
        {kind === 'invoice' && <p>Invoice: {record.invoice_number}<br/>Invoice total: {money(record.invoice_total)}</p>}
        {kind === 'receipt' && <p>Receipt: {record.receipt_number}<br/>Invoice: {record.invoice_number}<br/>Payment received: {money(record.gross_received)}</p>}
        <p className="muted">{record.filename} · Page {record.page} · Detected branch #{record.earning_branch_id}</p>
      </article>)}
      {!preview.records.length && <p>No valid documents to save. Correct the reported issues and upload again.</p>}
      <label className="mortuary-confirm"><input type="checkbox" checked={confirmed} disabled={busy} onChange={e => setConfirmed(e.target.checked)}/>I have checked the printed branch and document details and reviewed all excluded pages.</label>
      <button type="button" disabled={busy || !confirmed || !preview.records.length} onClick={save}>Save evidence and check claims automatically</button>
    </section>}
  </section>
}
