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
import CommissionPage from './CommissionPage'
import BusinessInformationPage from './BusinessInformationPage'
import DigitalIdCard from '../components/DigitalIdCard'
import { getNotifications, markNotificationRead } from '../api/client'
import { formatJohannesburgDateTime } from '../utils/dateTime'

function AttendanceExceptionPopup({ me, onNavigate }) {
  const canReceive = me.roles.includes('FranchiseUser') || me.roles.includes('ManagerUser')
  const [notification, setNotification] = useState(null)

  useEffect(() => {
    if (!canReceive) return undefined
    let active = true
    const poll = async () => {
      try {
        const items = await getNotifications()
        if (!active) return
        const next = (Array.isArray(items) ? items : []).find((item) => (
          item.notification_type === 'attendance_outside_area'
          && !item.is_read
          && Number(item.recipient_user_id) === Number(me.id)
        ))
        setNotification((current) => current?.id === next?.id ? current : (next || null))
      } catch {
        // Normal page error handling remains available; popup polling is non-blocking.
      }
    }
    poll()
    const timer = window.setInterval(poll, 10000)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [canReceive, me.id])

  if (!notification) return null

  const close = async (openTarget = false) => {
    try {
      await markNotificationRead(notification.id)
    } catch {
      // The popup can still close if the read receipt cannot be saved.
    }
    const target = notification.related_table === 'attendance_events' ? 'approvals' : notification.target_tab
    setNotification(null)
    if (openTarget && target) onNavigate(target)
  }

  return (
    <div className="attendance-alert-backdrop" role="alertdialog" aria-modal="true" aria-labelledby="attendance-alert-title">
      <section className="attendance-alert-popup">
        <p className="eyebrow">GPS attendance warning</p>
        <h2 id="attendance-alert-title">{notification.subject}</h2>
        <p>{notification.message}</p>
        <small>{formatJohannesburgDateTime(notification.created_at)}</small>
        <div className="button-row">
          <button type="button" className="danger-button" onClick={() => close(true)}>Open attendance record</button>
          <button type="button" className="glass-button" onClick={() => close(false)}>Dismiss</button>
        </div>
      </section>
    </div>
  )
}

export default function DashboardPage({ me, roles, entities, onLogout }) {
  const isSuperUser = me.roles.includes('SuperUser')
  const isFranchiseUser = me.roles.includes('FranchiseUser')
  const isManagerUser = me.roles.includes('ManagerUser')
  const isEmployee = me.roles.includes('EmployeeUser')
  const isFinanceEmployee = (me.employee_role || '').trim().toLowerCase().includes('finance')
  const isStaffSelfService = isEmployee || isManagerUser
  const canManagePayroll = isSuperUser || isFranchiseUser || isFinanceEmployee
  const canUsePayroll = canManagePayroll || isStaffSelfService
  const isSignCapable = isEmployee || isManagerUser || isSuperUser
  const isApprovalCapable = isSuperUser || isFranchiseUser || isManagerUser

  const [isMobileLayout, setIsMobileLayout] = useState(() => window.matchMedia('(max-width: 760px)').matches)

  useEffect(() => {
    const media = window.matchMedia('(max-width: 760px)')
    const update = () => setIsMobileLayout(media.matches)
    update()
    if (media.addEventListener) {
      media.addEventListener('change', update)
      return () => media.removeEventListener('change', update)
    }
    media.addListener(update)
    return () => media.removeListener(update)
  }, [])

  const fullTabs = useMemo(() => [
    { id: 'home', label: 'Overview', visible: !isEmployee || isFinanceEmployee || isSuperUser || isFranchiseUser },
    { id: 'attendance', label: 'Mobile Sign In', visible: isSignCapable },
    { id: 'employee-card', label: 'Employee Card', visible: isEmployee || isManagerUser },
    { id: 'history', label: 'History', visible: isSignCapable || isApprovalCapable },
    { id: 'approvals', label: 'Approvals', visible: isSuperUser || isFranchiseUser || isManagerUser },
    { id: 'staff', label: isSuperUser ? 'HR Staff' : (isManagerUser ? 'My Staff' : 'My Profile'), visible: isSuperUser || isManagerUser || isEmployee },
    { id: 'business', label: 'Business Information', visible: isFranchiseUser },
    { id: 'franchises', label: 'Franchise Approvals', visible: isSuperUser },
    { id: 'leave', label: 'Leave', visible: isEmployee || isManagerUser || isFranchiseUser || isSuperUser },
    { id: 'commission', label: 'Commission & Overtime', visible: isFranchiseUser || isManagerUser || isEmployee || isSuperUser },
    { id: 'payroll', label: canManagePayroll ? 'Payroll' : 'Payslips', visible: canUsePayroll },
    { id: 'irp5', label: canManagePayroll ? 'IRP 5 Uploads' : 'My IRP 5', visible: isStaffSelfService || isFranchiseUser || isSuperUser },
  ].filter((tab) => tab.visible), [isSignCapable, isApprovalCapable, isSuperUser, isFranchiseUser, isEmployee, isManagerUser, isFinanceEmployee, isStaffSelfService, canManagePayroll, canUsePayroll])

  const mobileStaffTabs = useMemo(() => [
    { id: 'attendance', label: 'Mobile Sign In', visible: isSignCapable },
    { id: 'staff', label: 'My Staff', visible: isManagerUser },
    { id: 'staff', label: 'My Profile', visible: isEmployee },
    { id: 'employee-card', label: 'Employee Card', visible: isEmployee || isManagerUser },
    { id: 'history', label: 'History', visible: isSignCapable || isApprovalCapable },
    { id: 'approvals', label: 'Approvals', visible: isManagerUser },
    { id: 'leave', label: 'Leave', visible: isEmployee || isManagerUser },
    { id: 'commission', label: 'Commission & Overtime', visible: isEmployee || isManagerUser },
    { id: 'payroll', label: 'Payslips', visible: canUsePayroll },
    { id: 'irp5', label: 'My IRP 5', visible: isStaffSelfService },
  ].filter((tab) => tab.visible), [isSignCapable, isApprovalCapable, isEmployee, isManagerUser, canUsePayroll, isStaffSelfService])

  const tabs = isMobileLayout && isStaffSelfService && !canManagePayroll ? mobileStaffTabs : fullTabs
  const queryParams = new URLSearchParams(window.location.search)
  const defaultTab = queryParams.get('office_qr') ? 'attendance' : (queryParams.get('tab') || 'home')
  const shouldStartOnMobileMenu = isMobileLayout && isStaffSelfService && !canManagePayroll && !queryParams.get('tab') && !queryParams.get('office_qr')
  const [activeTab, setActiveTab] = useState(shouldStartOnMobileMenu ? null : (tabs.some((tab) => tab.id === defaultTab) ? defaultTab : (tabs[0]?.id || 'attendance')))

  useEffect(() => {
    if (isMobileLayout && isStaffSelfService && !canManagePayroll && activeTab === 'home') {
      setActiveTab(null)
      const url = new URL(window.location.href)
      url.searchParams.delete('tab')
      window.history.replaceState({}, '', url)
    }
  }, [isMobileLayout, isStaffSelfService, canManagePayroll, activeTab])
  const openTab = (tabId) => {
    setActiveTab(tabId)
    const url = new URL(window.location.href)
    url.searchParams.set('tab', tabId)
    window.history.replaceState({}, '', url)
  }

  const goBackToMobileMenu = () => {
    setActiveTab(null)
    const url = new URL(window.location.href)
    url.searchParams.delete('tab')
    window.history.replaceState({}, '', url)
  }

  const showMobileStaffMenuOnly = isMobileLayout && isStaffSelfService && !canManagePayroll && activeTab === null
  const showMobileStaffContentOnly = isMobileLayout && isStaffSelfService && !canManagePayroll && activeTab !== null

  return (
    <div className={showMobileStaffMenuOnly ? 'app-shell mobile-staff-menu-shell' : (showMobileStaffContentOnly ? 'app-shell mobile-staff-content-shell' : 'app-shell')}>
      <AttendanceExceptionPopup me={me} onNavigate={openTab} />
      {!showMobileStaffContentOnly ? <aside className="sidebar glass-card">
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
      </aside> : null}

      {!showMobileStaffMenuOnly ? <main className="page content-panel">
        {showMobileStaffContentOnly ? (
          <div className="mobile-page-header glass-card">
            <button type="button" className="glass-button" onClick={goBackToMobileMenu}>Back to menu</button>
            <strong>{tabs.find((tab) => tab.id === activeTab)?.label || 'Page'}</strong>
          </div>
        ) : null}
        {activeTab === 'home' ? <OverviewDashboardPage me={me} onNavigate={openTab} /> : null}
        {activeTab === 'attendance' && isSignCapable ? <MobileAttendancePage me={me} onDone={goBackToMobileMenu} /> : null}
        {activeTab === 'employee-card' && (isEmployee || isManagerUser) ? <DigitalIdCard /> : null}
        {activeTab === 'history' && (isSignCapable || isApprovalCapable) ? <AttendanceHistoryPage me={me} /> : null}
        {activeTab === 'approvals' && (isSuperUser || isFranchiseUser || isManagerUser) ? <AttendanceApprovalPage me={me} /> : null}
        {activeTab === 'staff' && (isSuperUser || isManagerUser || isEmployee) ? <FranchiseStaffPage me={me} onNavigate={openTab} /> : null}
        {activeTab === 'business' && isFranchiseUser ? <BusinessInformationPage /> : null}
        {activeTab === 'franchises' && isSuperUser ? <FranchiseRegistrationApprovalPage me={me} /> : null}
        {activeTab === 'leave' ? <LeavePage me={me} /> : null}
        {activeTab === 'commission' ? <CommissionPage me={me} /> : null}
        {activeTab === 'payroll' && canUsePayroll ? <PayrollPage me={me} /> : null}
        {activeTab === 'irp5' ? <Irp5DocumentsPage me={me} /> : null}
      </main> : null}
    </div>
  )
}
