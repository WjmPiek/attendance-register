import { useEffect, useState } from 'react'
import { getMyDigitalIdCard } from '../api/client'
import StaffIdCard from './StaffIdCard.jsx'

export default function DigitalIdCard() {
  const [card, setCard] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true
    getMyDigitalIdCard()
      .then((data) => { if (alive) setCard(data) })
      .catch((err) => { if (alive) setError(err.message || 'Digital ID card unavailable') })
    return () => { alive = false }
  }, [])

  if (error) return <p className="error">Digital ID card unavailable: {error}</p>
  if (!card) return <section className="form-card"><p>Loading employee card...</p></section>

  return (
    <section className="form-card employee-card-page">
      <div className="detail-header employee-card-heading">
        <div>
          <p className="eyebrow">Employee identification</p>
          <h1>Employee Card</h1>
          <p className="muted">This card is linked only to your registered staff profile.</p>
        </div>
      </div>
      <div className="employee-card-mobile-stage">
        <StaffIdCard item={card} className="employee-self-id-card" />
      </div>
    </section>
  )
}
