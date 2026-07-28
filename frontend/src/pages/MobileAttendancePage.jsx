import { useEffect, useRef, useState } from 'react'
import Card from '../components/Card'
import SignaturePad from '../components/SignaturePad'
import { getAttendanceStatus, submitAttendance, validateOfficeQr } from '../api/client'
import { formatJohannesburgDateTime } from '../utils/dateTime'

const GPS_OPTIONS = { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 }
const REAR_CAMERA_HINTS = ['back', 'rear', 'environment', 'world']

function locationErrorMessage(error) {
  if (error?.code === 1) return 'Location permission was denied. Allow Location for this site and enable precise device location.'
  if (error?.code === 2) return 'The device could not determine its GPS coordinates. Enable precise/high-accuracy location and try again.'
  if (error?.code === 3) return 'GPS location timed out. Move near a window or outdoors and try again.'
  return 'GPS coordinates are required for every sign-in and sign-out.'
}

async function getRearCameraStream() {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error('Camera access is required to scan the office QR code.')
  }

  const streamFor = (video) => navigator.mediaDevices.getUserMedia({ video, audio: false })
  const cameraSizes = {
    width: { ideal: 1280 },
    height: { ideal: 720 },
  }

  try {
    return await streamFor({
      facingMode: { exact: 'environment' },
      ...cameraSizes,
    })
  } catch (exactError) {
    if (exactError?.name === 'NotAllowedError' || exactError?.name === 'SecurityError') throw exactError
  }

  try {
    return await streamFor({
      facingMode: { ideal: 'environment' },
      ...cameraSizes,
    })
  } catch (idealError) {
    if (idealError?.name === 'NotAllowedError' || idealError?.name === 'SecurityError') throw idealError
  }

  try {
    const devices = await navigator.mediaDevices.enumerateDevices()
    const cameras = devices.filter((device) => device.kind === 'videoinput')
    const rearCamera = cameras.find((device) => REAR_CAMERA_HINTS.some((hint) => device.label.toLowerCase().includes(hint)))
      || (cameras.length > 1 ? cameras[cameras.length - 1] : null)
    if (rearCamera?.deviceId) {
      return await streamFor({
        deviceId: { exact: rearCamera.deviceId },
        ...cameraSizes,
      })
    }
  } catch (deviceError) {
    if (deviceError?.name === 'NotAllowedError' || deviceError?.name === 'SecurityError') throw deviceError
  }

  return streamFor(true)
}

export default function MobileAttendancePage({ me, onDone }) {
  const [status, setStatus] = useState(null)
  const [step, setStep] = useState(1)
  const [selectedAction, setSelectedAction] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [signatureValue, setSignatureValue] = useState('')
  const [qrValue, setQrValue] = useState('')
  const [qrOffice, setQrOffice] = useState(null)
  const [manualEntry, setManualEntry] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [scanError, setScanError] = useState('')
  const [manualEntryAvailable, setManualEntryAvailable] = useState(false)
  const [scanRestart, setScanRestart] = useState(0)
  const [gpsEvidence, setGpsEvidence] = useState(null)
  const [gpsError, setGpsError] = useState('')
  const [photoPreview, setPhotoPreview] = useState('')
  const [photoReady, setPhotoReady] = useState(false)

  const scannerVideoRef = useRef(null)
  const scannerStopRef = useRef(() => {})
  const scanLockedRef = useRef(false)
  const gpsWatchRef = useRef(null)

  const loadStatus = async () => {
    try {
      setStatus(await getAttendanceStatus())
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => { loadStatus() }, [])

  const stopGpsWatch = () => {
    if (gpsWatchRef.current != null && navigator.geolocation) {
      navigator.geolocation.clearWatch(gpsWatchRef.current)
      gpsWatchRef.current = null
    }
  }

  const beginBackgroundGps = () => {
    if (!navigator.geolocation) {
      setGpsError('GPS is not available on this device/browser.')
      return
    }
    stopGpsWatch()
    setGpsError('')
    gpsWatchRef.current = navigator.geolocation.watchPosition(
      (position) => {
        setGpsEvidence({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy: position.coords.accuracy,
          captured_at: new Date().toISOString(),
        })
        setGpsError('')
      },
      (locationError) => setGpsError(locationErrorMessage(locationError)),
      GPS_OPTIONS,
    )
  }

  const getFreshLocation = () => new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error('GPS is not available on this device/browser.'))
      return
    }
    navigator.geolocation.getCurrentPosition(
      (position) => resolve({
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
        accuracy: position.coords.accuracy,
      }),
      (locationError) => reject(new Error(locationErrorMessage(locationError))),
      GPS_OPTIONS,
    )
  })

  useEffect(() => () => {
    scannerStopRef.current()
    stopGpsWatch()
  }, [])

  const captureAttendancePhoto = async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('Camera access is required to capture attendance evidence.')
    }
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
      const canvas = document.createElement('canvas')
      canvas.width = Math.min(720, video.videoWidth || 640)
      canvas.height = Math.min(720, video.videoHeight || 480)
      canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height)
      const photo = canvas.toDataURL('image/jpeg', 0.76)
      setPhotoPreview(photo)
      setPhotoReady(true)
      return photo
    } catch (err) {
      if (err?.name === 'NotAllowedError' || err?.name === 'SecurityError') {
        throw new Error('Camera permission was denied. Allow Camera for this site, then reload the page.')
      }
      throw new Error(err.message || 'The automatic attendance photo could not be captured.')
    } finally {
      if (stream) stream.getTracks().forEach((track) => track.stop())
    }
  }

  const acceptQr = async (rawValue) => {
    if (scanLockedRef.current) return
    scanLockedRef.current = true
    scannerStopRef.current()
    setScanning(false)
    setScanError('')
    setError('')
    setMessage('QR code detected. Confirming the assigned office...')
    try {
      const office = await validateOfficeQr(String(rawValue || '').trim())
      setQrOffice(office)
      setQrValue(office.qr_payload || String(rawValue || '').trim())
      setStep(3)
      setMessage('Office QR registered. Capturing the attendance photo in the background...')
      await captureAttendancePhoto()
      setMessage('QR, photo and GPS evidence are ready. Draw your signature to complete the attendance record.')
    } catch (err) {
      setError(err.message)
      setQrOffice(null)
      setQrValue('')
      setStep(2)
      scanLockedRef.current = false
      setScanRestart((value) => value + 1)
    }
  }

  useEffect(() => {
    if (step !== 2 || manualEntry) return undefined
    let cancelled = false
    let stream = null
    let frameId = null
    let fallbackTimer = null
    let detecting = false

    const stopScanner = () => {
      cancelled = true
      if (frameId) window.cancelAnimationFrame(frameId)
      if (fallbackTimer) window.clearTimeout(fallbackTimer)
      if (stream) stream.getTracks().forEach((track) => track.stop())
      if (scannerVideoRef.current) scannerVideoRef.current.srcObject = null
      setScanning(false)
    }
    scannerStopRef.current = stopScanner

    const startScanner = async () => {
      scanLockedRef.current = false
      setScanError('')
      try {
        stream = await getRearCameraStream()
        if (cancelled) return
        const video = scannerVideoRef.current
        video.srcObject = stream
        video.playsInline = true
        video.muted = true
        await video.play()
        setScanning(true)
        if (!window.BarcodeDetector) {
          setManualEntryAvailable(true)
          setScanError('The rear camera is open, but this browser cannot automatically read QR codes. Use Chrome/Edge for automatic scanning, or ask your manager/franchise user for the four-digit code.')
          return
        }
        const formats = await window.BarcodeDetector.getSupportedFormats?.()
        if (formats && !formats.includes('qr_code')) {
          setManualEntryAvailable(true)
          setScanError('The rear camera is open, but this browser cannot automatically read QR codes. Use Chrome/Edge for automatic scanning, or ask your manager/franchise user for the four-digit code.')
          return
        }
        const detector = new window.BarcodeDetector({ formats: ['qr_code'] })
        fallbackTimer = window.setTimeout(() => {
          if (cancelled || scanLockedRef.current) return
          setManualEntryAvailable(true)
          setScanError('The rear camera is open but no QR code has been detected yet. Keep scanning, or ask your manager/franchise user for the four-digit code.')
        }, 45000)

        const scanFrame = async () => {
          if (cancelled || scanLockedRef.current) return
          if (!detecting && video.readyState >= 2) {
            detecting = true
            try {
              const codes = await detector.detect(video)
              const value = codes?.find((code) => code.rawValue)?.rawValue
              if (value) {
                await acceptQr(value)
                return
              }
            } catch {
              // A transient frame detection failure should not stop the scanner.
            } finally {
              detecting = false
            }
          }
          frameId = window.requestAnimationFrame(scanFrame)
        }
        frameId = window.requestAnimationFrame(scanFrame)
      } catch (err) {
        setScanning(false)
        setManualEntryAvailable(true)
        setScanError(err?.name === 'NotAllowedError' || err?.name === 'SecurityError'
          ? 'Camera permission was denied. Allow Camera for this site and try again.'
          : (err.message || 'The QR scanner could not start. Ask your manager/franchise user for the four-digit code.'))
      }
    }

    startScanner()
    return stopScanner
  }, [step, manualEntry, scanRestart])

  const selectAction = (action) => {
    setSelectedAction(action)
    setStep(2)
    setMessage('GPS capture started in the background. Hold the office QR code inside the camera frame.')
    setError('')
    setScanError('')
    setManualEntryAvailable(false)
    setQrValue('')
    setQrOffice(null)
    setSignatureValue('')
    setPhotoPreview('')
    setPhotoReady(false)
    setManualEntry(false)
    beginBackgroundGps()
  }

  const verifyManualQr = async () => {
    if (!/^\d{4}$/.test(qrValue.trim())) {
      setError('Enter the four-digit code from your manager or franchise user.')
      return
    }
    setMessage('Saving the QR code and confirming the assigned office...')
    await acceptQr(qrValue.trim())
  }

  const retryPhoto = async () => {
    setLoading(true)
    setError('')
    try {
      await captureAttendancePhoto()
      setMessage('Attendance photo captured. Draw your signature to complete the record.')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const resetFlow = () => {
    scannerStopRef.current()
    stopGpsWatch()
    scanLockedRef.current = false
    setStep(1)
    setSelectedAction('')
    setQrValue('')
    setQrOffice(null)
    setSignatureValue('')
    setPhotoPreview('')
    setPhotoReady(false)
    setGpsEvidence(null)
    setGpsError('')
    setManualEntry(false)
    setManualEntryAvailable(false)
  }

  const saveAttendance = async () => {
    setLoading(true)
    setError('')
    try {
      if (!selectedAction) throw new Error('Choose sign in or sign out first.')
      if (!qrOffice || !qrValue) throw new Error('Scan and register the assigned office QR code.')
      if (!signatureValue) throw new Error('Draw your signature before saving.')
      if (!photoReady || !photoPreview) throw new Error('The automatic attendance photo is required.')

      setMessage('Confirming current GPS coordinates and saving attendance...')
      const location = await getFreshLocation()
      setGpsEvidence({ ...location, captured_at: new Date().toISOString() })
      const result = await submitAttendance(selectedAction, {
        ...location,
        device_info: navigator.userAgent,
        signature_value: signatureValue,
        photo_value: photoPreview,
        work_location_type: 'office',
        employee_note: null,
        qr_value: qrValue,
      })
      setMessage(result.message)
      await loadStatus()
      stopGpsWatch()
      setStep(4)
    } catch (err) {
      setMessage('')
      setError(err.message)
      if (/code|expired|already used|QR/i.test(err.message || '')) {
        setQrValue('')
        setQrOffice(null)
        setPhotoPreview('')
        setPhotoReady(false)
        setSignatureValue('')
        scanLockedRef.current = false
        setStep(2)
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card title="Mobile Attendance">
      <p className="muted">Complete the three steps in order. GPS coordinates are captured in the background and saved with every attendance event.</p>

      <div className="status-panel">
        <div><strong>User:</strong> {me.full_name}</div>
        <div><strong>Status:</strong> {status?.current_status || 'loading'}</div>
        <div><strong>Last action:</strong> {status?.last_action || 'none'}</div>
        <div><strong>Last time:</strong> {formatJohannesburgDateTime(status?.last_action_at)}</div>
      </div>

      <div className="attendance-flow-progress" aria-label={`Attendance step ${Math.min(step, 3)} of 3`}>
        <span className={step >= 1 ? 'active' : ''}>1. Sign in/out</span>
        <span className={step >= 2 ? 'active' : ''}>2. Scan QR</span>
        <span className={step >= 3 ? 'active' : ''}>3. Sign</span>
      </div>

      {step === 1 ? (
        <section className="attendance-flow-step">
          <h3>Step 1 — Choose sign in or sign out</h3>
          <div className="mobile-actions attendance-action-choice">
            <button disabled={status?.current_status === 'signed_in'} onClick={() => selectAction('sign-in')}>Sign in</button>
            <button className="danger-button" disabled={status?.current_status !== 'signed_in'} onClick={() => selectAction('sign-out')}>Sign out</button>
          </div>
        </section>
      ) : null}

      {step === 2 ? (
        <section className="attendance-flow-step">
          <div className="detail-header">
            <div>
              <h3>Step 2 — Scan the office QR code</h3>
              <p className="muted small">The next step opens automatically as soon as the QR code is detected and registered.</p>
            </div>
            <button type="button" className="glass-button" onClick={resetFlow}>Cancel</button>
          </div>

          {!manualEntry ? (
            <div className="live-qr-scanner">
              <video ref={scannerVideoRef} aria-label="Live office QR scanner" playsInline muted autoPlay disablePictureInPicture />
              <strong>{scanning ? 'Hold the QR code steady in view' : 'Starting camera...'}</strong>
            </div>
          ) : (
            <div className="manual-qr-save-panel">
              <p className="muted small">If this browser cannot scan the QR code automatically, ask your manager or franchise user for the four-digit office code. Enter it here, then save it to continue.</p>
              <label>
                Four-digit QR value
                <input
                  value={qrValue}
                  onChange={(event) => setQrValue(event.target.value.replace(/\D/g, '').slice(0, 4))}
                  inputMode="numeric"
                  pattern="[0-9]{4}"
                  maxLength="4"
                  autoComplete="one-time-code"
                  placeholder="0000"
                />
              </label>
              <button type="button" className="primary-action" onClick={verifyManualQr} disabled={qrValue.length !== 4}>Save QR code and continue</button>
            </div>
          )}
          {scanError ? <p className="error">{scanError}</p> : null}
          {!manualEntry && manualEntryAvailable ? <button type="button" className="link-button" onClick={() => {
            scannerStopRef.current()
            setScanError('')
            setMessage('Enter the four-digit office code, then tap Save QR code and continue.')
            setManualEntry(true)
          }}>Scan and save QR code manually</button> : null}
        </section>
      ) : null}

      {step === 3 ? (
        <section className="attendance-flow-step">
          <div className="detail-header">
            <div>
              <h3>Step 3 — Sign the {selectedAction === 'sign-out' ? 'sign-out' : 'sign-in'}</h3>
              <p className="muted small">Office confirmed: {qrOffice?.office_name || 'assigned office'}</p>
            </div>
            <button type="button" className="glass-button" onClick={resetFlow}>Cancel</button>
          </div>
          <SignaturePad onChange={setSignatureValue} />
          <div className="attendance-evidence-status">
            <span className={gpsEvidence ? 'ready' : 'waiting'}>{gpsEvidence ? `GPS ready · ±${Math.round(gpsEvidence.accuracy)} m` : 'Capturing GPS...'}</span>
            <span className={photoReady ? 'ready' : 'waiting'}>{photoReady ? 'Automatic photo ready' : 'Capturing automatic photo...'}</span>
          </div>
          {gpsError ? <p className="error">{gpsError}</p> : null}
          {!photoReady ? <button type="button" className="glass-button" onClick={retryPhoto} disabled={loading}>Retry attendance photo</button> : null}
          {photoPreview ? <img src={photoPreview} alt="Automatic attendance evidence" className="attendance-photo-preview" /> : null}
          <button type="button" className="attendance-complete-button" onClick={saveAttendance} disabled={loading || !signatureValue || !photoReady}>
            {loading ? 'Saving GPS and attendance...' : `Complete ${selectedAction === 'sign-out' ? 'sign out' : 'sign in'}`}
          </button>
        </section>
      ) : null}

      {step === 4 ? (
        <section className="attendance-flow-step attendance-complete-state">
          <h3>Attendance saved</h3>
          <p className="success">{message}</p>
          <p className="muted small">The GPS coordinates, accuracy, QR office, signature and automatic photo were recorded.</p>
          <div className="button-row">
            <button type="button" onClick={resetFlow}>New attendance action</button>
            <button type="button" className="glass-button" onClick={() => onDone?.()}>Done</button>
          </div>
        </section>
      ) : null}

      {step < 4 && message ? <p className="success-message">{message}</p> : null}
      {error ? <p className="error">{error}</p> : null}
    </Card>
  )
}
