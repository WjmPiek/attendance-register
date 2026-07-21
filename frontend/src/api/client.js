const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api'

export async function apiRequest(path, options = {}) {
  const token = localStorage.getItem('token')
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  }

  if (token) headers.Authorization = `Bearer ${token}`

  let response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers })
  } catch (err) {
    throw new Error(`Could not reach the API at ${API_BASE_URL}. Check that the backend is running and CORS is enabled.`)
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(body.detail || 'Request failed')
  }
  return response.json()
}

export async function apiBlob(path, options = {}) {
  const token = localStorage.getItem('token')
  const headers = { ...(options.headers || {}) }
  if (token) headers.Authorization = `Bearer ${token}`
  const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers })
  if (!response.ok) {
    const body = await response.text().catch(() => 'Request failed')
    throw new Error(body || 'Request failed')
  }
  return response.blob()
}

export async function login(loginName, password) {
  return apiRequest('/auth/login', { method: 'POST', body: JSON.stringify({ email: loginName, password }) })
}

export async function forgotPassword(email) {
  return apiRequest('/auth/forgot-password', { method: 'POST', body: JSON.stringify({ email }) })
}

export async function getMe() {
  return apiRequest('/auth/me')
}

export async function getRoles() {
  return apiRequest('/roles')
}

export async function getCoreEntities() {
  return apiRequest('/meta/core-entities')
}

export async function getAttendanceStatus() {
  return apiRequest('/attendance/status')
}

function buildAttendanceQuery({ userId = '', franchiseId = '', fromDate = '', toDate = '' } = {}) {
  const params = new URLSearchParams()
  if (userId) params.set('user_id', userId)
  if (franchiseId) params.set('franchise_id', franchiseId)
  if (fromDate) params.set('from_date', fromDate)
  if (toDate) params.set('to_date', toDate)
  const qs = params.toString()
  return qs ? `?${qs}` : ''
}

export async function getAttendanceHistory(filters = {}) {
  return apiRequest(`/attendance/history${buildAttendanceQuery(filters)}`)
}

export async function getAttendanceSessions(filters = {}) {
  return apiRequest(`/attendance/sessions${buildAttendanceQuery(filters)}`)
}

export async function getAttendanceVisibleUsers(franchiseId = '') {
  const qs = franchiseId ? `?franchise_id=${encodeURIComponent(franchiseId)}` : ''
  return apiRequest(`/attendance/visible-users${qs}`)
}

export async function getAttendanceFranchises() {
  return apiRequest('/attendance/franchises')
}

export async function exportAttendancePdf({ view = 'sessions', userId = '', fromDate = '', toDate = '' } = {}) {
  const params = new URLSearchParams()
  params.set('view', view)
  if (userId) params.set('user_id', userId)
  if (fromDate) params.set('from_date', fromDate)
  if (toDate) params.set('to_date', toDate)
  return apiBlob(`/attendance/export?${params.toString()}`)
}

export async function exportAttendancePdfBatch({ view = 'sessions', userIds = [], fromDate = '', toDate = '' } = {}) {
  const params = new URLSearchParams()
  params.set('view', view)
  userIds.forEach((id) => params.append('user_ids', id))
  if (fromDate) params.set('from_date', fromDate)
  if (toDate) params.set('to_date', toDate)
  return apiBlob(`/attendance/export-batch?${params.toString()}`)
}

export async function submitAttendance(action, payload) {
  return apiRequest(`/attendance/${action}`, { method: 'POST', body: JSON.stringify(payload) })
}


export async function validateOfficeQr(qrValue) {
  return apiRequest('/attendance/office-qr/validate', { method: 'POST', body: JSON.stringify({ qr_value: qrValue }) })
}

export async function getOfficeQrCodes() {
  return apiRequest('/attendance/office-qr/offices')
}

export async function downloadOfficeQrPdf(areaId) {
  return apiBlob(`/attendance/office-qr/${areaId}/pdf`)
}

export async function regenerateOfficeQr(areaId) {
  return apiRequest(`/attendance/office-qr/offices/${areaId}/regenerate`, { method: 'POST' })
}

export async function getAttendanceApprovals({ approvalStatus = 'pending', userId = '', franchiseId = '' } = {}) {
  const params = new URLSearchParams()
  params.set('approval_status', approvalStatus)
  if (userId) params.set('user_id', userId)
  if (franchiseId) params.set('franchise_id', franchiseId)
  return apiRequest(`/attendance/approvals?${params.toString()}`)
}

export async function approveAttendanceEvent(eventId, payload = {}) {
  return apiRequest(`/attendance/events/${eventId}/approve`, { method: 'POST', body: JSON.stringify(payload) })
}

export async function rejectAttendanceEvent(eventId, payload = {}) {
  return apiRequest(`/attendance/events/${eventId}/reject`, { method: 'POST', body: JSON.stringify(payload) })
}

export async function registerFranchise(payload) {
  return apiRequest('/franchise/register', { method: 'POST', body: JSON.stringify(payload) })
}

function normalizeListResponse(data) {
  if (Array.isArray(data)) return data
  if (Array.isArray(data?.items)) return data.items
  if (Array.isArray(data?.data)) return data.data
  if (Array.isArray(data?.franchises)) return data.franchises
  if (Array.isArray(data?.registrations)) return data.registrations
  return []
}

export async function getFranchiseRegistrations(statusFilter = 'pending') {
  const params = new URLSearchParams()
  params.set('status_filter', statusFilter)
  const data = await apiRequest(`/franchise/registrations?${params.toString()}`)
  return normalizeListResponse(data)
}

export async function approveFranchiseRegistration(registrationId, note = '') {
  return apiRequest(`/franchise/registrations/${registrationId}/approve`, { method: 'POST', body: JSON.stringify({ note }) })
}

export async function rejectFranchiseRegistration(registrationId, note = '') {
  return apiRequest(`/franchise/registrations/${registrationId}/reject`, { method: 'POST', body: JSON.stringify({ note }) })
}

export async function apiFetch(path, options = {}) {
  const token = localStorage.getItem('token')
  const url = path.startsWith('http') ? path : API_BASE_URL + path

  const res = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  })

  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || 'Request failed')
  }

  return res.json()
}


export async function resetStaffPassword(type, id, password) {
  return apiFetch(`/franchise-staff/${type}/${id}/reset-password`, { method: 'POST', body: JSON.stringify({ password }) })
}


export async function getMyBusinessInformation() {
  return apiRequest('/franchise/me')
}

export async function updateMyBusinessInformation(payload) {
  return apiRequest('/franchise/me', { method: 'PUT', body: JSON.stringify(payload) })
}

export async function getDashboardAlerts() {
  return apiRequest('/alerts/summary')
}

export async function getNotifications() {
  return apiRequest('/alerts/notifications')
}

export async function createManualNotification(payload) {
  return apiRequest('/alerts/notifications', { method: 'POST', body: JSON.stringify(payload) })
}

export async function markNotificationRead(notificationId) {
  return apiRequest(`/alerts/notifications/${notificationId}/read`, { method: 'POST' })
}

export async function getMyPayslips() {
  return apiRequest('/payroll/my-payslips')
}

export async function getPayrollPayslips() {
  return apiRequest('/payroll/payslips')
}

export async function downloadPayslip(id, password = '') {
  const headers = password ? { 'X-Document-Password': password } : {}
  return apiBlob(`/payroll/payslips/${id}`, { headers })
}

export async function deletePayslip(id) {
  return apiRequest(`/payroll/payslips/${id}`, { method: 'DELETE' })
}

  
export async function getIrp5Employees() {
  return apiRequest('/irp5/employees')
}

export async function uploadIrp5Document(typeOrEmployeeId, staffIdOrFile, maybeFile, maybeTaxYear = '', maybeNotes = '') {
  const type = typeof typeOrEmployeeId === 'string' ? typeOrEmployeeId : 'employees'
  const staffId = typeof typeOrEmployeeId === 'string' ? staffIdOrFile : typeOrEmployeeId
  const file = typeof typeOrEmployeeId === 'string' ? maybeFile : staffIdOrFile
  const taxYear = typeof typeOrEmployeeId === 'string' ? maybeTaxYear : maybeFile || ''
  const notes = typeof typeOrEmployeeId === 'string' ? maybeNotes : maybeTaxYear || ''
  const token = localStorage.getItem('token')
  const form = new FormData()
  form.append('file', file)
  const params = new URLSearchParams()
  if (taxYear) params.set('tax_year', taxYear)
  if (notes) params.set('notes', notes)
  const response = await fetch(`${API_BASE_URL}/irp5/${type}/${staffId}/upload?${params.toString()}`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: 'Upload failed' }))
    throw new Error(body.detail || 'Upload failed')
  }
  return response.json()
}

export async function getMyIrp5Documents() {
  return apiRequest('/irp5/my-documents')
}

export async function getIrp5Documents() {
  return apiRequest('/irp5/documents')
}

export async function downloadIrp5Document(documentId, password = '') {
  const headers = password ? { 'X-Document-Password': password } : {}
  return apiBlob(`/irp5/documents/${documentId}/download`, { headers })
}

export async function deleteIrp5Document(documentId) {
  return apiRequest(`/irp5/documents/${documentId}`, { method: 'DELETE' })
}

export async function previewIrp5Document(documentId, password = '') {
  return downloadIrp5Document(documentId, password)
}


export async function applyLeave(payload) {
  return apiRequest('/leave/apply', { method: 'POST', body: JSON.stringify(payload) })
}

export async function getLeaveApplications(status = '') {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  const qs = params.toString()
  return apiRequest(`/leave/applications${qs ? `?${qs}` : ''}`)
}

export async function approveLeaveApplication(id, note = '') {
  return apiRequest(`/leave/applications/${id}/approve`, { method: 'POST', body: JSON.stringify({ note }) })
}

export async function declineLeaveApplication(id, note = '') {
  return apiRequest(`/leave/applications/${id}/decline`, { method: 'POST', body: JSON.stringify({ note }) })
}


export async function importPayrollDocument(file, payrollMonth = '') {
  const token = localStorage.getItem('token')
  const form = new FormData()
  form.append('file', file)
  if (payrollMonth) form.append('payroll_month', payrollMonth)
  const response = await fetch(`${API_BASE_URL}/payroll/import-document`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: 'Payroll import failed' }))
    throw new Error(body.detail || 'Payroll import failed')
  }
  return response.json()
}

export async function getPayrollImports() {
  return apiRequest('/payroll/imports')
}

export async function getPayrollImportDetail(id) {
  return apiRequest(`/payroll/imports/${id}`)
}

export async function updatePayrollImport(id, payload) {
  return apiRequest(`/payroll/imports/${id}`, { method: 'PUT', body: JSON.stringify(payload) })
}

export async function deletePayrollImport(id) {
  return apiRequest(`/payroll/imports/${id}`, { method: 'DELETE' })
}


export async function uploadStaffIdPhoto(type, id, file) {
  const token = localStorage.getItem('token')
  const form = new FormData()
  form.append('file', file)
  const response = await fetch(`${API_BASE_URL}/franchise-staff/${type}/${id}/photo`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: 'Photo upload failed' }))
    throw new Error(body.detail || 'Photo upload failed')
  }
  return response.json()
}

export async function downloadStaffIdCards(franchiseId = '', staffType = '', staffId = '') {
  const params = new URLSearchParams()
  if (franchiseId) params.set('franchise_id', franchiseId)
  if (staffType) params.set('staff_type', staffType)
  if (staffId) params.set('staff_id', staffId)
  const qs = params.toString()
  return apiBlob(`/franchise-staff/id-cards/export${qs ? `?${qs}` : ''}`)
}

export async function updateFranchiseRegistration(registrationId, payload) {
  const attempts = [
    [`/franchise/registrations/${registrationId}`, 'PUT'],
    [`/franchise/registrations/${registrationId}`, 'PATCH'],
    [`/franchise/registrations/${registrationId}/edit`, 'POST'],
    [`/franchise/registrations/${registrationId}/edit`, 'PUT'],
    [`/franchise/registrations/${registrationId}/edit`, 'PATCH'],
  ]

  let lastError
  for (const [path, method] of attempts) {
    try {
      return await apiRequest(path, { method, body: JSON.stringify(payload) })
    } catch (err) {
      lastError = err
      // Only try the compatibility endpoints when the route is missing.
      // Validation/permission errors should be shown immediately.
      if (!String(err.message || '').toLowerCase().includes('not found')) throw err
    }
  }
  throw lastError || new Error('Failed to update franchise')
}

export async function getMyDigitalIdCard() {
  return apiRequest('/franchise-staff/id-card/me')
}

export async function updateFranchiseUser(franchiseUserId, payload) {
  return apiRequest(`/franchise/users/${franchiseUserId}`, { method: 'PATCH', body: JSON.stringify(payload) })
}

export async function getFranchiseUsers() {
  return apiRequest('/franchise/users')
}

export async function getMyFranchiseProfile() {
  return apiRequest('/franchise/me')
}

export async function updateMyFranchiseProfile(payload) {
  return apiRequest('/franchise/me', { method: 'PATCH', body: JSON.stringify(payload) })
}

export async function updateOfficeLocation(areaId, payload) {
  return apiRequest(`/attendance/office-qr/offices/${areaId}/location`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export async function updateOfficeDetails(areaId, payload) {
  return apiRequest(`/attendance/office-qr/offices/${areaId}`, { method: 'PATCH', body: JSON.stringify(payload) })
}

export async function deleteOffice(areaId) {
  return apiRequest(`/attendance/office-qr/offices/${areaId}`, { method: 'DELETE' })
}

export async function getOfficeLinkedStaff(areaId) {
  return apiRequest(`/attendance/office-qr/offices/${areaId}/linked-staff`)
}

export async function reassignOfficeLinkedStaff(areaId, newAddress) {
  return apiRequest(`/attendance/office-qr/offices/${areaId}/reassign-linked-staff`, {
    method: 'POST',
    body: JSON.stringify({ new_address: newAddress }),
  })
}
export async function getCommissionTypes() { return apiRequest('/commission/types') }
export async function getCommissionEmployees() { return apiRequest('/commission/employees') }
export async function getCommissionStructures() { return apiRequest('/commission/structures') }
export async function saveCommissionStructure(payload) { return apiRequest('/commission/structures', { method: 'POST', body: JSON.stringify(payload) }) }
export async function getCommissionEntries(filters = {}) {
  const params = new URLSearchParams()
  if (filters.employeeUserId) params.set('employee_user_id', filters.employeeUserId)
  if (filters.fromDate) params.set('from_date', filters.fromDate)
  if (filters.toDate) params.set('to_date', filters.toDate)
  if (filters.status) params.set('status', filters.status)
  if (filters.search) params.set('search', filters.search)
  const qs = params.toString()
  return apiRequest(`/commission/entries${qs ? `?${qs}` : ''}`)
}
export async function createCommissionEntry(payload) { return apiRequest('/commission/entries', { method: 'POST', body: JSON.stringify(payload) }) }
export async function deleteCommissionEntry(id) { return apiRequest(`/commission/entries/${id}`, { method: 'DELETE' }) }
export async function reviewCommissionEntry(id, payload) { return apiRequest(`/commission/entries/${id}/review`, { method: 'PUT', body: JSON.stringify(payload) }) }
export async function bulkReviewCommissionEntries(payload) { return apiRequest('/commission/entries/bulk-review', { method: 'POST', body: JSON.stringify(payload) }) }
export async function downloadCommissionForm(id) { return apiBlob(`/commission/entries/${id}/form.pdf`) }
export async function downloadCommissionReport(filters = {}) {
  const params = new URLSearchParams()
  if (filters.employeeUserId) params.set('employee_user_id', filters.employeeUserId)
  if (filters.fromDate) params.set('from_date', filters.fromDate)
  if (filters.toDate) params.set('to_date', filters.toDate)
  return apiBlob(`/commission/report.pdf${params.toString() ? `?${params}` : ''}`)
}
