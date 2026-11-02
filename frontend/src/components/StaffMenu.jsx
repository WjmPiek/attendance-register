import { staffPages } from '../api/staffNavigation'

export default function StaffMenu({ canManage, canImport, isEmployee, onOpen }) {
  const visible = page => {
    if (['branches', 'add'].includes(page.id)) return canManage
    if (['receipts', 'mortuary'].includes(page.id)) return canManage || canImport
    if (page.id === 'qr') return !isEmployee
    return true
  }
  return <nav className="staff-menu-cards" aria-label="HR Staff pages">
    {staffPages.filter(visible).map(page => <button type="button" className="staff-menu-card" key={page.id} onClick={() => onOpen(page.id)}>
      <strong>{page.title}</strong><span>{page.description}</span><span className="staff-menu-open" aria-hidden="true">Open →</span>
    </button>)}
  </nav>
}
