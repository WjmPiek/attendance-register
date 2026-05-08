import { useEffect, useMemo, useState } from 'react'
import { deleteIrp5Document, downloadIrp5Document, getIrp5Documents, getIrp5Employees, getMyIrp5Documents, uploadIrp5Document } from '../api/client'
import DragDropFileInput from '../components/DragDropFileInput.jsx'

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

export default function Irp5DocumentsPage({ me }) {
  const isFinance = (me.employee_role || '').trim().toLowerCase().includes('finance')
  const canUpload = me.roles.includes('SuperUser') || me.roles.includes('FranchiseUser') || isFinance
  const isEmployee = me.roles.includes('EmployeeUser')
  const canDelete = canUpload
  const [employees, setEmployees] = useState([])
  const [selectedEmployeeId, setSelectedEmployeeId] = useState('')
  const [taxYear, setTaxYear] = useState(new Date().getFullYear().toString())
  const [notes, setNotes] = useState('')
  const [file, setFile] = useState(null)
  const [docs, setDocs] = useState([])
  const [yearFilter, setYearFilter] = useState('')
  const [previewUrl, setPreviewUrl] = useState('')
  const [previewName, setPreviewName] = useState('')
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const load = async () => {
    setErr('')
    try {
      if (canUpload) setEmployees(await getIrp5Employees())
      setDocs(canUpload ? await getIrp5Documents() : (isEmployee ? await getMyIrp5Documents() : []))
    } catch (error) {
      setErr(error.message || 'Failed to load IRP5 documents')
    }
  }

  useEffect(() => { load() }, [])
  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl) }, [previewUrl])

  const selectedEmployee = useMemo(() => employees.find((e) => `${e.staff_type || 'employee'}:${e.staff_id || e.employee_user_id}` === selectedEmployeeId), [employees, selectedEmployeeId])
  const years = useMemo(() => Array.from(new Set(docs.map((d) => d.tax_year).filter(Boolean))).sort().reverse(), [docs])
  const filteredDocs = useMemo(() => yearFilter ? docs.filter((d) => String(d.tax_year || '') === String(yearFilter)) : docs, [docs, yearFilter])
  const groupedDocs = useMemo(() => filteredDocs.reduce((acc, doc) => { const y = doc.tax_year || 'No tax year'; (acc[y] ||= []).push(doc); return acc }, {}), [filteredDocs])

  const upload = async (ev) => {
    ev.preventDefault()
    setMsg('')
    setErr('')
    if (!selectedEmployeeId) return setErr('Please select an employee or manager.')
    if (!file) return setErr('Please choose an IRP5 PDF or image file.')
    try {
      const uploadType = selectedEmployee?.staff_type === 'manager' ? 'managers' : 'employees'
      const uploadId = selectedEmployee?.staff_id || selectedEmployee?.employee_user_id
      await uploadIrp5Document(uploadType, uploadId, file, taxYear, notes)
      setMsg(`IRP5 uploaded and linked to ${selectedEmployee?.name || 'staff member'}.`)
      setFile(null)
      setNotes('')
      await load()
    } catch (error) {
      setErr(error.message || 'Upload failed')
    }
  }

  const download = async (doc) => {
    setErr('')
    try {
      const blob = await downloadIrp5Document(doc.id)
      saveBlob(blob, doc.original_filename || `irp5-${doc.id}.pdf`)
    } catch (error) {
      setErr(error.message || 'Download failed')
    }
  }

  const preview = async (doc) => {
    setErr('')
    try {
      const blob = await downloadIrp5Document(doc.id)
      if (previewUrl) URL.revokeObjectURL(previewUrl)
      setPreviewUrl(URL.createObjectURL(blob))
      setPreviewName(doc.original_filename || `IRP5 ${doc.tax_year || ''}`)
    } catch (error) {
      setErr(error.message || 'Preview failed')
    }
  }

  const remove = async (doc) => {
    setMsg('')
    setErr('')
    if (!window.confirm(`Delete IRP5 document ${doc.original_filename || doc.id}?`)) return
    try {
      await deleteIrp5Document(doc.id)
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl)
        setPreviewUrl('')
        setPreviewName('')
      }
      setMsg('IRP5 document deleted.')
      await load()
    } catch (error) {
      setErr(error.message || 'Delete failed')
    }
  }

  const printPreview = () => {
    if (!previewUrl) return
    const win = window.open(previewUrl, '_blank')
    if (win) win.addEventListener('load', () => win.print(), { once: true })
  }

  return (
    <div className="irp5-page no-top-gap">
      <div className="section-header compact-header">
        <p className="eyebrow">IRP 5 Documents</p>
        <h2>{canUpload ? 'Employee Tax Documents' : 'My Tax Documents'}</h2>
        <p className="muted">IRP 5 uploads are linked to selected employees or managers. Franchise and Finance users can view, download or delete documents inside their allowed scope.</p>
      </div>
      {msg ? <p className="success">{msg}</p> : null}
      {err ? <p className="error">{err}</p> : null}

      {canUpload ? (
        <section className="form-card staff-card">
          <h2>Upload IRP 5 for Employee / Manager</h2>
          <form className="staff-form-single" onSubmit={upload}>
            <label>Selected employee / manager<select value={selectedEmployeeId} onChange={(e) => setSelectedEmployeeId(e.target.value)} required><option value="">Select employee or manager by name</option>{employees.map((e) => { const value = `${e.staff_type || 'employee'}:${e.staff_id || e.employee_user_id}`; return <option key={value} value={value}>{e.name} {e.surname} - {e.staff_role || e.employee_role || e.staff_type || 'Employee'}</option> })}</select></label>
            <label>Tax year<input value={taxYear} onChange={(e) => setTaxYear(e.target.value)} placeholder="2026" /></label>
            <DragDropFileInput label="IRP 5 file" accept="application/pdf,image/png,image/jpeg" file={file} onFile={setFile} required />
            <label>Notes<textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Optional notes" /></label>
            <button className="primary-action">Upload and link to employee</button>
          </form>
        </section>
      ) : null}

      {(isEmployee || canUpload) ? (
        <section className="form-card staff-list-card">
          <div className="list-header"><div><h2>{canUpload ? 'IRP 5 Documents' : 'My IRP 5 Documents'}</h2><p className="muted">Preview PDF in the app, download it, print it, or delete it if your user role allows deleting.</p></div><label>Tax year<select value={yearFilter} onChange={(e) => setYearFilter(e.target.value)}><option value="">All years</option>{years.map((y) => <option key={y} value={y}>{y}</option>)}</select></label></div>
          {Object.keys(groupedDocs).map((year) => (
            <div key={year} className="year-group"><h3>{year}</h3><div className="table-wrap"><table><thead><tr><th>Employee</th><th>File</th><th>Uploaded</th><th>Notes</th><th>Action</th></tr></thead><tbody>{groupedDocs[year].map((doc) => <tr key={doc.id}><td>{doc.staff_name || 'My document'}</td><td>{doc.original_filename}</td><td>{doc.created_at ? new Date(doc.created_at).toLocaleString('en-ZA', { timeZone: 'Africa/Johannesburg', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'}</td><td>{doc.notes || '—'}</td><td><div className="action-row"><button className="link-button" onClick={() => preview(doc)}>View</button><button className="link-button" onClick={() => download(doc)}>Download</button>{canDelete ? <button className="link-button danger-button" onClick={() => remove(doc)}>Delete</button> : null}</div></td></tr>)}</tbody></table></div></div>
          ))}
          {!filteredDocs.length ? <p className="muted">No IRP 5 documents found.</p> : null}
          {previewUrl ? <div className="pdf-preview"><div className="list-header"><h3>Preview: {previewName}</h3><button className="primary-action" onClick={printPreview}>Print IRP5</button></div><iframe title="IRP5 PDF Preview" src={previewUrl} /></div> : null}
        </section>
      ) : null}
    </div>
  )
}
