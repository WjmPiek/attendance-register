import { useEffect, useMemo, useState } from 'react'
import {
  downloadOfficeQrPdf,
  getMyBusinessInformation,
  getOfficeQrCodes,
  regenerateOfficeQr,
  updateMyBusinessInformation,
  updateOfficeDetails,
  updateOfficeLocation,
  deleteOffice,
  getOfficeLinkedStaff,
  reassignOfficeLinkedStaff,
} from '../api/client'
import OfficeLocationMap from '../components/OfficeLocationMap'

const emptyForm = {
  franchise_name: '', business_name: '', trading_as: '', business_registration_number: '', vat_number: '',
  office_address: '', website: '', office_number: '', twenty_four_hour_number: '', contact_number: ''
}

const normalizeAddress = (value) => String(value || '').trim().toLowerCase().replace(/\s+/g, ' ')

export default function BusinessInformationPage() {
  const [form, setForm] = useState(emptyForm)
  const [office, setOffice] = useState(null)
  const [addressHistory, setAddressHistory] = useState([])
  const [allOffices, setAllOffices] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [regenerating, setRegenerating] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [pickedLocation, setPickedLocation] = useState(null)
  const [radius, setRadius] = useState(100)
  const [deleteDialog, setDeleteDialog] = useState(null)
  const [replacementAddress, setReplacementAddress] = useState('')

  const load = async () => {
    setLoading(true); setError('')
    try {
      const [data, offices] = await Promise.all([getMyBusinessInformation(), getOfficeQrCodes()])
      const nextForm = Object.fromEntries(Object.keys(emptyForm).map((key) => [key, data?.[key] || '']))
      setForm(nextForm)
      setAllOffices(offices || [])
      const businessAddress = normalizeAddress(nextForm.office_address)
      const activeOffices = (offices || []).filter((item) => !item.is_archived)
      const headOffice = activeOffices.find((item) => normalizeAddress(item.address) === businessAddress)
        || activeOffices[0]
        || null
      setOffice(headOffice)
      setAddressHistory((offices || []).filter((item) => item.is_archived))
      setRadius(headOffice?.allowed_radius_m || 100)
    } catch (err) { setError(err.message || 'Unable to load business information') }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const mapUrl = useMemo(() => form.office_address
    ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(form.office_address.trim())}`
    : '', [form.office_address])

  const change = (key) => (event) => setForm((current) => ({ ...current, [key]: event.target.value }))

  const save = async (event) => {
    event.preventDefault(); setSaving(true); setMessage(''); setError('')
    try {
      const saved = await updateMyBusinessInformation(form)
      setForm(Object.fromEntries(Object.keys(emptyForm).map((key) => [key, saved?.[key] || ''])))
      setMessage('Business information saved successfully. The Head Office QR remains linked to this address.')
      await load()
    } catch (err) { setError(err.message || 'Unable to save business information') }
    finally { setSaving(false) }
  }

  const saveOfficeSettings = async () => {
    if (!office) return
    setSaving(true); setMessage(''); setError('')
    try {
      await updateOfficeDetails(office.id, {
        name: form.business_name || form.franchise_name || 'Business',
        address: form.office_address,
        allowed_radius_m: Number(radius || 100),
      })
      if (pickedLocation) {
        await updateOfficeLocation(office.id, {
          latitude: pickedLocation.latitude,
          longitude: pickedLocation.longitude,
          allowed_radius_m: Number(radius || 100),
        })
      }
      setMessage('Head Office GPS and attendance radius saved.')
      setPickedLocation(null)
      await load()
    } catch (err) { setError(err.message || 'Unable to save Head Office settings') }
    finally { setSaving(false) }
  }

  const downloadQr = async () => {
    if (!office) return
    setError(''); setMessage('')
    try {
      const blob = await downloadOfficeQrPdf(office.id)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${form.business_name || form.franchise_name || 'head_office'}_attendance_qr.pdf`.replace(/[^a-z0-9_.-]+/gi, '_')
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
      setMessage('Professional A4 Head Office QR PDF downloaded.')
    } catch (err) { setError(err.message || 'Unable to download QR PDF') }
  }

  const generateNewQr = async () => {
    if (!office) return
    const confirmed = window.confirm('Generate a new QR code? The current printed QR code will immediately stop working. The business address, GPS point and attendance radius will remain unchanged.')
    if (!confirmed) return
    setRegenerating(true); setError(''); setMessage('')
    try {
      await regenerateOfficeQr(office.id)
      setMessage('New Head Office QR code generated. The previous QR code is now invalid.')
      await load()
    } catch (err) { setError(err.message || 'Unable to generate a new QR code') }
    finally { setRegenerating(false) }
  }


  const beginDeleteOffice = async () => {
    if (!office) return
    setError(''); setMessage('')
    try {
      const linked = await getOfficeLinkedStaff(office.id)
      setDeleteDialog(linked)
      setReplacementAddress('')
    } catch (err) { setError(err.message || 'Unable to check linked staff') }
  }

  const confirmDeleteOffice = async () => {
    if (!office || !deleteDialog) return
    setSaving(true); setError(''); setMessage('')
    try {
      if (deleteDialog.count > 0) {
        if (!replacementAddress.trim()) throw new Error('Enter the new address for all linked employees and managers first.')
        await reassignOfficeLinkedStaff(office.id, replacementAddress.trim())
      }
      await deleteOffice(office.id)
      setDeleteDialog(null)
      setMessage('The old address was archived, not deleted. Linked staff were moved to the replacement address and all historical records remain available.')
      await load()
    } catch (err) { setError(err.message || 'Unable to delete office address') }
    finally { setSaving(false) }
  }

  const editRegisteredAddress = async (item) => {
    const nextAddress = window.prompt('Edit registered address:', item.address || '')
    if (nextAddress === null || !nextAddress.trim()) return
    const nextName = window.prompt('Business / office name:', item.name || form.business_name || form.franchise_name || 'Business')
    if (nextName === null) return
    setSaving(true); setError(''); setMessage('')
    try {
      await updateOfficeDetails(item.id, { name: nextName.trim() || 'Business', address: nextAddress.trim(), allowed_radius_m: Number(item.allowed_radius_m || 100) })
      if (!item.is_archived && office?.id === item.id) {
        await updateMyBusinessInformation({ ...form, office_address: nextAddress.trim() })
      }
      setMessage('Registered address updated throughout the office record.')
      await load()
    } catch (err) { setError(err.message || 'Unable to edit registered address') }
    finally { setSaving(false) }
  }

  const selectAddressForArchive = async (item) => {
    if (item.is_archived) return
    setOffice(item)
    setRadius(item.allowed_radius_m || 100)
    try {
      const linked = await getOfficeLinkedStaff(item.id)
      setDeleteDialog(linked)
      setReplacementAddress('')
    } catch (err) { setError(err.message || 'Unable to check linked staff') }
  }

  if (loading) return <section className="form-card"><p>Loading business information...</p></section>

  return (
    <div className="business-information-page">
      <section className="form-card business-info-hero">
        <div><p className="eyebrow">Franchise profile</p><h1>Business Information</h1><p className="muted">Manage the business profile, Head Office GPS and the single active attendance QR code. This page is visible only to the franchise user.</p></div>
        {mapUrl ? <a className="glass-button" href={mapUrl} target="_blank" rel="noreferrer">Open address in Google Maps</a> : null}
      </section>

      <form className="form-card business-info-form" onSubmit={save}>
        {error ? <p className="error">{error}</p> : null}
        {message ? <p className="success-message">{message}</p> : null}
        <div className="form-grid two-column-grid">
          <label>Franchise name<input value={form.franchise_name} onChange={change('franchise_name')} /></label>
          <label>Registered business name<input value={form.business_name} onChange={change('business_name')} /></label>
          <label>Trading as<input value={form.trading_as} onChange={change('trading_as')} /></label>
          <label>Registration number<input value={form.business_registration_number} onChange={change('business_registration_number')} /></label>
          <label>VAT number<input value={form.vat_number} onChange={change('vat_number')} /></label>
          <label>Website<input value={form.website} onChange={change('website')} placeholder="https://example.co.za" /></label>
          <label>Office number<input value={form.office_number} onChange={change('office_number')} /></label>
          <label>24-hour number<input value={form.twenty_four_hour_number} onChange={change('twenty_four_hour_number')} /></label>
          <label>Primary contact number<input value={form.contact_number} onChange={change('contact_number')} /></label>
          <label className="full-width-field">Business address<textarea rows="4" value={form.office_address} onChange={change('office_address')} placeholder="Street, suburb, city, province, postal code, South Africa" /></label>
        </div>
        <div className="button-row"><button type="submit" disabled={saving}>{saving ? 'Saving...' : 'Save all business information'}</button><button type="button" className="glass-button" onClick={load} disabled={saving}>Reset</button></div>
      </form>

      <section className="form-card registered-addresses-card">
        <div><p className="eyebrow">Address register</p><h2>All Registered Addresses</h2><p className="muted">Active and historical addresses remain visible. Deleting an active address archives it after linked staff are reassigned.</p></div>
        <div className="table-wrap"><table><thead><tr><th>Business / Office</th><th>Address</th><th>Status</th><th>Actions</th></tr></thead><tbody>
          {allOffices.map((item) => { const maps = item.address ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(item.address)}` : ''; return <tr key={item.id}><td><strong>{item.name || form.business_name || form.franchise_name || 'Business'}</strong></td><td>{item.address || '—'}</td><td><span className={`status-pill ${item.is_archived ? 'declined' : 'approved'}`}>{item.is_archived ? 'Archived' : 'Active'}</span></td><td><div className="action-row">{maps ? <a className="link-button" href={maps} target="_blank" rel="noreferrer">View (Google Maps)</a> : null}<button type="button" className="link-button" onClick={() => editRegisteredAddress(item)}>Edit</button><button type="button" className="link-button danger" disabled={item.is_archived} title={item.is_archived ? 'Historical records are retained permanently' : 'Reassign linked staff and archive this address'} onClick={() => selectAddressForArchive(item)}>{item.is_archived ? 'Retained' : 'Delete'}</button></div></td></tr> })}
          {!allOffices.length ? <tr><td colSpan="4" className="muted">No registered addresses found.</td></tr> : null}
        </tbody></table></div>
      </section>

      <section className="form-card business-map-card">
        <div><h2>Head Office GPS and attendance radius</h2><p className="muted">All employees, agents and managers assigned to the business address use this one Head Office QR code.</p><strong>{form.office_address || 'No business address saved yet.'}</strong></div>
        {office ? <>
          <OfficeLocationMap office={{ ...office, address: form.office_address }} onPick={setPickedLocation} />
          <div className="form-grid two-column-grid business-qr-settings">
            <label>Attendance radius (metres)<input type="number" min="10" value={radius} onChange={(event) => setRadius(event.target.value)} /></label>
            <div className="business-qr-status"><span className="muted small">Current QR status</span><strong>{office.qr_enabled === false ? 'Inactive' : 'Active'}</strong></div>
          </div>
          {pickedLocation ? <p className="muted small">Selected GPS: {pickedLocation.latitude.toFixed(6)}, {pickedLocation.longitude.toFixed(6)}</p> : null}
          <div className="button-row"><button type="button" onClick={saveOfficeSettings} disabled={saving}>Save GPS and radius</button><button type="button" className="danger-button" onClick={beginDeleteOffice} disabled={saving}>Replace and archive address</button></div>
        </> : <p className="muted">Save a complete business address first. The system will create the single Head Office QR location automatically.</p>}
      </section>


      <section className="form-card business-address-history-card">
        <div><p className="eyebrow">Permanent record</p><h2>Previous Business Addresses</h2><p className="muted">Old addresses are retained permanently for audit and attendance history. Archived QR codes remain invalid and cannot be used for attendance.</p></div>
        {addressHistory.length ? <div className="linked-staff-list">
          {addressHistory.map((item) => <div className="linked-staff-row" key={item.id}>
            <div><strong>{item.name || form.business_name || form.franchise_name || 'Business'}</strong><span>{item.address || 'No address recorded'}</span></div>
            <span className="status-chip">Archived{item.archived_at ? ` · ${new Date(item.archived_at).toLocaleDateString()}` : ''}</span>
          </div>)}
        </div> : <p className="muted">No previous business addresses have been archived.</p>}
      </section>

      <section className="form-card business-qr-card">
        <div><p className="eyebrow">Attendance QR</p><h2>Head Office QR Management</h2><p className="muted">There is one active QR code for the business address. Registered staff assigned to this address scan the same code to open the sign-in or sign-out page.</p></div>
        {office ? <div className="business-qr-actions">
          <button type="button" onClick={downloadQr}>Download professional A4 QR</button>
          <button type="button" className="secondary-action" onClick={generateNewQr} disabled={regenerating}>{regenerating ? 'Generating...' : 'Generate New QR Code'}</button>
          <p className="muted small">Generating a new code invalidates every previously printed copy immediately. The address, GPS coordinates and radius are preserved.</p>
        </div> : <p className="muted">No Head Office QR is available until the business address is saved.</p>}
      </section>
      {deleteDialog ? <div className="modal-backdrop"><section className="form-card office-delete-modal"><h2>Staff linked to this address</h2><p className="muted">Every linked employee, agent and manager must receive a replacement address before this address is archived. No historical records will be deleted.</p><div className="linked-staff-list">{deleteDialog.items?.length ? deleteDialog.items.map((item) => <div className="linked-staff-row" key={`${item.staff_type}-${item.staff_id}`}><strong>{item.full_name || item.employee_number}</strong><span>{item.staff_type} · {item.employee_number || 'No employee number'}</span></div>) : <p>No active staff are linked to this office.</p>}</div>{deleteDialog.count > 0 ? <label>Replacement address for all linked staff<textarea rows="3" value={replacementAddress} onChange={(e) => setReplacementAddress(e.target.value)} placeholder="Street, suburb, city, province, postal code" /></label> : null}<div className="button-row"><button type="button" className="danger-button" onClick={confirmDeleteOffice} disabled={saving}>{saving ? 'Updating...' : 'Update staff and archive address'}</button><button type="button" className="glass-button" onClick={() => setDeleteDialog(null)} disabled={saving}>Cancel</button></div></section></div> : null}
    </div>
  )
}
