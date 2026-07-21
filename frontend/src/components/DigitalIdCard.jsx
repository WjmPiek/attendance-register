import { useEffect, useState } from 'react'
import { getMyDigitalIdCard } from '../api/client'

function initials(name = '') {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((x) => x[0]?.toUpperCase()).join('') || 'ID'
}

function splitDisplayName(card) {
  const first = (card?.name || '').trim()
  const surname = (card?.surname || '').trim()
  if (first || surname) return { first: first || card.full_name || 'Staff', surname }
  const parts = String(card?.full_name || 'Staff').trim().split(/\s+/).filter(Boolean)
  if (parts.length <= 1) return { first: parts[0] || 'Staff', surname: '' }
  return { first: parts.slice(0, -1).join(' '), surname: parts.at(-1) }
}

export default function DigitalIdCard() {
  const [card, setCard] = useState(null)
  const [error, setError] = useState('')
  const [open, setOpen] = useState(true)

  useEffect(() => {
    let alive = true
    getMyDigitalIdCard()
      .then((data) => { if (alive) setCard(data) })
      .catch((err) => { if (alive) setError(err.message || 'Digital ID card unavailable') })
    return () => { alive = false }
  }, [])

  if (error) return <p className="muted small">Digital ID card unavailable: {error}</p>
  if (!card) return <div className="digital-id-card loading-card">Loading digital ID card...</div>
  const displayName = splitDisplayName(card)

  return (
    <section className="digital-id-wrapper">
      <div className="detail-header compact-header">
        <div>
          <h3>Digital Staff ID</h3>
          <p className="muted small">Show this card from your mobile phone for staff identification.</p>
        </div>
        <button type="button" className="secondary-action" onClick={() => setOpen(!open)}>{open ? 'Hide' : 'Show'}</button>
      </div>
      {open ? (
      <div className="premium-id-card">
        <div className="premium-id-swoosh"></div>

        <div className="premium-id-header">
          <div>
            <h2>STAFF ID</h2>
          </div>
          <img src="/logo.png" className="premium-id-logo" alt="Logo" />
        </div>

        <div className="premium-id-body">
          <div className="premium-id-photo">
            {card.photo_url ? <img src={card.photo_url} alt="Staff" /> : <span>{initials(card.full_name)}</span>}
          </div>

          <div className="premium-id-info">
            <strong>{displayName.first}</strong>
            <strong>{displayName.surname}</strong>
            <span className="premium-role">🌐 {card.role_label}</span>
            <span className="premium-franchise">▦ Franchise: {card.franchise_name}</span>
          </div>

          <div className="premium-id-qr">
            {card.qr_image_url ? <img src={card.qr_image_url} alt="QR" /> : <span>QR</span>}
          </div>
        </div>

        <div className="premium-id-meta">
          <div><small>Status</small><b>{card.status || 'Active'}</b></div>
          <div><small>User ID</small><b>{card.user_id}</b></div>
          <div><small>Issued</small><b>21 May 2025</b></div>
          <div><small>ID Validity</small><b>No Expiry</b></div>
        </div>

        <div className="premium-id-footer">
          🌐 Scan QR code or visit {card.qr_payload}
        </div>
      </div>          
      ) : null}
    </section>
  )
}
