import { useEffect, useState } from 'react'
import { deletePayslip, downloadPayslip, getMyPayslips, getPayrollEmployees, getPayrollPayslips, uploadPayslipDocument } from '../api/client'

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
  const isFinance = (me?.employee_role || '').toLowerCase().includes('finance')
  const canManage = Boolean(me?.roles?.includes('SuperUser') || me?.roles?.includes('FranchiseUser') || isFinance)
  const [staff, setStaff] = useState([])
  const [payslips, setPayslips] = useState([])
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const load = async () => {
    setErr('')
    try {
      if (canManage) {
        const [people, docs] = await Promise.all([getPayrollEmployees(), getPayrollPayslips()])
        setStaff(people)
        setPayslips(docs)
      } else {
        setStaff([])
        setPayslips(await getMyPayslips())
      }
    } catch (error) {
      setErr(error.message || 'Unable to load payroll documents')
    }
  }

  useEffect(() => { load() }, [canManage])

  const uploadFor = (person) => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.pdf,.zip,.png,.jpg,.jpeg,application/pdf,application/zip,image/png,image/jpeg'
    input.onchange = async () => {
      const file = input.files?.[0]
      if (!file) return
      setMsg('')
      setErr('')
      try {
        await uploadPayslipDocument(person.staff_type, person.staff_id || person.user_id, file)
        setMsg(`Payslip uploaded and linked to ${person.name} ${person.surname}.`)
        await load()
      } catch (error) {
        setErr(error.message || 'Payslip upload failed')
      }
    }
    input.click()
  }

  const openDocument = async (doc, download = false) => {
    try {
      const password = canManage ? '' : window.prompt('Enter your account password to open this private document')
      if (!canManage && !password) return
      const blob = await downloadPayslip(doc.id, password || '')
      if (download) saveBlob(blob, doc.original_filename || 'payslip.pdf')
      else {
        const url = URL.createObjectURL(blob)
        window.open(url, '_blank', 'noopener,noreferrer')
        setTimeout(() => URL.revokeObjectURL(url), 60000)
      }
    } catch (error) {
      setErr(error.message || 'Could not open payslip')
    }
  }

  const remove = async (doc) => {
    if (!window.confirm(`Remove ${doc.original_filename || 'this payslip'}?`)) return
    try {
      await deletePayslip(doc.id)
      await load()
      setMsg('Payslip removed.')
    } catch (error) {
      setErr(error.message || 'Could not remove payslip')
    }
  }

  return (
    <div className="payroll-page">
      <div className="section-header compact-header">
        <p className="eyebrow">Payroll</p>
        <h2>{canManage ? 'Employee Payslips' : 'My Payslips'}</h2>
        <p className="muted">{canManage ? 'Every registered staff member is listed below. Upload a payslip directly next to the correct person.' : 'Only payslips linked to your own account are shown.'}</p>
      </div>
      {msg ? <p className="success">{msg}</p> : null}
      {err ? <p className="error">{err}</p> : null}

      {canManage ? (
        <section className="form-card staff-list-card">
          <div className="table-wrap"><table><thead><tr><th>Employee</th><th>Role</th><th>EMPL. NO</th><th>Email</th><th>Upload</th></tr></thead><tbody>
            {staff.map((person) => <tr key={`${person.staff_type}-${person.staff_id || person.user_id}`}><td>{person.name} {person.surname}</td><td>{person.role || person.staff_type}</td><td>{person.employee_number || '—'}</td><td>{person.email || '—'}</td><td><button type="button" className="link-button" onClick={() => uploadFor(person)}>Upload payslip</button></td></tr>)}
            {!staff.length ? <tr><td colSpan="5" className="muted">No registered employees found.</td></tr> : null}
          </tbody></table></div>
        </section>
      ) : null}

      <section className="form-card staff-list-card">
        <h2>{canManage ? 'Linked Payslips' : 'My Payslips'}</h2>
        <div className="table-wrap"><table><thead><tr><th>Employee</th><th>File</th><th>Uploaded</th><th>Action</th></tr></thead><tbody>
          {payslips.map((doc) => <tr key={doc.id}><td>{doc.staff_name || 'My payslip'}</td><td>{doc.original_filename}</td><td>{doc.uploaded_at ? new Date(doc.uploaded_at).toLocaleDateString('en-ZA') : '—'}</td><td><div className="action-row"><button className="link-button" onClick={() => openDocument(doc, false)}>View</button><button className="link-button" onClick={() => openDocument(doc, true)}>Download</button>{canManage ? <button className="link-button danger-button" onClick={() => remove(doc)}>Remove</button> : null}</div></td></tr>)}
          {!payslips.length ? <tr><td colSpan="4" className="muted">No payslips linked yet.</td></tr> : null}
        </tbody></table></div>
      </section>
    </div>
  )
}
