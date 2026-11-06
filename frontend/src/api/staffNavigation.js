import { useEffect, useState } from 'react'

export const staffPages = [
  { id: 'documents', title: 'Commission documents', description: 'Monthly uploads, payment balances, document corrections and activity log.' },
  { id: 'proof', title: 'Upload proof', description: 'Import the compulsory service and payment documents.' },
  { id: 'branches', title: 'All Branches & Commissions', description: 'Staff, commission permissions and reports for every linked branch.' },
  { id: 'invoices', title: 'MF Invoice', description: 'Import and download the original service invoice.' },
  { id: 'receipts', title: 'MF File Receipt', description: 'Import receipts and allocate eligible employee commissions.' },
  { id: 'mortuary', title: 'Mortuary Book', description: 'Import removal records and match drivers and assistants.' },
  { id: 'view', title: 'View Staff', description: 'View and manage your employees and managers.' },
  { id: 'add', title: 'Add New Employee', description: 'Create an employee or manager and choose their home branch.' },
  { id: 'qr', title: 'Office Attendance Codes', description: 'View office QR codes and issue attendance codes.' },
  { id: 'payslips', title: 'My Payslips', description: 'Open and download your payslips.' },
]

function readPage() {
  const params = new URLSearchParams(window.location.search)
  const page = params.get('staff_page') || 'menu'
  return { page: [...staffPages.map(p => p.id), 'card'].includes(page) ? page : 'menu',
    action: params.get('staff_action') || '', employee: params.get('staff_employee') || '', branch: params.get('staff_branch') || '' }
}

export function useStaffNavigation(tab = 'staff') {
  const [route, setRoute] = useState(readPage)
  useEffect(() => {
    const sync = () => setRoute(readPage())
    window.addEventListener('popstate', sync)
    return () => window.removeEventListener('popstate', sync)
  }, [])
  const navigate = (page, details = {}) => {
    const url = new URL(window.location.href)
    url.searchParams.set('tab', tab)
    for (const key of ['page', 'action', 'employee', 'branch']) url.searchParams.delete(`staff_${key}`)
    if (page !== 'menu') url.searchParams.set('staff_page', page)
    for (const key of ['action', 'employee', 'branch']) if (details[key]) url.searchParams.set(`staff_${key}`, details[key])
    window.history.pushState({}, '', url)
    setRoute(readPage())
  }
  useEffect(() => { window.scrollTo(0, 0) }, [route.page, route.action, route.employee, route.branch])
  return [route, navigate]
}
