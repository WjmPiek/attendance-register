import { useEffect, useRef, useState } from 'react'
import Card from '../components/Card'
import { getAttendanceStatus, submitAttendance, validateOfficeQr } from '../api/client'
import SignaturePad from '../components/SignaturePad'
import { getDistance } from '../utils/distance'

function officeCodeFromScan(rawValue) {
  const raw = String(rawValue || '').trim()
  if (/^\d{4}$/.test(raw)) return raw
  try {
    const url = new URL(raw)
    const linkedCode = url.searchParams.get('office_qr')
    return /^\d{4}$/.test(linkedCode || '') ? linkedCode : ''
  } catch {
    const match = raw.match(/(?:office_qr=)?(\d{4})(?:\D|$)/)
    return match?.[1] || ''
  }
}

export default function MobileAttendancePage({ me, onDone }) {
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [workLocationType, setWorkLocationType] = useState('office')
  const [employeeNote, setEmployeeNote] = useState('')
  const [signatureValue, setSignatureValue] = useState('')
  const [qrValue, setQrValue] = useState(() => new URLSearchParams(window.location.search).get('office_qr') || '')
  const [qrOffice, setQrOffice] = useState(null)
  const [manualCodeEntry, setManualCodeEntry] = useState(false)
  const [evidenceReady, setEvidenceReady] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [cameraOpen, setCameraOpen] = useState(false)
  const [cameraStream, setCameraStream] = useState(null)
  const [photoPreview, setPhotoPreview] = useState('')
  const videoRef = useRef(null)

  const loadStatus = async () => {
    try {
      const data = await getAttendanceStatus()
      setStatus(data)
    } catch (err) {
      setMessage('')
      setError(err.message)
    }
  }

  useEffect(() => {
    loadStatus()
    const linkedQr = new URLSearchParams(window.location.search).get('office_qr')
    if (linkedQr) {
      validateOfficeQr(linkedQr)
        .then((office) => {
          setQrOffice(office)
          setQrValue(office.qr_payload || linkedQr)
          setMessage('Office QR verified. Take your attendance photo to continue.')
        })
        .catch((err) => setError(err.message))
    }
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
      (locationError) => {
        if (locationError?.code === 1) {
          reject(new Error('Location permission was denied. Open this site’s permissions, set Location to Allow, enable device Location Services, then reload the page.'))
        } else if (locationError?.code === 2) {
          reject(new Error('Your device could not determine its GPS location. Turn on precise/high-accuracy location and try again outdoors or near a window.'))
        } else if (locationError?.code === 3) {
          reject(new Error('GPS location timed out. Confirm Location Services are on and try again.'))
        } else {
          reject(new Error('GPS permission is required. Please allow location access.'))
        }
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
    )
  })

  const captureAttendancePhoto = async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('Camera access is required to capture your attendance photo.')
    }
    stopCamera()
    let stream
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'user' }, width: { ideal: 720 }, height: { ideal: 720 } },
        audio: false,
      })
      const video = document.createElement('video')
      video.playsInline = true
      video.muted = true
      video.srcObject = stream
      await new Promise((resolve, reject) => {
        const timeout = window.setTimeout(() => reject(new Error('Camera did not become ready.')), 10000)
        video.onloadedmetadata = () => {
          window.clearTimeout(timeout)
          video.play().then(resolve).catch(reject)
        }
      })
      const width = Math.min(720, video.videoWidth || 640)
      const height = Math.min(720, video.videoHeight || 480)
      const canvas = document.createElement('canvas')
      canvas.width = width
      canvas.height = height
      canvas.getContext('2d').drawImage(video, 0, 0, width, height)
      const value = canvas.toDataURL('image/jpeg', 0.76)
      setPhotoPreview(value)
      return value
    } catch (err) {
      if (err?.name === 'NotAllowedError' || err?.name === 'SecurityError' || /permission denied/i.test(err?.message || '')) {
        throw new Error('Camera permission was denied. Open this site’s permissions, set Camera to Allow, enable camera access in your device privacy settings, then reload the page.')
      }
      if (err?.name === 'NotFoundError' || err?.name === 'DevicesNotFoundError') {
        throw new Error('No working camera was found. A front-camera photo is required for attendance.')
      }
      if (err?.name === 'NotReadableError' || err?.name === 'TrackStartError') {
        throw new Error('The camera is busy or blocked by the system. Close other camera apps, check device privacy settings, and try again.')
      }
      throw new Error(err.message || 'Camera permission is required for the automatic attendance photo.')
    } finally {
      if (stream) stream.getTracks().forEach((track) => track.stop())
    }
  }


  const stopCamera = () => {
    setScanning(false)
    setCameraOpen(false)
    setCameraStream((current) => {
      if (current) current.getTracks().forEach((track) => track.stop())
      return null
    })
    if (videoRef.current) videoRef.current.srcObject = null
  }

  useEffect(() => () => stopCamera(), [])

  const validateQr = async (value) => {
    if (!/^\d{4}$/.test(value?.trim() || '')) throw new Error('Enter the four-digit office code.')
    const office = await validateOfficeQr(value.trim())
    setQrOffice(office)
    setQrValue(office.qr_payload || value.trim())
    return office
  }

  const prepareEvidence = async () => {
    setLoading(true)
    setError('')
    setMessage('Taking your attendance photo...')
    try {
      const photo = await captureAttendancePhoto()
      setPhotoPreview(photo)
      setEvidenceReady(true)
      setMessage('Photo captured. Draw your signature, then sign in or out.')
    } catch (err) {
      setMessage('')
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const verifyManualCode = async () => {
    setLoading(true)
    setError('')
    setMessage('')
    try {
      await validateQr(qrValue)
      await prepareEvidence()
    } catch (err) {
      setError(err.message)
      setLoading(false)
    }
  }

  const startQrScan = async () => {
    setError('')
    setMessage('')
    if (workLocationType !== 'office') return
    if (!navigator.mediaDevices?.getUserMedia) {
      setManualCodeEntry(true)
      setError('Camera scanning is not available in this browser. Enter the office code to continue.')
      return
    }
    try {
      setCameraOpen(true)
      setScanning(true)
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      })
      setCameraStream(stream)
      const video = videoRef.current
      if (!video) throw new Error('Camera preview is not ready. Please try again.')
      video.srcObject = stream
      video.setAttribute('playsinline', 'true')
      video.muted = true
      await video.play()

      if (!('BarcodeDetector' in window)) {
        setScanning(false)
        setMessage('Camera is open. This browser cannot auto-read QR codes, so scan with a supported mobile browser or type the QR code below.')
        return
      }

      const detector = new window.BarcodeDetector({ formats: ['qr_code'] })
      const deadline = Date.now() + 30000
      while (Date.now() < deadline) {
        const codes = await detector.detect(video).catch(() => [])
        if (codes.length) {
          const raw = codes[0].rawValue || ''
          const scannedCode = officeCodeFromScan(raw)
          if (!scannedCode) throw new Error('This QR code is not a valid office attendance code.')
          await validateQr(scannedCode)
          stopCamera()
          await new Promise((resolve) => window.setTimeout(resolve, 150))
          await prepareEvidence()
          return
        }
        await new Promise((resolve) => setTimeout(resolve, 250))
      }
      setScanning(false)
      setError('Camera opened but no QR code was detected. Hold the phone closer to the office QR code or enter it manually.')
    } catch (err) {
      stopCamera()
      setError(err.message || 'Camera permission is required to scan the office QR code.')
    }
  }

  const handleAction = async (action) => {
    setLoading(true)
    setError('')
    setMessage('')
    try {
      if (!evidenceReady || !photoPreview) throw new Error('Capture your attendance photo before signing in or out.')
      if (!signatureValue) throw new Error('Signature is required before sign in/out.')
      if (workLocationType === 'office' && !/^\d{4}$/.test(qrValue.trim())) {
        throw new Error('Enter the four-digit office code before signing in or out.')
      }
      if (workLocationType === 'office' && !qrOffice) {
        await validateQr(qrValue)
      }
      if (workLocationType === 'on_road' && !employeeNote.trim()) {
        throw new Error('Please enter a road-work reason/note.')
      }
      const location = await getLocation()
      const officeDistance = qrOffice?.latitude != null && qrOffice?.longitude != null
        ? getDistance(location.latitude, location.longitude, Number(qrOffice.latitude), Number(qrOffice.longitude))
        : null
      const distanceMessage = officeDistance == null
        ? 'GPS captured.'
        : `GPS captured: ${officeDistance >= 1000 ? `${(officeDistance / 1000).toFixed(2)} km` : `${Math.round(officeDistance)} m`} from the assigned office point.`
      setMessage(`${distanceMessage} Saving attendance...`)
      const payload = {
        ...location,
        device_info: navigator.userAgent,
        signature_value: signatureValue,
        photo_value: photoPreview,
        work_location_type: workLocationType,
        employee_note: employeeNote.trim() || null,
        qr_value: workLocationType === 'office' && qrValue.trim() ? qrValue : null,
      }
      const result = await submitAttendance(action, payload)
      setMessage(result.message)
      setSignatureValue('')
      setEmployeeNote('')
      setQrValue('')
      setQrOffice(null)
      setManualCodeEntry(false)
      setEvidenceReady(false)
      setPhotoPreview('')
      await loadStatus()
    } catch (err) {
      setMessage('')
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const checkDevicePermissions = async () => {
    setLoading(true)
    setError('')
    setMessage('')
    try {
      await getLocation()
      setMessage('GPS is ready. Checking the front camera...')
      await captureAttendancePhoto()
      setPhotoPreview('')
      setMessage('GPS and camera permissions are ready.')
    } catch (err) {
      setMessage('')
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card title="Mobile Employee Attendance">
      <p className="muted">Follow the steps below. Your office QR identifies the location; the code is shown only when manual entry is needed.</p>
      <div className="status-panel">
        <div><strong>User:</strong> {me.full_name}</div>
        <div><strong>Status:</strong> {status?.current_status || 'loading'}</div>
        <div><strong>Last action:</strong> {status?.last_action || 'none'}</div>
        <div><strong>Last time:</strong> {status?.last_action_at || 'n/a'}</div>
      </div>

      <div className="history-toolbar one-column">
        <label>
          Work location
          <select value={workLocationType} onChange={(event) => {
            setWorkLocationType(event.target.value)
            setQrOffice(null)
            setQrValue('')
            setManualCodeEntry(false)
            setEvidenceReady(false)
            setPhotoPreview('')
          }}>
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
        <div className="detail-header mobile-qr-header">
          <div>
            <h3>Step 1 — Confirm work location</h3>
            <p className="muted small">{workLocationType === 'office' ? 'Scan the office QR. GPS still checks that you are inside the office radius.' : 'For road work, continue to the attendance photo.'}</p>
          </div>
          {workLocationType === 'office' ? <button type="button" onClick={startQrScan} disabled={scanning || loading}>
            {scanning ? 'Scanning...' : 'Scan office QR'}
          </button> : <button type="button" onClick={prepareEvidence} disabled={loading}>{loading ? 'Opening camera...' : 'Take attendance photo'}</button>}
        </div>
        <div className={`qr-camera-panel ${cameraOpen ? 'open' : ''}`}>
          <video ref={videoRef} className="qr-camera-preview" playsInline muted />
          <div className="qr-camera-frame" aria-hidden="true" />
          {cameraOpen ? <button type="button" className="secondary-action" onClick={stopCamera}>Close camera</button> : null}
        </div>
        {workLocationType === 'office' && !manualCodeEntry && !qrOffice ? <button type="button" className="link-button" onClick={() => setManualCodeEntry(true)}>Cannot scan? Enter office code</button> : null}
        {workLocationType === 'office' && manualCodeEntry && !qrOffice ? (
          <div className="form-grid one-column">
            <label>
              Four-digit office code (required)
              <input
                value={qrValue}
                onChange={(event) => setQrValue(event.target.value.replace(/\D/g, '').slice(0, 4))}
                inputMode="numeric"
                pattern="[0-9]{4}"
                maxLength="4"
                autoComplete="one-time-code"
                placeholder="Enter the code displayed at this office"
              />
            </label>
            <button type="button" className="secondary-action" onClick={verifyManualCode} disabled={loading || qrValue.length !== 4}>{loading ? 'Checking...' : 'Verify and take photo'}</button>
          </div>
        ) : null}
        {qrOffice ? (
          <div className="status-panel">
            <p className="success">Office confirmed: {qrOffice.office_name || 'assigned office'}</p>
            <p className="muted small">{qrOffice.address || 'No address captured'} · Allowed radius: {qrOffice.allowed_radius_m || 100} m</p>
            {!evidenceReady ? <button type="button" onClick={prepareEvidence} disabled={loading}>{loading ? 'Opening camera...' : 'Take attendance photo'}</button> : null}
          </div>
        ) : null}
        {workLocationType === 'on_road' ? <p className="muted small">QR scan is not required for on-road work, but the note is required and goes for approval.</p> : null}
      </div>

      {evidenceReady ? <div className="attendance-step"><h3>Step 3 — Sign</h3><SignaturePad onChange={setSignatureValue} /></div> : null}

      <div className="attendance-evidence-note">
        <strong>Step 2 — Attendance photo</strong>
        <p className="muted small">After the QR is accepted, the front camera captures the attendance photo and moves you to the signature step.</p>
        <button type="button" className="glass-button" onClick={checkDevicePermissions} disabled={loading}>Test GPS & camera permissions</button>
        <p className="muted small">If permission was previously denied, use the lock/settings icon beside the website address to allow Location and Camera. Also enable Location Services and camera access in the device’s privacy settings, then reload this page.</p>
        {photoPreview ? <img src={photoPreview} alt="Latest automatic attendance capture" className="attendance-photo-preview" /> : null}
      </div>

      {evidenceReady ? <div className="mobile-actions">
        <button disabled={loading || status?.current_status === 'signed_in'} onClick={() => handleAction('sign-in')}>
          {loading ? 'Working...' : 'Sign in'}
        </button>
        <button className="danger" disabled={loading || status?.current_status !== 'signed_in'} onClick={() => handleAction('sign-out')}>
          {loading ? 'Working...' : 'Sign out'}
        </button>
      </div> : null}
      <p className="muted small">GPS, signature and camera evidence are recorded for office and on-road events. Outside-radius, low-accuracy and on-road events remain visible for approval review.</p>
      {message ? <div className="status-panel"><p className="success">{message}</p><button type="button" onClick={() => onDone?.()}>Done</button></div> : null}
      {error ? <p className="error">{error}</p> : null}
    </Card>
  )
}
