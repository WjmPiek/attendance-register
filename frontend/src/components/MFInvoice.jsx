import ImportBranchScope from './ImportBranchScope'
import { useEffect, useState } from 'react'
import { apiRequest, apiBlob, uploadMFInvoices } from '../api/client'
import './MortuaryBook.css'

const money = value => `R ${Number(value || 0).toLocaleString('en-ZA', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

export default function MFInvoice({ franchiseId }) {
  const [externalBranchId, setExternalBranchId] = useState('')
  const [files, setFiles] = useState([]), [preview, setPreview] = useState(null), [confirmed, setConfirmed] = useState(false)
  const [documents, setDocuments] = useState([]), [busy, setBusy] = useState(false)
  const [error, setError] = useState(''), [notice, setNotice] = useState('')
  const suffix = franchiseId ? `?franchise_user_id=${encodeURIComponent(franchiseId)}` : ''
  const load = async () => setDocuments((await apiRequest(`/receipt-commissions/documents${suffix}`)).filter(d => d.kind === 'invoice'))
  useEffect(() => { load().catch(e => setError(e.message)) }, [suffix])
  const run = async action => { setBusy(true); setError(''); setNotice(''); try { await action() } catch (e) { setError(e.message) } finally { setBusy(false) } }
  const upload = event => {
    event.preventDefault()
    run(async () => { setPreview(null); setConfirmed(false); setPreview(await uploadMFInvoices(files, franchiseId, externalBranchId)) })
  }
  const save = () => run(async () => {
    const result = await apiRequest('/receipt-commissions/invoices/stage', { method: 'POST', body: JSON.stringify({ preview_token: preview.preview_token, confirmed_franchise: confirmed }) })
    setPreview(null); setFiles([]); setConfirmed(false); await load()
    setNotice(`${result.saved} invoices saved; ${result.duplicates} duplicates skipped. Import the matching Mortuary Book and all payment receipts, then review commissions under MF File Receipt.`)
  })
  const download = document => run(async () => {
    const blob = await apiBlob(`/receipt-commissions/invoices/${document.id}/download${suffix}`)
    const url = URL.createObjectURL(blob), link = window.document.createElement('a')
    link.href = url; link.download = `mf-invoice-${document.id}.pdf`; link.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  })
  return <section className="mortuary-book">
    <ImportBranchScope franchiseId={franchiseId} value={externalBranchId} onChange={value => { setExternalBranchId(value); setPreview(null) }}/>
    <header className="form-card"><h2>MF Invoice</h2><p>Import the original invoice showing the full service amount. All three document types must match the branch, deceased name and surname, and MF file number. Receipts must also reference this invoice number.</p><p className="muted">No commission is payable until the invoice is fully paid. The invoice commission is awarded once per employee. VAT is checked against the system branch record: a registered branch uses the amount before VAT; a confirmed non-VAT branch uses the full amount. Unclear invoice VAT details use the confirmed system status.</p></header>
    {error && <p role="alert" className="error-message">{error}</p>}{notice && <p role="status" className="success-message">{notice}</p>}
    <form className="form-card" onSubmit={upload}><h3>1. Select invoice PDFs</h3><label>MF Invoice PDFs<input type="file" multiple required accept=".pdf,application/pdf" disabled={busy} onChange={e => { setFiles(Array.from(e.target.files)); setPreview(null); setConfirmed(false) }}/></label><p className="muted">Up to 30 searchable PDFs, 10 MB per PDF and 50 MB per batch. Original PDFs are retained for download.</p><button className="primary-button" disabled={busy || !files.length}>Read MF Invoices</button></form>
    {preview && <section className="form-card"><h3>2. Check invoice details</h3>{preview.errors.length > 0 && <div role="alert" className="error-message"><strong>Excluded pages</strong><ul>{preview.errors.map((item, index) => <li key={index}>{item.filename} · {item.page || ''}: {item.error}</li>)}</ul></div>}{preview.records.map((record, index) => <article className="mortuary-record" key={index}><h4>{record.branch} · MF {record.reference} · Invoice {record.invoice_number}</h4><p>Deceased: {record.deceased}<br/>Invoice date: {record.service_date}<br/>Invoice total: {money(record.invoice_total)}<br/>Printed VAT number: {record.vat_number || 'Not shown'}<br/>Printed amount before VAT: {record.invoice_subtotal ? money(record.invoice_subtotal) : 'Not shown'}</p>{record.vat_issue && <p className="muted">{record.vat_issue}</p>}</article>)}<label className="mortuary-confirm"><input type="checkbox" checked={confirmed} disabled={busy} onChange={e => setConfirmed(e.target.checked)}/>I confirm the printed invoice details and franchise and have reviewed all excluded pages.</label><button type="button" className="primary-button" disabled={busy || !confirmed || !preview.records.length} onClick={save}>Save invoice proof</button></section>}
    <section className="form-card"><h3>Saved invoices</h3><div className="table-wrap"><table><thead><tr><th>Branch / MF</th><th>Deceased</th><th>Invoice / Date</th><th>Invoice total</th><th>Original PDF</th></tr></thead><tbody>{documents.map(document => <tr key={document.id}><td>{document.record.branch}<br/>{document.record.reference}</td><td>{document.record.deceased}</td><td>{document.record.invoice_number}<br/>{document.record.service_date}</td><td>{money(document.record.invoice_total)}</td><td><button type="button" className="link-button" disabled={busy} onClick={() => download(document)}>Download invoice</button></td></tr>)}{!documents.length && <tr><td colSpan="5">No invoices imported yet.</td></tr>}</tbody></table></div></section>
  </section>
}
