import { useEffect, useState } from 'react'
import BusinessInformationPage from './BusinessInformationPage'
import CommissionSettingsPage from './CommissionSettingsPage'

const readPage = () => new URLSearchParams(window.location.search).get('business_page') === 'rates' ? 'rates' : 'profile'

export default function BusinessPage() {
  const [page, setPage] = useState(readPage)
  useEffect(() => {
    const sync = () => setPage(readPage())
    window.addEventListener('popstate', sync)
    return () => window.removeEventListener('popstate', sync)
  }, [])
  const open = next => {
    const url = new URL(window.location.href)
    url.searchParams.set('business_page', next)
    window.history.pushState({}, '', url)
    setPage(next)
  }
  return <section className="card attendance-tab-panel business-tab-page">
    <header className="tab-page-intro"><h3>Business</h3><p>Manage your business information and commission settings.</p></header>
    <nav className="staff-page-navigation" aria-label="Business subtabs">
      <button type="button" className={page === 'profile' ? 'primary-button' : 'glass-button'} aria-current={page === 'profile' ? 'page' : undefined} onClick={() => open('profile')}>Business Information</button>
      <button type="button" className={page === 'rates' ? 'primary-button' : 'glass-button'} aria-current={page === 'rates' ? 'page' : undefined} onClick={() => open('rates')}>Commissions</button>
    </nav>
    {page === 'rates' ? <CommissionSettingsPage /> : <BusinessInformationPage />}
  </section>
}
