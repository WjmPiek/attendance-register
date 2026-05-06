import { useEffect, useState } from 'react'
import Card from '../components/Card'
import { getAttendanceStatus, submitAttendance, validateOfficeQr } from '../api/client'
import SignaturePad from '../components/SignaturePad'
import DigitalIdCard from '../components/DigitalIdCard'

export default function MobileAttendancePage({ me }) {
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [workLocationType, setWorkLocationType] = useState('office')
  const [employeeNote, setEmployeeNote] = useState('')
  const [signatureValue, setSignatureValue] = useState('')
  const [qrValue, setQrValue] = useState('')
  const [qrOffice, setQrOffice] = useState(null)
  const [scanning, setScanning] = useState(false)

  const loadStatus = async () => {
    try {
      const data = await getAttendanceStatus()
      setStatus(data)
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => {
    loadStatus()
  }, [])

  const getLocation = () => new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error('GPS is not available on this device/browser.'))
      return
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({
        latitude: pos.coords.latitude,
        longitude: pos.coords.longitude,
        accuracy: pos.coords.accuracy,
      }),
      () => reject(new Error('GPS permission is required. Please allow location access.')),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
    )
  })

  const validateQr = async (value) => {
    if (!value?.trim()) throw new Error('Please scan or enter the office QR code first.')
    const office = await validateOfficeQr(value.trim())
    setQrOffice(office)
    setQrValue(office.qr_payload || value.trim())
    return office
  }

  const startQrScan = async () => {
    setError('')
    setMessage('')
    if (!('BarcodeDetector' in window)) {
      setError('This browser does not support camera QR scanning. Type or paste the QR code into the manual field below.')
      return
    }
    let stream
    try {
      setScanning(true)
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
      const video = document.createElement('video')
      video.srcObject = stream
      video.setAttribute('playsinline', 'true')
      await video.play()
      const detector = new window.BarcodeDetector({ formats: ['qr_code'] })
      const deadline = Date.now() + 20000
      while (Date.now() < deadline) {
        const codes = await detector.detect(video).catch(() => [])
        if (codes.length) {
          const raw = codes[0].rawValue || ''
          await validateQr(raw)
          setMessage('Office QR scanned and linked.')
          return
        }
        await new Promise((resolve) => setTimeout(resolve, 350))
      }
      throw new Error('No QR code detected. Try again closer to the printed code, or enter it manually.')
    } catch (err) {
      setError(err.message || 'QR scan failed')
    } finally {
      if (stream) stream.getTracks().forEach((track) => track.stop())
      setScanning(false)
    }
  }

  const handleAction = async (action) => {
    setLoading(true)
    setError('')
    setMessage('')
    try {
      if (!signatureValue) throw new Error('Signature is required before sign in/out.')
      if (workLocationType === 'office' && !qrOffice) {
        await validateQr(qrValue)
      }
      if (workLocationType === 'on_road' && !employeeNote.trim()) {
        throw new Error('Please enter a road-work reason/note.')
      }
      const location = await getLocation()
      const payload = {
        ...location,
        device_info: navigator.userAgent,
        signature_value: signatureValue,
        work_location_type: workLocationType,
        employee_note: employeeNote.trim() || null,
        qr_value: workLocationType === 'office' ? qrValue : null,
      }
      const result = await submitAttendance(action, payload)
      setMessage(result.message)
      await loadStatus()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card title="Mobile Employee Attendance">
      <DigitalIdCard />
      <p className="muted">Sign in/out with GPS and signature. Choose On road when working away from the assigned office.</p>
      <div className="status-panel">
        <div><strong>User:</strong> {me.full_name}</div>
        <div><strong>Status:</strong> {status?.current_status || 'loading'}</div>
        <div><strong>Last action:</strong> {status?.last_action || 'none'}</div>
        <div><strong>Last time:</strong> {status?.last_action_at || 'n/a'}</div>
      </div>

      <div className="history-toolbar one-column">
        <label>
          Work location
          <select value={workLocationType} onChange={(event) => setWorkLocationType(event.target.value)}>
            <option value="office">Assigned office / area</option>
            <option value="on_road">On the road / field work</option>
          </select>
        </label>
        <label>
          Employee note {workLocationType === 'on_road' ? '(required)' : '(optional)'}
          <textarea value={employeeNote} onChange={(event) => setEmployeeNote(event.target.value)} placeholder="Example: client visit, delivery, field work" />
        </label>
      </div>

      <div className="qr-scan-card">
        <div className="detail-header">
          <div>
            <h3>Office QR code</h3>
            <p className="muted small">Scan the printed office QR code before signing in or out. This links the attendance record to the office address.</p>
          </div>
          <button type="button" onClick={startQrScan} disabled={scanning || workLocationType !== 'office'}>
            {scanning ? 'Scanning...' : 'Scan QR'}
          </button>
        </div>
        <label>
          Manual QR code entry
          <input value={qrValue} onChange={(event) => { setQrValue(event.target.value); setQrOffice(null) }} placeholder="ARP-OFFICE:..." disabled={workLocationType !== 'office'} />
        </label>
        <button type="button" className="secondary-action" onClick={() => validateQr(qrValue).then(() => setMessage('Office QR linked.')).catch((err) => setError(err.message))} disabled={workLocationType !== 'office'}>Validate QR</button>
        {qrOffice ? <p className="success">Linked to {qrOffice.office_name || 'office'} · {qrOffice.address || 'No address captured'}</p> : null}
        {workLocationType === 'on_road' ? <p className="muted small">QR scan is not required for on-road work, but the note is required and goes for approval.</p> : null}
      </div>

      <SignaturePad onChange={setSignatureValue} />

      <div className="mobile-actions">
        <button disabled={loading || status?.current_status === 'signed_in'} onClick={() => handleAction('sign-in')}>
          {loading ? 'Working...' : 'Sign in'}
        </button>
        <button className="danger" disabled={loading || status?.current_status !== 'signed_in'} onClick={() => handleAction('sign-out')}>
          {loading ? 'Working...' : 'Sign out'}
        </button>
      </div>
      <p className="muted small">GPS and signature are recorded for office and on-road events. On-road events go to approval review.</p>
      {message ? <p className="success">{message}</p> : null}
      {error ? <p className="error">{error}</p> : null}
    </Card>
  )
}
