import { useEffect, useMemo, useState } from 'react'
import { getMyBusinessInformation, updateMyBusinessInformation } from '../api/client'

const emptyForm = {
  franchise_name: '', business_name: '', trading_as: '', business_registration_number: '', vat_number: '',
  office_address: '', website: '', office_number: '', twenty_four_hour_number: '', contact_number: ''
}

export default function BusinessInformationPage() {
  const [form, setForm] = useState(emptyForm)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const load = async () => {
    setLoading(true); setError('')
    try {
      const data = await getMyBusinessInformation()
      setForm(Object.fromEntries(Object.keys(emptyForm).map((key) => [key, data?.[key] || ''])))
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
      setMessage('Business information saved successfully.')
    } catch (err) { setError(err.message || 'Unable to save business information') }
    finally { setSaving(false) }
  }

  if (loading) return <section className="form-card"><p>Loading business information...</p></section>

  return (
    <div className="business-information-page">
      <section className="form-card business-info-hero">
        <div><p className="eyebrow">Franchise profile</p><h1>Business Information</h1><p className="muted">Keep your legal, contact and location details up to date. This page is visible only to the franchise user.</p></div>
        {mapUrl ? <a className="glass-button" href={mapUrl} target="_blank" rel="noreferrer">Open correct address in Google Maps</a> : null}
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
        <div><h2>Google Maps address</h2><p className="muted">The map link uses the complete saved address instead of stale or incorrect coordinates.</p><strong>{form.office_address || 'No business address saved yet.'}</strong></div>
        {mapUrl ? <iframe title="Business location" loading="lazy" referrerPolicy="no-referrer-when-downgrade" src={`https://www.google.com/maps?q=${encodeURIComponent(form.office_address)}&output=embed`} /> : null}
      </section>
    </div>
  )
}
