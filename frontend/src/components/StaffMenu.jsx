import { staffPages } from '../api/staffNavigation'

export default function StaffMenu({ canManage, canImport, isEmployee, onOpen }) {
  const visible = page => {
    if (['branches', 'add'].includes(page.id)) return canManage
    if (['invoices', 'receipts', 'mortuary'].includes(page.id)) return false
    if (page.id === 'proof') return canManage || canImport
    if (page.id === 'qr') return !isEmployee
    return true
  }
  return <nav className="staff-menu-cards" aria-label="HR Staff pages">
    {staffPages.filter(visible).map(page => page.id === 'proof' ? <section className="staff-upload-proof" key={page.id} aria-labelledby="upload-proof-title">
      <strong id="upload-proof-title">Upload proof</strong>
      <p className="muted">All three documents are compulsory before any commission can be approved for payment.</p>
      <div className="staff-proof-links">{staffPages.filter(item => ['invoices', 'receipts', 'mortuary'].includes(item.id)).map(item => <div className="staff-proof-card" key={item.id}><strong>{item.title}</strong><button type="button" className="link-button" onClick={() => onOpen(item.id)}>Import file →</button></div>)}</div>
    </section> : <button type="button" className="staff-menu-card" key={page.id} onClick={() => onOpen(page.id)}>
      <strong>{page.title}</strong><span>{page.description}</span><span className="staff-menu-open" aria-hidden="true">Open →</span>
    </button>)}
  </nav>
}
