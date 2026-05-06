import { useEffect, useMemo, useState } from 'react'
import { getPayrollEmployees, getPayrollRuns, previewPayroll, savePayrollSettings, importPayrollDocument, getPayrollImports } from '../api/client'
import DragDropFileInput from '../components/DragDropFileInput.jsx'

function money(value) {
  return `R ${Number(value || 0).toFixed(2)}`
}

function currentMonthStart() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`
}

export default function PayrollPage() {
  const [employees, setEmployees] = useState([])
  const [runs, setRuns] = useState([])
  const [imports, setImports] = useState([])
  const [importFile, setImportFile] = useState(null)
  const [importResult, setImportResult] = useState(null)
  const [selectedUserId, setSelectedUserId] = useState('')
  const [employeeSearch, setEmployeeSearch] = useState('')
  const [month, setMonth] = useState(currentMonthStart())
  const [preview, setPreview] = useState(null)
  const [form, setForm] = useState({ basic_salary: 0, hourly_rate: 0, allowances: 0, deductions: 0, paye_percent: 0, uif_percent: 1, pay_frequency: 'monthly', is_active: true })
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const filteredEmployees = useMemo(() => {
    const q = employeeSearch.trim().toLowerCase()
    if (!q) return employees
    return employees.filter((e) => [e.name, e.surname, e.email, e.role, e.staff_type].filter(Boolean).join(' ').toLowerCase().includes(q))
  }, [employees, employeeSearch])
  const selectedEmployee = useMemo(() => employees.find((e) => String(e.user_id) === String(selectedUserId)), [employees, selectedUserId])

  async function load() {
    setError('')
    try {
      const [staff, savedRuns, importRows] = await Promise.all([getPayrollEmployees(), getPayrollRuns(), getPayrollImports()])
      setEmployees(staff)
      setRuns(savedRuns)
      setImports(importRows)
      if (!selectedUserId && staff.length) setSelectedUserId(String(staff[0].user_id))
    } catch (e) {
      setError(e.message || 'Failed to load payroll')
    }
  }

  useEffect(() => { load() }, [])

  useEffect(() => {
    if (!selectedEmployee) return
    setForm({
      basic_salary: Number(selectedEmployee.basic_salary || 0),
      hourly_rate: Number(selectedEmployee.hourly_rate || 0),
      allowances: Number(selectedEmployee.allowances || 0),
      deductions: Number(selectedEmployee.deductions || 0),
      paye_percent: Number(selectedEmployee.paye_percent || 0),
      uif_percent: Number(selectedEmployee.uif_percent ?? 1),
      pay_frequency: selectedEmployee.pay_frequency || 'monthly',
      is_active: selectedEmployee.payroll_active !== false,
    })
  }, [selectedEmployee])

  async function saveSettings(e) {
    e.preventDefault()
    if (!selectedUserId) return
    setMessage('')
    setError('')
    try {
      await savePayrollSettings({ user_id: Number(selectedUserId), ...form })
      setMessage('Payroll settings saved.')
      await load()
    } catch (err) {
      setError(err.message || 'Could not save payroll settings')
    }
  }

  async function runPreview(saveRun = false) {
    setMessage('')
    setError('')
    try {
      const data = await previewPayroll(month, saveRun)
      setPreview(data)
      if (saveRun) {
        setMessage('Payroll draft saved.')
        const savedRuns = await getPayrollRuns()
        setRuns(savedRuns)
      }
    } catch (err) {
      setError(err.message || 'Could not generate payroll')
    }
  }

  async function uploadPayrollFile(e) {
    e.preventDefault()
    if (!importFile) {
      setError('Choose a CSV or Excel payroll file first')
      return
    }
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

  return (
    <div className="payroll-page">
      {message ? <p className="success">{message}</p> : null}
      {error ? <p className="error">{error}</p> : null}

      <section className="leave-grid payroll-grid">
        <form className="form-card staff-form-single" onSubmit={saveSettings}>
          <h2>Employee payroll setup</h2>
          <label className="wide">Search employee / manager
            <input type="search" value={employeeSearch} onChange={(e) => setEmployeeSearch(e.target.value)} placeholder="Search by name, email or role" />
          </label>
          <label className="wide">Employee / Manager
            <select value={selectedUserId} onChange={(e) => setSelectedUserId(e.target.value)}>
              {filteredEmployees.map((e) => <option key={e.user_id} value={e.user_id}>{e.name} {e.surname} - {e.role || e.staff_type}</option>)}
            </select>
          </label>
          <label>Basic monthly salary<input type="number" step="0.01" value={form.basic_salary} onChange={(e) => setForm({ ...form, basic_salary: Number(e.target.value) })} /></label>
          <label>Hourly rate<input type="number" step="0.01" value={form.hourly_rate} onChange={(e) => setForm({ ...form, hourly_rate: Number(e.target.value) })} /></label>
          <label>Allowances<input type="number" step="0.01" value={form.allowances} onChange={(e) => setForm({ ...form, allowances: Number(e.target.value) })} /></label>
          <label>Deductions<input type="number" step="0.01" value={form.deductions} onChange={(e) => setForm({ ...form, deductions: Number(e.target.value) })} /></label>
          <label>PAYE %<input type="number" step="0.01" value={form.paye_percent} onChange={(e) => setForm({ ...form, paye_percent: Number(e.target.value) })} /></label>
          <label>UIF %<input type="number" step="0.01" value={form.uif_percent} onChange={(e) => setForm({ ...form, uif_percent: Number(e.target.value) })} /></label>
          <label>Pay frequency<select value={form.pay_frequency} onChange={(e) => setForm({ ...form, pay_frequency: e.target.value })}><option value="monthly">Monthly</option><option value="weekly">Weekly</option><option value="hourly">Hourly</option></select></label>
          <label className="checkbox-line"><input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} /> Include in payroll</label>
          <button className="primary-action">Save payroll settings</button>
        </form>

        <section className="form-card">
          <h2>Payroll run</h2>
          <label>Payroll month<input type="date" value={month} onChange={(e) => setMonth(e.target.value)} /></label>
          <div className="action-row wrap-actions">
            <button className="glass-button" onClick={() => runPreview(false)}>Preview Payroll</button>
            <button className="primary-action" onClick={() => runPreview(true)}>Save Draft Run</button>
          </div>
          {preview ? (
            <div className="stat-grid mini payroll-totals">
              <div className="stat-card"><strong>{preview.totals.staff_count}</strong><span>Staff</span></div>
              <div className="stat-card"><strong>{money(preview.totals.gross_pay)}</strong><span>Gross</span></div>
              <div className="stat-card"><strong>{money(preview.totals.deductions)}</strong><span>Deductions</span></div>
              <div className="stat-card"><strong>{money(preview.totals.net_pay)}</strong><span>Net pay</span></div>
            </div>
          ) : <p className="muted">Preview a month to calculate gross pay, deductions and net pay.</p>}
        </section>
      </section>

      <section className="form-card staff-list-card payroll-import-card">
        <h2>Import payroll document</h2>
        <p className="muted">Franchise users and Finance staff can upload a CSV or Excel payroll document. Rows are matched to the correct employee by User ID, email, or full name. Matching rows update employee payroll settings automatically.</p>
        <form onSubmit={uploadPayrollFile} className="payroll-import-form">
          <label>Payroll month<input type="date" value={month} onChange={(e) => setMonth(e.target.value)} /></label>
          <DragDropFileInput label="Payroll file" accept=".csv,.xlsx,.xlsm" file={importFile} onFile={setImportFile} />
          <button className="primary-action" type="submit">Import and allocate to employees</button>
        </form>
        {importResult ? (
          <div className="import-result">
            <p className="success">Imported {importResult.rows_matched} of {importResult.rows_total} payroll rows.</p>
            <div className="table-wrap"><table><thead><tr><th>Row</th><th>Employee</th><th>Status</th><th>Message</th><th>Salary</th><th>Hourly</th><th>Allowances</th><th>Deductions</th></tr></thead><tbody>{importResult.rows.map((r) => <tr key={r.row_number}><td>{r.row_number}</td><td>{r.employee_name || r.email || '-'}</td><td><span className={`status-pill ${r.status === 'matched' ? 'approved' : 'pending'}`}>{r.status}</span></td><td>{r.message}</td><td>{money(r.basic_salary)}</td><td>{money(r.hourly_rate)}</td><td>{money(r.allowances)}</td><td>{money(r.deductions)}</td></tr>)}</tbody></table></div>
          </div>
        ) : null}
        <h3>Recent payroll imports</h3>
        <div className="table-wrap"><table><thead><tr><th>Date</th><th>File</th><th>Rows</th><th>Matched</th><th>Status</th></tr></thead><tbody>{imports.map((r) => <tr key={r.id}><td>{new Date(r.imported_at).toLocaleString('en-ZA', { timeZone: 'Africa/Johannesburg', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })}</td><td>{r.filename}</td><td>{r.rows_total}</td><td>{r.rows_matched}</td><td>{r.status}</td></tr>)}{!imports.length ? <tr><td colSpan="5" className="muted">No payroll imports yet.</td></tr> : null}</tbody></table></div>
      </section>

      {preview ? (
        <section className="form-card staff-list-card">
          <h2>Payroll preview</h2>
          <div className="table-wrap"><table><thead><tr><th>Employee</th><th>Role</th><th>Present</th><th>Leave</th><th>Late</th><th>Missing sign-out</th><th>Gross</th><th>Deductions</th><th>Net</th></tr></thead><tbody>{preview.rows.map((r) => <tr key={r.user_id}><td><strong>{r.staff_name}</strong></td><td>{r.role}</td><td>{r.days_present}</td><td>{r.leave_days}</td><td>{r.late_count}</td><td>{r.missing_sign_out_count}</td><td>{money(r.gross_pay)}</td><td>{money(r.deductions)}</td><td><strong>{money(r.net_pay)}</strong></td></tr>)}</tbody></table></div>
        </section>
      ) : null}

      <section className="form-card staff-list-card">
        <h2>Saved payroll drafts</h2>
        <div className="table-wrap"><table><thead><tr><th>Month</th><th>Employee</th><th>Role</th><th>Gross</th><th>Deductions</th><th>Net</th><th>Status</th></tr></thead><tbody>{runs.map((r) => <tr key={`${r.id}-${r.user_id}`}><td>{String(r.run_month).slice(0, 10)}</td><td>{r.staff_name}</td><td>{r.role}</td><td>{money(r.gross_pay)}</td><td>{money(r.deductions)}</td><td>{money(r.net_pay)}</td><td><span className="status-pill pending">{r.status}</span></td></tr>)}{!runs.length ? <tr><td colSpan="7" className="muted">No saved payroll runs yet.</td></tr> : null}</tbody></table></div>
      </section>
    </div>
  )
}
