import { useState, useEffect, useRef } from 'react'
import { forgotPassword, registerFranchise, resetForgottenPassword } from '../api/client'
import Card from '../components/Card'
import InstallPrompt from '../components/InstallPrompt'

const emptyRegistration = {
  business_name: '',
  trading_as: '',
  business_registration_number: '',
  vat_number: '',
  office_address: '',
  website: '',
  office_number: '',
  twenty_four_hour_number: '',
  franchisee_name: '',
  franchisee_surname: '',
  email: '',
  contact_number: '',
  password: '',
  confirm_password: '',
}

export default function LoginPage({ onLogin, loading, error }) {
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const resetToken = new URLSearchParams(window.location.search).get('reset_token') || ''
  const [resetPassword, setResetPassword] = useState('')
  const [resetMessage, setResetMessage] = useState('')
  const [registration, setRegistration] = useState(emptyRegistration)
  const [registering, setRegistering] = useState(false)
  const [registrationMessage, setRegistrationMessage] = useState('')
  const [registrationError, setRegistrationError] = useState('')
  const [forgotMessage, setForgotMessage] = useState('')
  const [forgotLoading, setForgotLoading] = useState(false)

  const addressInputRef = useRef(null)
  const autocompleteRef = useRef(null)

  const submitLogin = (event) => {
    event.preventDefault()
    onLogin(email.trim(), password)
  }

  useEffect(() => {
    if (mode !== 'register') return
    const apiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY

    function initAutocomplete() {
      if (!window.google || !addressInputRef.current) return

      autocompleteRef.current = new window.google.maps.places.Autocomplete(
        addressInputRef.current,
        {
          componentRestrictions: { country: 'za' },
          fields: ['formatted_address'],
        }
      )

      autocompleteRef.current.addListener('place_changed', () => {
        const place = autocompleteRef.current.getPlace()

        if (place?.formatted_address) {
          updateRegistration('office_address', place.formatted_address)
        }
      })
    }

    const existingScript = document.querySelector(
      'script[data-google-places="true"]'
    )

    if (!window.google && !existingScript) {
      const script = document.createElement('script')

      script.dataset.googlePlaces = 'true'
      script.src = `https://maps.googleapis.com/maps/api/js?key=${apiKey}&libraries=places`

      script.async = true
      script.defer = true
      script.onload = initAutocomplete

      document.head.appendChild(script)
    } else {
      setTimeout(initAutocomplete, 100)
    }
  }, [mode])

  const submitForgotPassword = async () => {
    setForgotMessage('')
    if (!email) {
      setForgotMessage('Enter your email address first, then click Forgot password.')
      return
    }
    setForgotLoading(true)
    try {
      const data = await forgotPassword(email)
      const contact = data.franchise_admin_email ? ` Contact: ${data.franchise_admin_email}` : ''
      setForgotMessage(`${data.message || 'Password reset request checked.'}${contact}`)
    } catch (err) {
      setForgotMessage(err.message || 'Password reset request failed.')
    } finally {
      setForgotLoading(false)
    }
  }

  const updateRegistration = (key, value) => {
    setRegistration((current) => ({ ...current, [key]: value }))
  }

  const submitRegistration = async (event) => {
    event.preventDefault()
    setRegistrationMessage('')
    setRegistrationError('')

    if (registration.password !== registration.confirm_password) {
      setRegistrationError('Password and confirm password must match')
      return
    }

    setRegistering(true)
    try {
      const { confirm_password, ...payload } = registration
      await registerFranchise(payload)
      setRegistration(emptyRegistration)
      setRegistrationMessage('Registration submitted. A SuperUser must approve it before login is enabled.')
    } catch (err) {
      setRegistrationError(err.message)
    } finally {
      setRegistering(false)
    }
  }

  return (
    <div className="center-page login-page-bg">
      <Card title={mode === 'login' ? '' : 'Register New Franchise'} className={mode === 'login' ? 'form-card login-card login-card-compact' : 'form-card wide-form login-card'}>
        <div className="martins-login-header">
          <strong>Martins Login</strong>
          <span>Attendance</span>
        </div>
        <div className="martins-auth-brand">
          <img className="login-logo" src="/logo.png" alt="Martins logo" />
          <strong>Martins System</strong>
          <span>Attendance</span>
        </div>

        {resetToken ? (
          <form className="login-form" onSubmit={async (event) => { event.preventDefault(); try { const data = await resetForgottenPassword(resetToken, resetPassword); setResetMessage(data.message || 'Password changed.'); window.history.replaceState({}, '', window.location.pathname); } catch (err) { setResetMessage(err.message || 'Reset failed.'); } }}>
            <h2>Create a new password</h2>
            <label>New password<input type={showPassword ? 'text' : 'password'} minLength="8" required value={resetPassword} onChange={(e) => setResetPassword(e.target.value)} /></label>
            <label><input type="checkbox" checked={showPassword} onChange={(e) => setShowPassword(e.target.checked)} /> Show password</label>
            <button type="submit">Save new password</button>
            {resetMessage ? <p>{resetMessage}</p> : null}
          </form>
        ) : mode === 'login' ? (
          <>
            <form className="login-form" onSubmit={submitLogin}>
              <label>Email or username
                <input value={email} onChange={(event) => setEmail(event.target.value)} type="text" autoComplete="username" autoCapitalize="none" autoCorrect="off" spellCheck={false} required />
              </label>
              <label>Password
                <div className="password-input-row"><input value={password} onChange={(event) => setPassword(event.target.value)} type={showPassword ? 'text' : 'password'} autoComplete="current-password" required /><button type="button" className="glass-button password-toggle" onClick={() => setShowPassword((v) => !v)}>{showPassword ? 'Hide' : 'Show'}</button></div>
              </label>
              <div className="login-form-actions">
                <button type="submit" disabled={loading}>{loading ? 'Logging in...' : 'Login'}</button>
                <button type="button" className="link-button forgot-link" disabled={forgotLoading} onClick={submitForgotPassword}>{forgotLoading ? 'Checking...' : 'Forgot password?'}</button>
              </div>
              {forgotMessage ? <p className="muted small">{forgotMessage}</p> : null}
              {error ? <p className="error">{error}</p> : null}
            </form>

            <div className="login-register-bottom">
              <span className="muted small">Need franchise access?</span>
              <button type="button" className="secondary" onClick={() => setMode('register')}>Register New Franchise</button>
            </div>
          </>
        ) : (
          <form onSubmit={submitRegistration}>
            <h3>Business Details</h3>
            <div className="form-grid">
              <label>Business Name
                <input value={registration.business_name} onChange={(e) => updateRegistration('business_name', e.target.value)} required />
              </label>
              <label>Trading As
                <input value={registration.trading_as} onChange={(e) => updateRegistration('trading_as', e.target.value)} />
              </label>
              <label>Business Registration Number
                <input value={registration.business_registration_number} onChange={(e) => updateRegistration('business_registration_number', e.target.value)} />
              </label>
              <label>VAT Nr
                <input value={registration.vat_number} onChange={(e) => updateRegistration('vat_number', e.target.value)} />
              </label>
              <label className="span-2">Office Address
                <input
                  ref={addressInputRef}
                  value={registration.office_address}
                  onChange={(e) => updateRegistration('office_address', e.target.value)}
                  placeholder="Start typing address..."
                />
              </label>
              <label className="span-2">Website Address
                <input value={registration.website} onChange={(e) => updateRegistration('website', e.target.value)} placeholder="https://example.co.za" />
              </label>
              <label>Office Number
                <input value={registration.office_number} onChange={(e) => updateRegistration('office_number', e.target.value)} />
              </label>
              <label>24 Hour Number
                <input value={registration.twenty_four_hour_number} onChange={(e) => updateRegistration('twenty_four_hour_number', e.target.value)} />
              </label>
            </div>

            <h3>Franchisee Details</h3>
            <div className="form-grid">
              <label>Name
                <input value={registration.franchisee_name} onChange={(e) => updateRegistration('franchisee_name', e.target.value)} required />
              </label>
              <label>Surname
                <input value={registration.franchisee_surname} onChange={(e) => updateRegistration('franchisee_surname', e.target.value)} required />
              </label>
              <label>Email Address
                <input value={registration.email} onChange={(e) => updateRegistration('email', e.target.value)} type="email" required />
              </label>
              <label>Contact Number
                <input value={registration.contact_number} onChange={(e) => updateRegistration('contact_number', e.target.value)} />
              </label>
              <label>Password
                <input value={registration.password} onChange={(e) => updateRegistration('password', e.target.value)} type="password" required minLength={8} />
              </label>
              <label>Confirm Password
                <input value={registration.confirm_password} onChange={(e) => updateRegistration('confirm_password', e.target.value)} type="password" required minLength={8} />
              </label>
            </div>

            {registrationError ? <p className="error">{registrationError}</p> : null}
            {registrationMessage ? <p className="success">{registrationMessage}</p> : null}
            <div className="registration-install-only">
              <InstallPrompt />
            </div>
            <div className="login-form-actions">
              <button type="submit" disabled={registering}>{registering ? 'Submitting...' : 'Submit Franchise Registration'}</button>
              <button type="button" className="secondary" onClick={() => setMode('login')}>Back to Login</button>
            </div>
          </form>
        )}
      </Card>
    </div>
  )
}
