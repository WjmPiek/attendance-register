import React from 'react'

function pick(...values) {
  return values.find((value) => value !== undefined && value !== null && String(value).trim() !== '') || ''
}

export function buildStaffIdCardData(item = {}) {
  const qrPayload = pick(item.qr_payload, item.website, 'https://martinsdirect.co.za')
  return {
    firstName: pick(item.name, item.first_name, item.full_name, 'Staff'),
    surname: pick(item.surname, ''),
    role: pick(item.role_label, item.employee_role, item.role, item.staff_type, 'Staff'),
    franchise: pick(item.franchise_name, item.business_name, item.office_name, 'Franchise'),
    status: pick(item.status, 'Active'),
    userId: pick(item.user_id, item.id, item.staff_id, ''),
    issued: pick(item.issued, '21 May 2025'),
    validity: pick(item.validity, 'No Expiry'),
    photoUrl: pick(item.photo_url, item.photoUrl, ''),
    qrImageUrl: pick(item.qr_image_url, item.qrImageUrl, ''),
    qrPayload,
    logoUrl: pick(item.franchise_logo, item.logo_url, '/logo.png'),
  }
}

export default function StaffIdCard({ item, className = '' }) {
  const card = buildStaffIdCardData(item)
  return (
    <div className={`staff-id-card ${className}`.trim()}>
      <div className="staff-id-header">
        <div className="staff-id-title">
          <h2>STAFF ID</h2>
        </div>
        <img src={card.logoUrl} className="staff-id-logo" alt="Logo" />
      </div>
      <div className="staff-id-main">
        <div className="staff-id-photo">
          {card.photoUrl ? <img src={card.photoUrl} alt="Staff" /> : <span>ID PHOTO</span>}
        </div>
        <div className="staff-id-person">
          <strong>{card.firstName}</strong>
          {card.surname ? <strong>{card.surname}</strong> : null}
          <span className="staff-id-role">■ {card.role}</span>
          <span className="staff-id-franchise">■ Franchise: {card.franchise}</span>
        </div>
        <div className="staff-id-qr">
          {card.qrImageUrl ? <img src={card.qrImageUrl} alt="QR code" /> : <span>QR</span>}
        </div>
      </div>
      <div className="staff-id-meta">
        <div><small>Status</small><b className="staff-id-active">{card.status}</b></div>
        <div><small>User ID</small><b>{card.userId}</b></div>
        <div><small>Issued</small><b>{card.issued}</b></div>
        <div><small>ID Validity</small><b>{card.validity}</b></div>
      </div>
      <div className="staff-id-footer">Scan QR code or visit {card.qrPayload}</div>
    </div>
  )
}
