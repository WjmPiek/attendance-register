import { useEffect, useState } from 'react'
import {
  importPayrollDocument,
  getPayrollImports,
  getPayrollPayslips,
  getMyPayslips,
  downloadPayslip,
  deletePayslip,
  getPayrollImportDetail,
  updatePayrollImport,
  deletePayrollImport,
} from '../api/client'
import DragDropFileInput from '../components/DragDropFileInput.jsx'

function currentMonthStart() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`
}

function openBlob(blob) {
  const url = URL.createObjectURL(blob)
  window.open(url, '_blank', 'noopener,noreferrer')
  setTimeout(() => URL.revokeObjectURL(url), 60 * 1000)
}

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export default function PayrollPage({ me }) {
  const isFinance = (me?.employee_role || '').trim().toLowerCase().includes('finance')
  const canManagePayroll = Boolean(me?.roles?.includes('SuperUser') || me?.roles?.includes('FranchiseUser') || isFinance)
  const [imports, setImports] = useState([])
  const [payslips, setPayslips] = useState([])
  const [importFile, setImportFile] = useState(null)
  const [importResult, setImportResult] = useState(null)
  const [month, setMonth] = useState(currentMonthStart())
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [selectedImport, setSelectedImport] = useState(null)

  function askDocumentPassword() {
    if (canManagePayroll) return ''
    const password = window.prompt('Enter your account password to open this private document')
    if (!password) {
      setError('Password is required to open this private document.')
      return null
    }
    return password
  }

  async function load() {
    setError('')
    try {
      const importRowsPromise = getPayrollImports().catch(() => [])
      if (canManagePayroll) {
        const [importRows, payslipRows] = await Promise.all([
          importRowsPromise,
          getPayrollPayslips().catch(() => getMyPayslips().catch(() => [])),
        ])
        setImports(importRows)
        setPayslips(payslipRows)
      } else {
        const payslipRows = await getMyPayslips()
        setImports([])
        setPayslips(payslipRows)
      }
    } catch (e) {
      setError(e.message || 'Failed to load payslips')
    }
  }

  useEffect(() => { load() }, [canManagePayroll])

  async function uploadPayrollFile(e) {
    e.preventDefault()
    if (!importFile) return setError('Choose a ZIP, CSV or Excel payroll file first')
    setMessage('')
    setError('')
    setImportResult(null)
    try {
      const data = await importPayrollDocument(importFile, month)
      setImportResult(data)
      setMessage('Payroll import processed and matched rows updated.')
      setImportFile(null)
      await load()
    } catch (err) {
      setError(err.message || 'Could not import payroll file')
    }
  }

  async function handleViewPayslip(payslip) {
    setMessage('')
    setError('')
    try {
      const password = askDocumentPassword()
      if (password === null) return
      const blob = await downloadPayslip(payslip.id, password)
      openBlob(blob)
      setMessage('Payslip opened. If the file itself is password protected, use the document password supplied by payroll.')
    } catch (err) {
      setError(err.message || 'Could not view payslip')
    }
  }

  async function handleDownloadPayslip(payslip) {
    setMessage('')
    setError('')
    try {
      const password = askDocumentPassword()
      if (password === null) return
      const blob = await downloadPayslip(payslip.id, password)
      saveBlob(blob, payslip.zip_filename || payslip.original_filename || 'payslip.zip')
      setMessage('Payslip downloaded. If the file itself is password protected, use the document password supplied by payroll.')
    } catch (err) {
      setError(err.message || 'Could not download payslip')
    }
  }

  async function handleDeletePayslip(payslip) {
    setMessage('')
    setError('')
    if (!window.confirm(`Delete payslip ${payslip.original_filename || payslip.id}?`)) return
    try {
      await deletePayslip(payslip.id)
      setMessage('Payslip deleted.')
      await load()
    } catch (err) {
      setError(err.message || 'Could not delete payslip')
    }
  }


  async function handleViewImport(row) {
    setMessage('')
    setError('')
    try {
      setSelectedImport(await getPayrollImportDetail(row.id))
    } catch (err) {
      setError(err.message || 'Could not open import details')
    }
  }

  async function handleEditImport(row) {
    setMessage('')
    setError('')
    const currentMonth = row.payroll_month ? String(row.payroll_month).slice(0, 10) : month
    const payrollMonth = window.prompt('Payroll month (YYYY-MM-DD)', currentMonth)
    if (payrollMonth === null) return
    const status = window.prompt('Import status', row.status || 'processed')
    if (status === null) return
    try {
      await updatePayrollImport(row.id, { payroll_month: payrollMonth, status })
      setMessage('Payroll import updated.')
      await load()
      if (selectedImport?.id === row.id) setSelectedImport(await getPayrollImportDetail(row.id))
    } catch (err) {
      setError(err.message || 'Could not update import')
    }
  }

  async function handleDeleteImport(row) {
    setMessage('')
    setError('')
    if (!window.confirm(`Delete import ${row.filename || row.id}? This will hide the linked payslips too.`)) return
    try {
      await deletePayrollImport(row.id)
      setMessage('Payroll import deleted and linked payslips hidden.')
      if (selectedImport?.id === row.id) setSelectedImport(null)
      await load()
    } catch (err) {
      setError(err.message || 'Could not delete import')
    }
  }

  return (
    <div className="payroll-page">
      {message ? <p className="success">{message}</p> : null}
      {error ? <p className="error">{error}</p> : null}

      <section className="form-card staff-list-card">
        <h2>{canManagePayroll ? 'Payslip Documents' : 'My Payslips'}</h2>
        <p className="muted">{canManagePayroll ? 'Admin, franchise and finance users can view, download or delete manager and employee payslips they are allowed to manage.' : 'View or download your payslips here.'} Payslip ZIP files still use the employee ID Number as the password.</p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Employee</th>
                <th>Payslip</th>
                <th>Payroll ZIP</th>
                <th>Employee Code</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {payslips.map((p) => (
                <tr key={p.id}>
                  <td>{p.uploaded_at ? new Date(p.uploaded_at).toLocaleDateString('en-ZA') : '-'}</td>
                  <td>{p.staff_name || 'My payslip'}</td>
                  <td>{p.original_filename}</td>
                  <td>{p.zip_filename || '-'}</td>
                  <td>{p.employee_key || '-'}</td>
                  <td>
                    <div className="action-row">
                      <button type="button" className="glass-button" onClick={() => handleViewPayslip(p)}>View</button>
                      <button type="button" className="glass-button" onClick={() => handleDownloadPayslip(p)}>Download</button>
                      {canManagePayroll ? <button type="button" className="glass-button danger-button" onClick={() => handleDeletePayslip(p)}>Delete</button> : null}
                    </div>
                  </td>
                </tr>
              ))}
              {!payslips.length ? <tr><td colSpan="6" className="muted">No payslips uploaded yet.</td></tr> : null}
            </tbody>
          </table>
        </div>
      </section>

      {canManagePayroll ? (
        <section className="form-card staff-list-card payroll-import-card">
          <h2>Import payslip ZIP</h2>
          <p className="muted">Admin, franchise and finance users can upload a password-protected payslip ZIP. Files are matched to employees by EMPL. NO and saved under each employee's Payslip tab.</p>
          <form onSubmit={uploadPayrollFile} className="payroll-import-form">
            <label>Payroll month<input type="date" value={month} onChange={(e) => setMonth(e.target.value)} /></label>
            <DragDropFileInput label="Payroll file" accept=".csv,.xlsx,.xls,.pdf,.zip,.ZIP,application/zip,application/x-zip-compressed" file={importFile} onFile={setImportFile} />
            <button className="primary-action" type="submit">Import payslips</button>
          </form>
          {importResult ? <div className="import-result"><p className="success">Imported {importResult.rows_matched} of {importResult.rows_total} payroll rows.</p></div> : null}
          <h3>Recent payroll imports</h3>
          <div className="table-wrap"><table><thead><tr><th>Date</th><th>File</th><th>Rows</th><th>Matched</th><th>Status</th><th>Action</th></tr></thead><tbody>{imports.map((r) => <tr key={r.id}><td>{new Date(r.imported_at).toLocaleString('en-ZA', { timeZone: 'Africa/Johannesburg', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })}</td><td>{r.filename}</td><td>{r.rows_total}</td><td>{r.rows_matched}</td><td>{r.status}</td><td><div className="action-row"><button type="button" className="glass-button" onClick={() => handleViewImport(r)}>View</button><button type="button" className="glass-button" onClick={() => handleEditImport(r)}>Edit</button><button type="button" className="glass-button danger-button" onClick={() => handleDeleteImport(r)}>Delete</button></div></td></tr>)}{!imports.length ? <tr><td colSpan="6" className="muted">No payroll imports yet.</td></tr> : null}</tbody></table></div>
          {selectedImport ? <div className="import-result"><div className="list-header"><div><h3>Import details: {selectedImport.filename}</h3><p className="muted">Matched {selectedImport.rows_matched} of {selectedImport.rows_total} rows.</p></div><button type="button" className="glass-button" onClick={() => setSelectedImport(null)}>Close</button></div><div className="table-wrap"><table><thead><tr><th>Row</th><th>Employee Code</th><th>Employee</th><th>Matched User</th><th>Method</th><th>Status</th><th>Message</th></tr></thead><tbody>{(selectedImport.rows || []).map((row) => <tr key={row.id}><td>{row.row_number}</td><td>{row.employee_key || '-'}</td><td>{row.employee_name || row.email || '-'}</td><td>{row.matched_user_id || '-'}</td><td>{row.match_method || '-'}</td><td>{row.status}</td><td>{row.message || '-'}</td></tr>)}</tbody></table></div></div> : null}
        </section>
      ) : null}
    </div>
  )
}

