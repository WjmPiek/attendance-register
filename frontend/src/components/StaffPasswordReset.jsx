import React, { useEffect, useRef, useState } from 'react'

export default function StaffPasswordReset({ label, onReset, onCancel }) {
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const panel = useRef(null)
  const submitting = useRef(false)

  useEffect(() => {
    panel.current?.scrollIntoView({ block: 'center', behavior: 'smooth' })
    panel.current?.querySelector('input')?.focus({ preventScroll: true })
  }, [])

  const submit = async event => {
    event.preventDefault()
    if (submitting.current) return
    if (password.length < 8) { setError('Password must be at least 8 characters.'); return }
    if (password !== confirmation) { setError('The passwords do not match.'); return }
    submitting.current = true
    setBusy(true); setError('')
    try {
      await onReset(password)
      setPassword(''); setConfirmation('')
    } catch (failure) {
      setError(failure.message || 'Unable to reset password. Please try again.')
    } finally {
      submitting.current = false
      setBusy(false)
    }
  }

  return <section ref={panel} className="form-card staff-password-reset" aria-label={`Reset password for ${label}`}>
    <h3>Reset password for {label}</h3>
    <form onSubmit={submit}>
      <label>New password<input type="password" autoComplete="new-password" required minLength={8} value={password} disabled={busy} onChange={event => setPassword(event.target.value)} /></label>
      <label>Confirm new password<input type="password" autoComplete="new-password" required minLength={8} value={confirmation} disabled={busy} onChange={event => setConfirmation(event.target.value)} /></label>
      <p className="muted">Use at least 8 characters. Only this staff member’s password will change.</p>
      {error && <p role="alert" className="error-message">{error}</p>}
      <div className="button-row">
        <button type="submit" disabled={busy}>{busy ? 'Saving password…' : 'Save new password'}</button>
        <button type="button" className="glass-button" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </form>
  </section>
}
