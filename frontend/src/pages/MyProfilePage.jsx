import { useEffect, useState } from 'react'
import { getMyDigitalIdCard } from '../api/client'
import LeavePage from './LeavePage'
import CommissionPage from './CommissionPage'
import PayrollPage from './PayrollPage'
import Irp5DocumentsPage from './Irp5DocumentsPage'

export default function MyProfilePage({ me }) {
  const [activeTab, setActiveTab] = useState('details')
  const [profile, setProfile] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    getMyDigitalIdCard()
      .then((data) => { if (active) setProfile(data) })
      .catch((err) => { if (active) setError(err.message || 'Profile information could not load.') })
    return () => { active = false }
  }, [])

  const tabs = [
    ['details', 'My Details'],
    ['leave', 'Leave'],
    ['commission', 'Commissions'],
    ['payslips', 'Payslips'],
    ['irp5', 'IRP5'],
  ]

  return (
    <div className="my-profile-page">
      <div className="section-header compact-header">
        <p className="eyebrow">Staff self-service</p>
        <h2>My Profile</h2>
        <p className="muted">View your staff details, submit leave and commissions, and access your payslips and IRP5 documents.</p>
      </div>
      <div className="sub-tabs profile-sub-tabs" aria-label="My Profile sections">
        {tabs.map(([id, label]) => <button key={id} type="button" className={activeTab === id ? 'active' : ''} onClick={() => setActiveTab(id)}>{label}</button>)}
      </div>

      {activeTab === 'details' ? <section className="form-card staff-profile-details">
        <h2>My Details</h2>
        {error ? <p className="error">{error}</p> : null}
        {!profile && !error ? <p>Loading profile...</p> : null}
        {profile ? <div className="profile-detail-grid">
          <div><small>Name</small><strong>{profile.full_name || me.full_name}</strong></div>
          <div><small>Role</small><strong>{profile.role_label || profile.staff_type}</strong></div>
          <div><small>Email</small><strong>{profile.email || me.email || '—'}</strong></div>
          <div><small>Contact number</small><strong>{profile.contact_number || '—'}</strong></div>
          <div><small>Franchise</small><strong>{profile.franchise_name || '—'}</strong></div>
          <div><small>Office</small><strong>{profile.office || 'Not assigned'}</strong></div>
          <div><small>Status</small><strong>{profile.status || 'Active'}</strong></div>
          <div><small>User ID</small><strong>{profile.user_id || me.id}</strong></div>
        </div> : null}
      </section> : null}
      {activeTab === 'leave' ? <LeavePage me={me} /> : null}
      {activeTab === 'commission' ? <CommissionPage me={me} /> : null}
      {activeTab === 'payslips' ? <PayrollPage me={me} /> : null}
      {activeTab === 'irp5' ? <Irp5DocumentsPage me={me} /> : null}
    </div>
  )
}
