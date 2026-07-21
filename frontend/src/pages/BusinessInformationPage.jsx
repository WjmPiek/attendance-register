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
      const businessAddress = normalizeAddress(nextForm.office_address)
      const headOffice = (offices || []).find((item) => normalizeAddress(item.address) === businessAddress)
        || (offices || []).find((item) => String(item.name || '').toLowerCase().includes('head office'))
        || null
      setOffice(headOffice)
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
        name: `${form.business_name || form.franchise_name || 'Head Office'} - Head Office`,
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
      setMessage('Office address deleted. Linked staff were moved to the replacement address.')
      await load()
    } catch (err) { setError(err.message || 'Unable to delete office address') }
    finally { setSaving(false) }
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

      <section className="form-card business-map-card">
        <div><h2>Head Office GPS and attendance radius</h2><p className="muted">All employees, agents and managers assigned to the business address use this one Head Office QR code.</p><strong>{form.office_address || 'No business address saved yet.'}</strong></div>
        {office ? <>
          <OfficeLocationMap office={{ ...office, address: form.office_address }} onPick={setPickedLocation} />
          <div className="form-grid two-column-grid business-qr-settings">
            <label>Attendance radius (metres)<input type="number" min="10" value={radius} onChange={(event) => setRadius(event.target.value)} /></label>
            <div className="business-qr-status"><span className="muted small">Current QR status</span><strong>{office.qr_enabled === false ? 'Inactive' : 'Active'}</strong></div>
          </div>
          {pickedLocation ? <p className="muted small">Selected GPS: {pickedLocation.latitude.toFixed(6)}, {pickedLocation.longitude.toFixed(6)}</p> : null}
          <div className="button-row"><button type="button" onClick={saveOfficeSettings} disabled={saving}>Save GPS and radius</button><button type="button" className="danger-button" onClick={beginDeleteOffice} disabled={saving}>Delete office address</button></div>
        </> : <p className="muted">Save a complete business address first. The system will create the single Head Office QR location automatically.</p>}
      </section>

      <section className="form-card business-qr-card">
        <div><p className="eyebrow">Attendance QR</p><h2>Head Office QR Management</h2><p className="muted">There is one active QR code for the business address. Registered staff assigned to this address scan the same code to open the sign-in or sign-out page.</p></div>
        {office ? <div className="business-qr-actions">
          <button type="button" onClick={downloadQr}>Download professional A4 QR</button>
          <button type="button" className="secondary-action" onClick={generateNewQr} disabled={regenerating}>{regenerating ? 'Generating...' : 'Generate New QR Code'}</button>
          <p className="muted small">Generating a new code invalidates every previously printed copy immediately. The address, GPS coordinates and radius are preserved.</p>
        </div> : <p className="muted">No Head Office QR is available until the business address is saved.</p>}
      </section>
      {deleteDialog ? <div className="modal-backdrop"><section className="form-card office-delete-modal"><h2>Employees linked to this address</h2><p className="muted">Every linked employee and manager must receive a replacement address before this office can be deleted.</p><div className="linked-staff-list">{deleteDialog.items?.length ? deleteDialog.items.map((item) => <div className="linked-staff-row" key={`${item.staff_type}-${item.staff_id}`}><strong>{item.full_name || item.employee_number}</strong><span>{item.staff_type} · {item.employee_number || 'No employee number'}</span></div>) : <p>No active staff are linked to this office.</p>}</div>{deleteDialog.count > 0 ? <label>Replacement address for all linked staff<textarea rows="3" value={replacementAddress} onChange={(e) => setReplacementAddress(e.target.value)} placeholder="Street, suburb, city, province, postal code" /></label> : null}<div className="button-row"><button type="button" className="danger-button" onClick={confirmDeleteOffice} disabled={saving}>{saving ? 'Updating...' : 'Update staff and delete office'}</button><button type="button" className="glass-button" onClick={() => setDeleteDialog(null)} disabled={saving}>Cancel</button></div></section></div> : null}
    </div>
  )
}
