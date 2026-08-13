import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  getMyBusinessInformation,
  getOfficeQrCodes,
  downloadOfficeQrPdf,
  regenerateOfficeQr,
  updateMyBusinessInformation,
  updateOfficeDetails,
  updateOfficeLocation,
  deleteOffice,
  getOfficeLinkedStaff,
  reassignOfficeLinkedStaff,
  createOffice,
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
  const [allOffices, setAllOffices] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [regenerating, setRegenerating] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [pickedLocation, setPickedLocation] = useState(null)
  const [gpsConfirmed, setGpsConfirmed] = useState(false)
  const [editingGps, setEditingGps] = useState(false)
  const [radius, setRadius] = useState(100)
  const [deleteDialog, setDeleteDialog] = useState(null)
  const [replacementAreaId, setReplacementAreaId] = useState('')
  const [newOffice, setNewOffice] = useState({ name: '', address: '', allowed_radius_m: 100 })

  const load = async () => {
    setLoading(true); setError('')
    try {
      const [data, offices] = await Promise.all([getMyBusinessInformation(), getOfficeQrCodes()])
      const nextForm = Object.fromEntries(Object.keys(emptyForm).map((key) => [key, data?.[key] || '']))
      setForm(nextForm)
      setAllOffices((offices || []).filter((item) => !item.is_archived))
      const businessAddress = normalizeAddress(nextForm.office_address)
      const activeOffices = (offices || []).filter((item) => !item.is_archived)
      const headOffice = activeOffices.find((item) => normalizeAddress(item.address) === businessAddress)
        || activeOffices[0]
        || null
      setOffice(headOffice)
      setRadius(headOffice?.allowed_radius_m || 100)
      setEditingGps(!(headOffice?.latitude != null && headOffice?.longitude != null))
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
      if (pickedLocation && !gpsConfirmed) {
        throw new Error('Confirm that the proposed GPS marker is the physical office entrance before saving.')
      }
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
      setGpsConfirmed(false)
      await load()
      setEditingGps(false)
    } catch (err) { setError(err.message || 'Unable to save Head Office settings') }
    finally { setSaving(false) }
  }

  const handleOfficePick = useCallback((location) => {
    setPickedLocation(location)
    setGpsConfirmed(false)
  }, [])

  const generateNewQr = async (targetOffice = office) => {
    if (!targetOffice) return
    const confirmed = window.confirm('Issue a new four-digit fallback code now? The current fallback code will immediately stop working. The permanent printed QR will not change.')
    if (!confirmed) return
    setRegenerating(true); setError(''); setMessage('')
    try {
      await regenerateOfficeQr(targetOffice.id)
      setMessage('New four-digit fallback code issued. It expires after 20 minutes. The permanent office QR is unchanged.')
      await load()
    } catch (err) { setError(err.message || 'Unable to generate a new QR code') }
    finally { setRegenerating(false) }
  }

  const printOfficeQr = async (targetOffice = office) => {
    if (!targetOffice) return
    try {
      const blob = await downloadOfficeQrPdf(targetOffice.id)
      const url = URL.createObjectURL(blob)
      window.open(url, '_blank', 'noopener,noreferrer')
      window.setTimeout(() => URL.revokeObjectURL(url), 60000)
    } catch (err) {
      setError(err.message || 'Unable to open the Head Office QR code PDF')
    }
  }


  const beginDeleteOffice = async () => {
    if (!office) return
    setError(''); setMessage('')
    try {
      const linked = await getOfficeLinkedStaff(office.id)
      setDeleteDialog(linked)
      setReplacementAreaId('')
    } catch (err) { setError(err.message || 'Unable to check linked staff') }
  }

  const confirmDeleteOffice = async () => {
    if (!office || !deleteDialog) return
    setSaving(true); setError(''); setMessage('')
    try {
      if (deleteDialog.count > 0) {
        const replacementOffice = allOffices.find((item) => String(item.id) === String(replacementAreaId) && Number(item.id) !== Number(office.id))
        if (!replacementOffice) throw new Error('Select one of the active registered franchise addresses first.')
        await reassignOfficeLinkedStaff(office.id, replacementOffice)
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


  const addOffice = async (event) => {
    event.preventDefault(); setSaving(true); setError(''); setMessage('')
    try {
      await createOffice({ ...newOffice, allowed_radius_m: Number(newOffice.allowed_radius_m || 100) })
      setNewOffice({ name: '', address: '', allowed_radius_m: 100 })
      setMessage('Additional office address added. It is now available for staff assignment and QR attendance.')
      await load()
    } catch (err) { setError(err.message || 'Unable to add office address') }
    finally { setSaving(false) }
  }
  const selectAddressForArchive = async (item) => {
    if (item.is_archived) return
    setOffice(item)
    setRadius(item.allowed_radius_m || 100)
    try {
      const linked = await getOfficeLinkedStaff(item.id)
      setDeleteDialog(linked)
      setReplacementAreaId('')
    } catch (err) { setError(err.message || 'Unable to check linked staff') }
  }

  if (loading) return <section className="form-card"><p>Loading business information...</p></section>

  return (
    <div className="business-information-page">
      <section className="form-card business-info-hero">
        <div><p className="eyebrow">Franchise profile</p><h1>Business Information</h1><p className="muted">Manage the business profile, office GPS locations, permanent reception QR codes and timed four-digit fallback codes. This page is visible only to the franchise user.</p></div>
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

      <form className="form-card" onSubmit={addOffice}>
        <div><p className="eyebrow">Additional location</p><h2>Add Office Address</h2></div>
        <div className="form-grid two-column-grid">
          <label>Office name<input required value={newOffice.name} onChange={(e) => setNewOffice((v) => ({ ...v, name: e.target.value }))} /></label>
          <label>Attendance radius (metres)<input type="number" min="10" value={newOffice.allowed_radius_m} onChange={(e) => setNewOffice((v) => ({ ...v, allowed_radius_m: e.target.value }))} /></label>
          <label className="full-width-field">Office address<textarea required rows="3" value={newOffice.address} onChange={(e) => setNewOffice((v) => ({ ...v, address: e.target.value }))} /></label>
        </div>
        <button type="submit" disabled={saving}>{saving ? 'Adding...' : 'Add additional office address'}</button>
      </form>

      <section className="form-card registered-addresses-card">
        <div><p className="eyebrow">Address register</p><h2>All Registered Addresses</h2><p className="muted">Only active franchise addresses are shown. Deleted addresses remain preserved in the database for audit history but are hidden from the system.</p></div>
        <div className="table-wrap"><table><thead><tr><th>Business / Office</th><th>Address</th><th>Status</th><th>Actions</th></tr></thead><tbody>
          {allOffices.filter((item) => !item.is_archived).map((item) => { const maps = item.address ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(item.address)}` : ''; return <tr key={item.id}><td><strong>{item.name || form.business_name || form.franchise_name || 'Business'}</strong></td><td>{item.address || '—'}</td><td><span className={`status-pill ${item.is_archived ? 'declined' : 'approved'}`}>{item.is_archived ? 'Archived' : 'Active'}</span></td><td><div className="action-row">{maps ? <a className="link-button" href={maps} target="_blank" rel="noreferrer">View (Google Maps)</a> : null}<button type="button" className="link-button" onClick={() => editRegisteredAddress(item)}>Edit</button><button type="button" className="link-button danger" disabled={item.is_archived} title={item.is_archived ? 'Historical records are retained permanently' : 'Reassign linked staff and archive this address'} onClick={() => selectAddressForArchive(item)}>{item.is_archived ? 'Retained' : 'Delete'}</button></div></td></tr> })}
          {!allOffices.length ? <tr><td colSpan="4" className="muted">No registered addresses found.</td></tr> : null}
        </tbody></table></div>
      </section>

      <section className="form-card business-map-card">
        <div><h2>Head Office GPS and attendance radius</h2><p className="muted">Employees scan the permanent reception QR. If they cannot scan it, they can ask their manager or franchise user for the current timed four-digit code.</p><strong>{form.office_address || 'No business address saved yet.'}</strong></div>
        {office && !editingGps && office.latitude != null && office.longitude != null ? (
          <div className="status-panel">
            <p className="success"><strong>Head Office GPS is saved.</strong></p>
            <p className="muted small">Entrance: {Number(office.latitude).toFixed(6)}, {Number(office.longitude).toFixed(6)} · Attendance radius: {office.allowed_radius_m || 100} m</p>
            <button type="button" className="glass-button" onClick={() => setEditingGps(true)}>Edit GPS and radius</button>
          </div>
        ) : office ? <>
          <OfficeLocationMap office={{ ...office, address: form.office_address }} onPick={handleOfficePick} />
          <div className="form-grid two-column-grid business-qr-settings">
            <label>Attendance radius (metres)<input type="number" min="10" value={radius} onChange={(event) => setRadius(event.target.value)} /></label>
            <div className="business-qr-status"><span className="muted small">Manager/franchise code</span><strong>{office.qr_payload || 'Unavailable'}</strong><span className="muted small">Single use · maximum 20 minutes</span></div>
          </div>
          {pickedLocation ? <p className="muted small">Selected GPS: {pickedLocation.latitude.toFixed(6)}, {pickedLocation.longitude.toFixed(6)}</p> : null}
          {office.latitude != null && office.longitude != null ? <p className="muted small">Previously saved GPS: {Number(office.latitude).toFixed(6)}, {Number(office.longitude).toFixed(6)}</p> : null}
          <label className="user-check"><input type="checkbox" checked={gpsConfirmed} onChange={(event) => setGpsConfirmed(event.target.checked)} /><span>I confirmed this marker is the physical Head Office entrance.</span></label>
          <div className="button-row"><button type="button" onClick={saveOfficeSettings} disabled={saving || !gpsConfirmed}>Save GPS and radius</button>{office.latitude != null && office.longitude != null ? <button type="button" className="glass-button" onClick={() => { setEditingGps(false); setPickedLocation(null); setGpsConfirmed(false) }}>Cancel edit</button> : null}<button type="button" className="danger-button" onClick={beginDeleteOffice} disabled={saving}>Replace and archive address</button></div>
        </> : <p className="muted">Save a complete business address first. The system will create the Head Office attendance location automatically.</p>}
      </section>


      <section className="form-card business-qr-card">
        <div><p className="eyebrow">Office attendance QR codes</p><h2>Permanent Office QR Codes</h2><p className="muted">Print and place the QR for each address at reception. These QR codes are permanently linked to their office addresses and do not expire. The separate four-digit fallback code expires after 20 minutes.</p></div>
        {allOffices.length ? <div className="office-qr-list">
          {allOffices.map((item) => <article className="office-qr-item" key={`office-qr-${item.id}`}>
            <div><h3>{item.name || 'Office'}</h3><p className="muted small">{item.address || 'Address not captured'}</p></div>
            {item.qr_image_url ? <img className="office-attendance-qr" src={item.qr_image_url} alt={`Permanent attendance QR code for ${item.name || 'office'}`} /> : <p className="error">QR image unavailable</p>}
            <p className="success small"><strong>Permanent QR:</strong> does not expire</p>
            <p className="muted small">Current four-digit fallback: <strong>{item.qr_payload || 'Unavailable'}</strong> · expires {item.qr_valid_until ? new Date(item.qr_valid_until).toLocaleTimeString('en-ZA', { hour: '2-digit', minute: '2-digit' }) : 'within 20 minutes'}.</p>
            <div className="button-row">
              {item.qr_image_url ? <button type="button" className="glass-button" onClick={() => printOfficeQr(item)}>Print permanent QR</button> : null}
              <button type="button" onClick={() => generateNewQr(item)} disabled={regenerating}>{regenerating ? 'Issuing...' : 'Issue new fallback code'}</button>
            </div>
          </article>)}
        </div> : <p className="muted">No office attendance QR is available until an office address is saved.</p>}
      </section>
      {deleteDialog ? <div className="modal-backdrop"><section className="form-card office-delete-modal"><h2>Staff linked to this address</h2><p className="muted">Every linked employee, agent and manager must receive a replacement address before this address is archived. No historical records will be deleted.</p><div className="linked-staff-list">{deleteDialog.items?.length ? deleteDialog.items.map((item) => <div className="linked-staff-row" key={`${item.staff_type}-${item.staff_id}`}><strong>{item.full_name || item.employee_number}</strong><span>{item.staff_type} · {item.employee_number || 'No employee number'}</span></div>) : <p>No active staff are linked to this office.</p>}</div>{deleteDialog.count > 0 ? <label>Replacement registered address<select value={replacementAreaId} onChange={(e) => setReplacementAreaId(e.target.value)}><option value="">Select an active franchise address</option>{allOffices.filter((item) => !item.is_archived && Number(item.id) !== Number(office?.id)).map((item) => <option key={item.id} value={item.id}>{item.name || 'Business'} — {item.address}</option>)}</select></label> : null}<div className="button-row"><button type="button" className="danger-button" onClick={confirmDeleteOffice} disabled={saving}>{saving ? 'Updating...' : 'Update staff and archive address'}</button><button type="button" className="glass-button" onClick={() => setDeleteDialog(null)} disabled={saving}>Cancel</button></div></section></div> : null}
    </div>
  )
}
