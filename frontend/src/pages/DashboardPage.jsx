import { useEffect, useMemo, useState } from 'react'
import AttendanceApprovalPage from './AttendanceApprovalPage'
import AttendanceHistoryPage from './AttendanceHistoryPage'
import MobileAttendancePage from './MobileAttendancePage'
import FranchiseRegistrationApprovalPage from './FranchiseRegistrationApprovalPage'
import FranchiseStaffPage from './FranchiseStaffPage'
import OverviewDashboardPage from './OverviewDashboardPage'
import Irp5DocumentsPage from './Irp5DocumentsPage'
import LeavePage from './LeavePage'
import PayrollPage from './PayrollPage'

export default function DashboardPage({ me, roles, entities, onLogout }) {
  const isSuperUser = me.roles.includes('SuperUser')
  const isFranchiseUser = me.roles.includes('FranchiseUser')
  const isManagerUser = me.roles.includes('ManagerUser')
  const isEmployee = me.roles.includes('EmployeeUser')
  const isFinanceEmployee = (me.employee_role || '').trim().toLowerCase().includes('finance')
  const canUsePayroll = isSuperUser || isFranchiseUser || isFinanceEmployee
  const isSignCapable = isEmployee || isManagerUser || isSuperUser
  const isApprovalCapable = isSuperUser || isFranchiseUser || isManagerUser

  const tabs = useMemo(() => [
    { id: 'home', label: 'Overview', visible: !isEmployee || isFinanceEmployee || isSuperUser || isFranchiseUser },
    { id: 'attendance', label: 'Mobile Sign In', visible: isSignCapable },
    { id: 'history', label: 'History', visible: isSignCapable || isApprovalCapable },
    { id: 'approvals', label: 'Approvals', visible: isApprovalCapable },
    { id: 'staff', label: 'HR Staff', visible: isSuperUser || isFranchiseUser },
    { id: 'franchises', label: 'Franchise Approvals', visible: isSuperUser },
    { id: 'leave', label: 'Leave', visible: isEmployee || isManagerUser || isFranchiseUser || isSuperUser },
    { id: 'payroll', label: 'Payroll', visible: canUsePayroll },
    { id: 'irp5', label: isFinanceEmployee ? 'IRP 5 Uploads' : 'My IRP 5', visible: isEmployee || isFranchiseUser || isSuperUser },
  ].filter((tab) => tab.visible), [isSignCapable, isApprovalCapable, isSuperUser, isFranchiseUser, isEmployee, isManagerUser, isFinanceEmployee, canUsePayroll])

  const defaultTab = new URLSearchParams(window.location.search).get('tab') || 'home'
  const [activeTab, setActiveTab] = useState(tabs.some((tab) => tab.id === defaultTab) ? defaultTab : (tabs[0]?.id || 'attendance'))
  const openTab = (tabId) => {
    setActiveTab(tabId)
    const url = new URL(window.location.href)
    url.searchParams.set('tab', tabId)
    window.history.replaceState({}, '', url)
  }


  return (
    <div className="app-shell">
      <aside className="sidebar glass-card">
        <div className="brand-block">
          <img src="/logo.png" alt="Martins logo" />
          <div>
            <strong>Attendance</strong>
            <span>Register Platform</span>
          </div>
        </div>
        <nav className="sidebar-tabs" aria-label="Main sections">
          {tabs.map((tab) => (
            <button key={tab.id} type="button" className={activeTab === tab.id ? 'tab-button active' : 'tab-button'} onClick={() => openTab(tab.id)}>
              {tab.label}
            </button>
          ))}
        </nav>
        <button className="logout-button glass-button" onClick={onLogout}>Logout</button>
      </aside>

      <main className="page content-panel">
        {activeTab === 'home' ? <OverviewDashboardPage me={me} onNavigate={openTab} /> : null}
        {activeTab === 'attendance' && isSignCapable ? <MobileAttendancePage me={me} /> : null}
        {activeTab === 'history' && (isSignCapable || isApprovalCapable) ? <AttendanceHistoryPage me={me} /> : null}
        {activeTab === 'approvals' && isApprovalCapable ? <AttendanceApprovalPage me={me} /> : null}
        {activeTab === 'staff' && (isSuperUser || isFranchiseUser) ? <FranchiseStaffPage me={me} /> : null}
        {activeTab === 'franchises' && isSuperUser ? <FranchiseRegistrationApprovalPage me={me} /> : null}
        {activeTab === 'leave' ? <LeavePage me={me} /> : null}
        {activeTab === 'payroll' && canUsePayroll ? <PayrollPage me={me} /> : null}
        {activeTab === 'irp5' ? <Irp5DocumentsPage me={me} /> : null}
      </main>
    </div>
  )
}
