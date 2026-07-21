import { useEffect, useState } from 'react'
import { deleteIrp5Document, downloadIrp5Document, getIrp5Documents, getIrp5Employees, getMyIrp5Documents, uploadIrp5Document } from '../api/client'

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
  const isFinance = (me?.employee_role || '').toLowerCase().includes('finance')
  const canManage = Boolean(me?.roles?.includes('SuperUser') || me?.roles?.includes('FranchiseUser') || isFinance)
  const [staff, setStaff] = useState([])
  const [docs, setDocs] = useState([])
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const load = async () => {
    setErr('')
    try {
      if (canManage) {
        const [people, documents] = await Promise.all([getIrp5Employees(), getIrp5Documents()])
        setStaff(people)
        setDocs(documents)
      } else {
        setStaff([])
        setDocs(await getMyIrp5Documents())
      }
    } catch (error) {
      setErr(error.message || 'Unable to load IRP 5 documents')
    }
  }

  useEffect(() => { load() }, [canManage])

  const uploadFor = (person) => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'application/pdf,image/png,image/jpeg'
    input.onchange = async () => {
      const file = input.files?.[0]
      if (!file) return
      const year = window.prompt('Tax year', String(new Date().getFullYear())) || ''
      setMsg('')
      setErr('')
      try {
        const type = person.staff_type === 'manager' ? 'managers' : 'employees'
        await uploadIrp5Document(type, person.staff_id || person.employee_user_id, file, year, '')
        setMsg(`IRP 5 uploaded and linked to ${person.name} ${person.surname}.`)
        await load()
      } catch (error) {
        setErr(error.message || 'Upload failed')
      }
    }
    input.click()
  }

  const openDocument = async (doc, download = false) => {
    try {
      const password = canManage ? '' : window.prompt('Enter your account password to open this private document')
      if (!canManage && !password) return
      const blob = await downloadIrp5Document(doc.id, password || '')
      if (download) saveBlob(blob, doc.original_filename || 'IRP5.pdf')
      else {
        const url = URL.createObjectURL(blob)
        window.open(url, '_blank', 'noopener,noreferrer')
        setTimeout(() => URL.revokeObjectURL(url), 60000)
      }
    } catch (error) {
      setErr(error.message || 'Could not open document')
    }
  }

  const remove = async (doc) => {
    if (!window.confirm(`Remove ${doc.original_filename || 'this IRP 5'}?`)) return
    try {
      await deleteIrp5Document(doc.id)
      await load()
      setMsg('IRP 5 removed.')
    } catch (error) {
      setErr(error.message || 'Could not remove document')
    }
  }

  return (
    <div className="irp5-page no-top-gap">
      <div className="section-header compact-header">
        <p className="eyebrow">IRP 5</p>
        <h2>{canManage ? 'Employee IRP 5 Documents' : 'My IRP 5 Documents'}</h2>
        <p className="muted">{canManage ? 'Every registered staff member is listed below. Upload the IRP 5 document next to the correct person.' : 'Only IRP 5 documents linked to your own account are shown.'}</p>
      </div>
      {msg ? <p className="success">{msg}</p> : null}
      {err ? <p className="error">{err}</p> : null}

      {canManage ? (
        <section className="form-card staff-list-card">
          <div className="table-wrap"><table><thead><tr><th>Employee</th><th>Role</th><th>Email</th><th>Upload</th></tr></thead><tbody>
            {staff.map((person) => <tr key={`${person.staff_type}-${person.staff_id}`}><td>{person.name} {person.surname}</td><td>{person.staff_role || person.employee_role || person.staff_type}</td><td>{person.email || '—'}</td><td><button className="link-button" onClick={() => uploadFor(person)}>Upload IRP 5</button></td></tr>)}
            {!staff.length ? <tr><td colSpan="4" className="muted">No registered employees found.</td></tr> : null}
          </tbody></table></div>
        </section>
      ) : null}

      <section className="form-card staff-list-card">
        <h2>{canManage ? 'Linked IRP 5 Documents' : 'My IRP 5 Documents'}</h2>
        <div className="table-wrap"><table><thead><tr><th>Employee</th><th>Tax year</th><th>File</th><th>Uploaded</th><th>Action</th></tr></thead><tbody>
          {docs.map((doc) => <tr key={doc.id}><td>{doc.staff_name || 'My document'}</td><td>{doc.tax_year || '—'}</td><td>{doc.original_filename}</td><td>{doc.created_at ? new Date(doc.created_at).toLocaleDateString('en-ZA') : '—'}</td><td><div className="action-row"><button className="link-button" onClick={() => openDocument(doc, false)}>View</button><button className="link-button" onClick={() => openDocument(doc, true)}>Download</button>{canManage ? <button className="link-button danger-button" onClick={() => remove(doc)}>Remove</button> : null}</div></td></tr>)}
          {!docs.length ? <tr><td colSpan="5" className="muted">No IRP 5 documents linked yet.</td></tr> : null}
        </tbody></table></div>
      </section>
    </div>
  )
}
