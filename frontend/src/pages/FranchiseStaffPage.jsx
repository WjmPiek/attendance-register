import React, { useEffect, useMemo, useState } from 'react'
import { apiFetch, resetStaffPassword, uploadIrp5Document, getOfficeQrCodes, downloadOfficeQrPdf, uploadStaffIdPhoto, downloadStaffIdCards, updateOfficeLocation } from '../api/client'
import OfficeLocationMap from '../components/OfficeLocationMap'
import DragDropFileInput from '../components/DragDropFileInput.jsx'
import StaffIdCard from '../components/StaffIdCard.jsx'
import { getCurrentLocation } from "../utils/location";
import { getDistance } from "../utils/distance";

const staffRoles = [
  'Manager',
  'Finance',
  'Admin',
  'Arrangement Officer',
  'Driver',
  'Cleaner',
  'Mortuary Assistant',
  'Garden Cleaner',
  'Tea Lady',
]

const emptyStaff = {
  role: 'Manager',
  manager_user_id: '',
  username: '',
  employee_number: '',
  name: '',
  surname: '',
  email: '',
  contact_number: '',
  office_address_assigned: '',
  work_start_time: '08:00',
  work_end_time: '17:00',
  password: '',
  is_active: true,
}


function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value))
}

async function cropPhotoToIdCardFile(dataUrl, offset, filename = 'id-photo.png') {
  if (!dataUrl) return null
  const image = await new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = reject
    img.src = dataUrl
  })
  const outW = 600
  const outH = 740
  const frameW = 156
  const frameH = 192
  const canvas = document.createElement('canvas')
  canvas.width = outW
  canvas.height = outH
  const ctx = canvas.getContext('2d')
  ctx.fillStyle = '#ffffff'
  ctx.fillRect(0, 0, outW, outH)
  const scale = Math.max(outW / image.width, outH / image.height)
  const drawW = image.width * scale
  const drawH = image.height * scale
  const dx = (outW - drawW) / 2 + (offset.x || 0) * (outW / frameW)
  const dy = (outH - drawH) / 2 + (offset.y || 0) * (outH / frameH)
  ctx.drawImage(image, dx, dy, drawW, drawH)
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png', 0.92))
  if (!blob) return null
  return new File([blob], filename.replace(/\.[^.]+$/, '') + '_aligned.png', { type: 'image/png' })
}

function MovablePhotoPlaceholder({ preview, offset, setOffset, onDropFile }) {
  const [dragging, setDragging] = React.useState(false)
  const [photoDragging, setPhotoDragging] = React.useState(false)
  const startRef = React.useRef({ x: 0, y: 0, ox: 0, oy: 0 })

  const startMove = (event) => {
    if (!preview) return
    event.preventDefault()
    setPhotoDragging(true)
    startRef.current = {
      x: event.clientX,
      y: event.clientY,
      ox: offset.x || 0,
      oy: offset.y || 0,
    }
    event.currentTarget.setPointerCapture?.(event.pointerId)
  }

  const movePhoto = (event) => {
    if (!photoDragging || !preview) return
    const nextX = startRef.current.ox + (event.clientX - startRef.current.x)
    const nextY = startRef.current.oy + (event.clientY - startRef.current.y)
    setOffset({ x: clamp(nextX, -55, 55), y: clamp(nextY, -70, 70) })
  }

  const stopMove = () => setPhotoDragging(false)

  const handleDrop = (event) => {
    event.preventDefault()
    event.stopPropagation()
    setDragging(false)
    const file = event.dataTransfer.files?.[0]
    if (file) onDropFile?.(file)
  }

  return (
    <div
      className={`id-photo-placeholder movable-photo ${dragging ? 'dragging' : ''} ${preview ? 'has-photo' : ''}`}
      onDragEnter={(e) => { e.preventDefault(); setDragging(true) }}
      onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
      onDragLeave={(e) => { e.preventDefault(); setDragging(false) }}
      onDrop={handleDrop}
      onPointerDown={startMove}
      onPointerMove={movePhoto}
      onPointerUp={stopMove}
      onPointerCancel={stopMove}
    >
      {preview ? (
        <img
          src={preview}
          alt="ID photo preview"
          draggable="false"
          style={{ transform: `translate(${offset.x || 0}px, ${offset.y || 0}px) scale(1.18)` }}
        />
      ) : <span>ID PHOTO</span>}
      {preview ? <em>Drag photo to align face</em> : null}
    </div>
  )
}

function cleanPayload(payload) {
  const next = { ...payload }
  Object.keys(next).forEach((key) => {
    if (next[key] === '') next[key] = null
  })
  if (!next.password) delete next.password
  if (next.manager_user_id) next.manager_user_id = Number(next.manager_user_id)
  else delete next.manager_user_id
  return next
}

function StaffDetail({ title, item, onClose, onEdit }) {
  if (!item) return null

  return (
    <section className="form-card staff-list-card detail-panel">
      <div className="detail-header">
        <h2>{title}</h2>
        <div className="action-links">
          <button type="button" className="link-button" onClick={onEdit}>Edit</button>
          <button type="button" className="link-button" onClick={onClose}>Close</button>
        </div>
      </div>

      <StaffIdCard item={item} />

      <div className="staff-detail-with-photo">
        <div className="id-photo-placeholder readonly-photo">
          {item.photo_url ? <img src={item.photo_url} alt="ID photo" /> : <span>ID PHOTO</span>}
        </div>

        <div className="detail-grid">
          {Object.entries(item)
            .filter(([key]) => ![
              'password_hash',
              'photo_url',
              'documents',
              'qr_image_url',
              'qr_payload',
              'profile_photo_filename',
              'profile_photo_mime',
              'login_email',
              'login_active'
            ].includes(key))
            .map(([key, value]) => (
              <div key={key}>
                <span>{key.replaceAll('_', ' ')}</span>
                <strong>{value === null || value === undefined || value === '' ? '—' : String(value)}</strong>
              </div>
            ))}
        </div>
      </div>

      {Array.isArray(item.documents) && item.documents.length ? (
        <div className="staff-documents">
          <h3>Linked Documents</h3>
          <ul>
            {item.documents.map((doc) => (
              <li key={doc.id}>
                <strong>{doc.original_filename}</strong>
                <span>{doc.tax_year ? ` Tax year: ${doc.tax_year}` : ''}</span>
                <span>{doc.created_at ? ` Uploaded: ${new Date(doc.created_at).toLocaleDateString()}` : ''}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="muted small">No linked documents found for this user.</p>
      )}
    </section>
  )
}

export default function FranchiseStaffPage() {
  const [activeSubTab, setActiveSubTab] = useState('view')
  const [managers, setManagers] = useState([])
  const [employees, setEmployees] = useState([])
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [staff, setStaff] = useState(emptyStaff)
  const [editing, setEditing] = useState(null)
  const [viewItem, setViewItem] = useState(null)
  const [viewTitle, setViewTitle] = useState('')
  const [officeQrs, setOfficeQrs] = useState([])
  const [idPhotoFile, setIdPhotoFile] = useState(null)
  const [idPhotoPreview, setIdPhotoPreview] = useState('')
  const [idPhotoOffset, setIdPhotoOffset] = useState({ x: 0, y: 0 })
  const [selectedOffice, setSelectedOffice] = useState(null);
  const [pickedLocation, setPickedLocation] = useState(null);
  const staffAddressInputRef = React.useRef(null);
  const staffAutocompleteRef = React.useRef(null);

  const activeManagers = useMemo(() => managers.filter((m) => m.is_active !== false), [managers])
  const isManagerRole = staff.role === 'Manager'

  const load = async () => {
    setErr('')
    try {
      const [m, e, qrs] = await Promise.all([
        apiFetch('/franchise-staff/managers'),
        apiFetch('/franchise-staff/employees'),
        getOfficeQrCodes().catch(() => []),
      ])
      setManagers(m)
      setEmployees(e)
      setOfficeQrs(qrs)
    } catch (error) {
      setErr(error.message || 'Failed to load franchise staff')
    }
  }

  useEffect(() => { load() }, [])

  useEffect(() => {
    if (activeSubTab !== 'add') return;

    const apiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;

    function initStaffAddressAutocomplete() {
      if (!window.google?.maps?.places || !staffAddressInputRef.current) return;

      staffAutocompleteRef.current = new window.google.maps.places.Autocomplete(
        staffAddressInputRef.current,
        {
          componentRestrictions: { country: 'za' },
          fields: ['formatted_address', 'geometry'],
        }
      );

      staffAutocompleteRef.current.addListener('place_changed', () => {
        const place = staffAutocompleteRef.current.getPlace();

        if (place?.formatted_address) {
          setStaff((current) => ({
            ...current,
            office_address_assigned: place.formatted_address,
          }));
        }
      });
    }

    if (window.google?.maps?.places) {
      setTimeout(initStaffAddressAutocomplete, 0);
      return;
    }

    if (!apiKey) {
      console.warn('Missing VITE_GOOGLE_MAPS_API_KEY');
      return;
    }

    const existingScript = document.querySelector('script[src*="maps.googleapis.com/maps/api/js"]');

    if (existingScript) {
      existingScript.addEventListener('load', initStaffAddressAutocomplete, { once: true });
      setTimeout(initStaffAddressAutocomplete, 500);
      return;
    }

    const script = document.createElement('script');
    script.dataset.googlePlaces = 'true';
    script.src = `https://maps.googleapis.com/maps/api/js?key=${apiKey}&libraries=places`;
    script.async = true;
    script.defer = true;
    script.onload = initStaffAddressAutocomplete;
    document.head.appendChild(script);
  }, [activeSubTab])

  const resetForm = () => {
    setStaff(emptyStaff)
    setEditing(null)
    setIdPhotoFile(null)
    setIdPhotoPreview('')
    setIdPhotoOffset({ x: 0, y: 0 })
  }


  const handleIdPhotoChange = (event) => {
    const file = event.target.files?.[0]
    if (!file) {
      setIdPhotoFile(null)
      setIdPhotoPreview('')
      return
    }
    if (!file.type.startsWith('image/')) {
      setErr('Please upload a JPG, PNG, or WEBP ID photo.')
      return
    }
    setIdPhotoFile(file)
    setIdPhotoOffset({ x: 0, y: 0 })
    const reader = new FileReader()
    reader.onload = () => setIdPhotoPreview(String(reader.result || ''))
    reader.readAsDataURL(file)
  }

  const saveStaff = async (ev) => {
    ev.preventDefault()
    setMsg('')
    setErr('')
    try {
      if (!editing && !idPhotoFile) {
        setErr('Please upload an ID photo before creating the staff member. The photo is linked to the staff ID card and PDF exports.')
        return
      }
      const payload = cleanPayload(staff)
      let savedType = isManagerRole ? 'managers' : 'employees'
      let savedId = editing?.id || null
      if (isManagerRole) {
        const managerPayload = { ...payload }
        delete managerPayload.role
        delete managerPayload.manager_user_id
        if (editing?.type === 'managers') {
          await apiFetch(`/franchise-staff/managers/${editing.id}`, { method: 'PUT', body: JSON.stringify(managerPayload) })
          setMsg('Manager updated.')
        } else {
          const created = await apiFetch('/franchise-staff/managers', { method: 'POST', body: JSON.stringify(managerPayload) })
          savedId = created.manager_id
          setMsg('Manager created and ID photo linked.')
        }
      } else {
        const employeePayload = { ...payload, employee_role: payload.role }
        delete employeePayload.role
        if (editing?.type === 'employees') {
          await apiFetch(`/franchise-staff/employees/${editing.id}`, { method: 'PUT', body: JSON.stringify(employeePayload) })
          setMsg('Employee updated.')
        } else {
          const created = await apiFetch('/franchise-staff/employees', { method: 'POST', body: JSON.stringify(employeePayload) })
          savedId = created.employee_id
          setMsg('Employee created and ID photo linked.')
        }
      }
      if (idPhotoFile && savedId) {
        const alignedPhoto = await cropPhotoToIdCardFile(idPhotoPreview, idPhotoOffset, idPhotoFile.name)
        await uploadStaffIdPhoto(savedType, savedId, alignedPhoto || idPhotoFile)
      }
      resetForm()
      setActiveSubTab('view')
      await load()
    } catch (error) {
      setErr(error.message || 'Failed to save staff member')
    }
  }

  const viewStaff = async (type, id) => {
    setErr('')
    try {
      const data = await apiFetch(`/franchise-staff/${type}/${id}`)
      setViewItem(data)
      setViewTitle(type === 'employees' ? 'Employee Information' : 'Manager Information')
      setActiveSubTab('view')
      setTimeout(() => document.querySelector('.detail-panel')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50)
    } catch (error) {
      setErr(error.message || 'Failed to view staff member')
    }
  }

  const editStaff = (type, item) => {
    setEditing({ type, id: item.id })
    setStaff({
      role: type === 'managers' ? 'Manager' : (item.employee_role || 'Finance'),
      manager_user_id: item.manager_user_id || '',
      name: item.name || '',
      surname: item.surname || '',
      email: item.email || '',
      contact_number: item.contact_number || '',
      office_address_assigned: item.office_address_assigned || '',
      work_start_time: item.work_start_time || '08:00',
      work_end_time: item.work_end_time || '17:00',
      password: '',
      username: item.username || '',
      employee_number: item.employee_number || '',
      is_active: item.is_active !== false,
    })
    setIdPhotoFile(null)
    setIdPhotoPreview(item.photo_url || '')
    setIdPhotoOffset({ x: 0, y: 0 })
    setActiveSubTab('add')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const resetPassword = async (type, id, label) => {
    const password = window.prompt('Enter a new password for ' + label + '. Minimum 8 characters.', '')
    if (password === null) return
    if (!password || password.length < 8) {
      setErr('Password must be at least 8 characters.')
      return
    }
    setMsg('')
    setErr('')
    try {
      await resetStaffPassword(type, id, password)
      setMsg('Password reset for ' + label + '.')
    } catch (error) {
      setErr(error.message || 'Failed to reset password')
    }
  }

  const uploadStaffIrp5 = async (type, staffMember) => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'application/pdf,image/png,image/jpeg'
    input.onchange = async () => {
      const file = input.files?.[0]
      if (!file) return
      const taxYear = window.prompt('Tax year for this IRP 5 document:', new Date().getFullYear().toString()) || ''
      setMsg('')
      setErr('')
      try {
        await uploadIrp5Document(type, staffMember.id, file, taxYear, '')
        setMsg(`IRP 5 uploaded and linked to ${staffMember.name} ${staffMember.surname}. It will show in that user's linked documents and My IRP 5 page.`)
      } catch (error) {
        setErr(error.message || 'Failed to upload IRP 5 document')
      }
    }
    input.click()
  }



  const uploadIdPhoto = async (type, item) => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'image/png,image/jpeg,image/webp'
    input.onchange = async () => {
      const file = input.files?.[0]
      if (!file) return
      setMsg('')
      setErr('')
      try {
        await uploadStaffIdPhoto(type, item.id, file)
        setMsg(`ID photo uploaded for ${item.name} ${item.surname}. It will print on ID cards and attendance PDF exports.`)
        await load()
      } catch (error) {
        setErr(error.message || 'Failed to upload ID photo')
      }
    }
    input.click()
  }

  const downloadIdCards = async (staffType, staffId) => {
    setMsg('')
    setErr('')

    if (!staffType || !staffId) {
      setErr('Please select a staff member first.')
      return
    }

    try {
      const blob = await downloadStaffIdCards('', staffType, staffId)

      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `staff_id_card_${staffType}_${staffId}.pdf`

      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)

      setMsg('Selected staff ID card PDF downloaded.')
    } catch (error) {
      console.error('Staff ID card download failed', error)
      setErr('Could not download the staff ID card. Please refresh and try again.')
    }
  }
 
  const printOfficeQr = async (office) => {
    setMsg('')
    setErr('')
    try {
      const blob = await downloadOfficeQrPdf(office.id)
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `office_qr_${office.name || office.id}.pdf`
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
      setMsg('Office QR PDF downloaded. Print and place it at the office attendance point.')
    } catch (error) {
      setErr(error.message || 'Failed to download office QR PDF')
    }
  }

  const saveOfficeLocation = async () => {
    if (!selectedOffice || !pickedLocation) return;

    await updateOfficeLocation(selectedOffice.id, pickedLocation);
    setMsg('Office GPS location saved.');
    const qrs = await getOfficeQrCodes();
    setOfficeQrs(qrs);
    setSelectedOffice(null);
    setPickedLocation(null);
  };

  const [myLocation, setMyLocation] = useState(null);

  useEffect(() => {
    if (selectedOffice) {
      getCurrentLocation().then(setMyLocation).catch(() => {});
    }
  }, [selectedOffice]);


  const deleteStaff = async (type, id) => {
    const label = type === 'employees' ? 'employee' : 'manager'
    if (!window.confirm(`Delete this ${label}? This will make the staff member inactive.`)) return
    setMsg('')
    setErr('')
    try {
      await apiFetch(`/franchise-staff/${type}/${id}`, { method: 'DELETE' })
      setMsg(`${label.charAt(0).toUpperCase() + label.slice(1)} deleted.`)
      if (viewItem?.id === id) {
        setViewItem(null)
        setViewTitle('')
      }
      await load()
    } catch (error) {
      setErr(error.message || `Failed to delete ${label}`)
    }
  }

  const renderActions = (type, item) => {
    const label = ((item.name || '') + ' ' + (item.surname || '')).trim() || type.slice(0, -1)

    const handleActionChange = (event) => {
      const action = event.target.value
      event.target.value = ''

      if (action === 'view') viewStaff(type, item.id)
      if (action === 'edit') editStaff(type, item)
      if (action === 'reset-password') resetPassword(type, item.id, label)
      if (action === 'download-id-card') downloadIdCards(type, item.id)
      if (action === 'upload-id-photo') uploadIdPhoto(type, item)
      if (action === 'upload-irp5') uploadStaffIrp5(type, item)
      if (action === 'delete') deleteStaff(type, item.id)
    }

    return (
      <td className="actions-cell">
        <select className="actions-dropdown" defaultValue="" onChange={handleActionChange} aria-label={`Actions for ${label}`}>
          <option value="" disabled>Actions</option>
          <option value="view">View</option>
          <option value="edit">Edit</option>
          <option value="reset-password">Reset Password</option>
          <option value="download-id-card">Download ID Card</option>
          <option value="upload-id-photo">Upload ID Photo</option>
          <option value="upload-irp5">Upload IRP 5</option>
          <option value="delete">Delete</option>
        </select>
      </td>
    )
  }

  return (
    <div className="staff-page">
      <div className="section-header">
        <p className="eyebrow">HR Management</p>
        <h2>My Franchise Staff</h2>
        <p className="muted">Add staff from one form, view details, edit records, reset passwords, or make staff inactive.</p>
      </div>

      <div className="sub-tabs">
        <button className={activeSubTab === 'view' ? 'active' : ''} onClick={() => setActiveSubTab('view')}>View Staff</button>
        <button className={activeSubTab === 'add' ? 'active' : ''} onClick={() => { resetForm(); setActiveSubTab('add') }}>Add New Employee</button>
        <button className={activeSubTab === 'qr' ? 'active' : ''} onClick={() => setActiveSubTab('qr')}>Office QR Codes</button>
      </div>

      {msg ? <p className="success">{msg}</p> : null}
      {err ? <p className="muted small">Staff data could not load. Check backend server, then refresh.</p> : null}

      {activeSubTab === 'add' ? (
        <section className="form-card staff-card single-staff-form">
          <div className="detail-header">
            <h2>{editing ? `Edit ${isManagerRole ? 'Manager' : 'Employee'}` : 'Add Staff Member'}</h2>
            {editing ? <button type="button" className="link-button" onClick={resetForm}>Cancel edit</button> : null}
          </div>
          <form onSubmit={saveStaff} className="staff-form-single">
            <label>Assign to / Role<select value={staff.role} onChange={(e) => setStaff({ ...staff, role: e.target.value, manager_user_id: e.target.value === 'Manager' ? '' : staff.manager_user_id })}>{staffRoles.map((role) => <option key={role}>{role}</option>)}</select></label>
            {!isManagerRole ? <label>Manager optional<select value={staff.manager_user_id || ''} onChange={(e) => setStaff({ ...staff, manager_user_id: e.target.value })}><option value="">No manager selected</option>{activeManagers.map((m) => <option key={m.id} value={m.id}>{m.name} {m.surname}</option>)}</select></label> : null}
            <label>Username <span className="optional-note">login name if no email</span><input value={staff.username || ''} onChange={(e) => setStaff({ ...staff, username: e.target.value })} placeholder="e.g. manager_northcliff" /></label>
            <label>EMPL. NO
              <span className="optional-note">used for payroll import matching</span>
              <input
                value={staff.employee_number || ''}
                onChange={(e) => setStaff({ ...staff, employee_number: e.target.value })}
                placeholder="e.g. 1234567"
              />
            </label>
            <label>Name<input required value={staff.name} onChange={(e) => setStaff({ ...staff, name: e.target.value })} /></label>
            <label>Surname<input required value={staff.surname} onChange={(e) => setStaff({ ...staff, surname: e.target.value })} /></label>
            <label>Email Address <span className="optional-note">optional</span><input type="email" value={staff.email || ''} onChange={(e) => setStaff({ ...staff, email: e.target.value })} /></label>
            <label>Contact Number<input value={staff.contact_number || ''} onChange={(e) => setStaff({ ...staff, contact_number: e.target.value })} /></label>
            <label>Office Address Assigned<input ref={staffAddressInputRef} value={staff.office_address_assigned || ''} onChange={(e) => setStaff({ ...staff, office_address_assigned: e.target.value })} placeholder="Start typing address..." /></label>
            <div className="hours-grid">
              <label>Office Start Time<input type="time" required value={staff.work_start_time || '08:00'} onChange={(e) => setStaff({ ...staff, work_start_time: e.target.value })} /></label>
              <label>Office End Time<input type="time" required value={staff.work_end_time || '17:00'} onChange={(e) => setStaff({ ...staff, work_end_time: e.target.value })} /></label>
            </div>
            <label>Password <span className="optional-note">blank = keep current / Temp123! for new</span><input type="password" value={staff.password || ''} onChange={(e) => setStaff({ ...staff, password: e.target.value })} /></label>
            <div className="id-photo-template">
              <MovablePhotoPlaceholder preview={idPhotoPreview} offset={idPhotoOffset} setOffset={setIdPhotoOffset} onDropFile={(file) => handleIdPhotoChange({ target: { files: [file] } })} />
              <div className="id-photo-fields">
                <div className="id-photo-drag-card"><DragDropFileInput label={`ID Photo ${editing ? '(optional replacement)' : '(required for new staff)'}`} accept="image/png,image/jpeg,image/webp" file={idPhotoFile} onFile={(file) => handleIdPhotoChange({ target: { files: file ? [file] : [] } })} required={!editing} preview /></div>
                <p className="muted small">The uploaded photo is linked to the staff ID card and will print on attendance PDF exports.</p>
              </div>
            </div>
            {editing ? <label className="checkbox-row"><input type="checkbox" checked={staff.is_active !== false} onChange={(e) => setStaff({ ...staff, is_active: e.target.checked })} /> Active</label> : null}
            <div className="id-card-form-actions separate-actions">
              <button type="submit" className="primary-action">
                {editing ? 'Save Staff Member' : 'Create Staff Member'}
              </button>

              {editing ? (
                <button
                  type="button"
                  className="secondary-action"
                  onClick={() => downloadIdCards(editing.type, editing.id)}
                >
                  Download ID Card
                </button>
              ) : null}

              {editing ? (
                <button
                  type="button"
                  className="secondary-action"
                  onClick={resetForm}
                >
                  Cancel Edit
                </button>
              ) : null}
            </div>
          </form>
        </section>
      ) : null}

      {activeSubTab === 'qr' ? (
        <section className="form-card staff-list-card">
          <h2>Printable Office QR Codes</h2>
          <p className="muted">Print the QR code for each office. Employees scan the printed code from their mobile phone before signing in or out.</p>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Office</th><th>Address / Description</th><th>Radius</th><th>QR Payload</th><th>Action</th></tr></thead>
              <tbody>
                {officeQrs.map((office) => <tr key={office.id}>
                  <td>{office.name || `Office #${office.id}`}</td>
                  <td>{office.address || '—'}</td>
                  <td>{office.allowed_radius_m || 100} m</td>
                  <td><code>{office.qr_payload}</code></td>
                  <td>
                    <button type="button" onClick={() => printOfficeQr(office)}>
                      Download / Print QR
                    </button>

                    <button type="button" onClick={() => setSelectedOffice(office)}>
                      Set GPS
                    </button>
                  </td>
                </tr>)}
                {!officeQrs.length ? <tr><td colSpan="5" className="muted">No offices found. Add office areas first, then assign staff to those offices.</td></tr> : null}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {selectedOffice ? (
        <div className="card" style={{ marginTop: 20 }}>
          <h3>Set GPS location: {selectedOffice.name || `Office #${selectedOffice.id}`}</h3>

          <p className="muted">
            Click the map or drag the marker to set the office GPS point.
          </p>

          {myLocation && (
            <p>
              Your Location: {myLocation.latitude.toFixed(6)} / {myLocation.longitude.toFixed(6)}
            </p>
          )}

          <OfficeLocationMap
            office={selectedOffice}
            onPick={setPickedLocation}
          />

          {pickedLocation ? (
            <p>
              Lat: {pickedLocation.latitude.toFixed(6)} / Lng: {pickedLocation.longitude.toFixed(6)}
            </p>
          ) : null}

          <div style={{ display: 'flex', gap: '10px', marginTop: '10px' }}>
            <button type="button" onClick={saveOfficeLocation}>
              Save Office Location
            </button>

            <button
              type="button"
              onClick={() => {
                setSelectedOffice(null);
                setPickedLocation(null);
              }}
              className="secondary-action"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}
      
      {activeSubTab === 'view' ? (
        <>
          <StaffDetail title={viewTitle} item={viewItem} onClose={() => setViewItem(null)} onEdit={() => {
            if (viewTitle.includes('Employee')) editStaff('employees', viewItem)
            else editStaff('managers', viewItem)
          }} />

          <section className="form-card staff-list-card">
            <h2>My Managers</h2>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Name</th><th>Username</th><th>Email</th><th>Contact</th><th>Office</th><th>Office Hours</th><th>Active</th><th>Actions</th></tr></thead>
                <tbody>
                  {managers.filter((m) => m.is_active !== false && m.login_active !== false).map((m) => <tr key={m.id} className={m.is_active === false ? 'inactive-row' : ''}>
                    <td>{m.name} {m.surname}</td><td>{m.username || '—'}</td><td>{m.email || '—'}</td><td>{m.contact_number || '—'}</td><td>{m.office_name || m.office_address_assigned || '—'}</td><td>{m.work_start_time || '08:00'} - {m.work_end_time || '17:00'}</td><td>{m.is_active === false ? 'No' : 'Yes'}</td>
                    {renderActions('managers', m)}
                  </tr>)}
                  {!managers.length ? <tr><td colSpan="9" className="muted">No managers found.</td></tr> : null}
                </tbody>
              </table>
            </div>
          </section>

          <section className="form-card staff-list-card">
            <h2>My Employees</h2>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Role</th><th>EMPL. NO</th><th>Name</th><th>Username</th><th>Email</th><th>Contact</th><th>Office</th><th>Office Hours</th><th>Active</th><th>Actions</th></tr></thead>
                <tbody>
                  {employees.filter((e) => e.is_active !== false && e.login_active !== false).map((e) => <tr key={e.id} className={e.is_active === false ? 'inactive-row' : ''}>
                    <td>{e.employee_role || '—'}</td><td>{e.employee_number || '—'}</td><td>{e.name} {e.surname}</td><td>{e.username || '—'}</td><td>{e.email || '—'}</td><td>{e.contact_number || '—'}</td><td>{e.office_name || e.office_address_assigned || '—'}</td><td>{e.work_start_time || '08:00'} - {e.work_end_time || '17:00'}</td><td>{e.is_active === false ? 'No' : 'Yes'}</td>
                    {renderActions('employees', e)}
                  </tr>)}
                  {!employees.length ? <tr><td colSpan="9" className="muted">No employees found.</td></tr> : null}
                </tbody>
              </table>
            </div>
          </section>
        </>
      ) : null}
    </div>
  )
}
