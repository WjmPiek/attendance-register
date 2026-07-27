from pathlib import Path
import ast
import re

ROOT = Path(__file__).resolve().parents[1]
checks = []

def check(name, condition):
    checks.append((name, bool(condition)))

for path in sorted((ROOT / 'backend').rglob('*.py')):
    try:
        ast.parse(path.read_text(encoding='utf-8'))
        check(f'syntax {path.relative_to(ROOT)}', True)
    except SyntaxError:
        check(f'syntax {path.relative_to(ROOT)}', False)

migration = (ROOT/'backend/alembic/versions/006_v3_operational_schema.py').read_text()
staff_integrity_migration = (ROOT/'backend/alembic/versions/007_staff_hierarchy_integrity.py').read_text()
optional_email_migration = (ROOT/'backend/alembic/versions/008_optional_staff_email.py').read_text()
commission_migration = (ROOT/'backend/alembic/versions/009_commission_workflow.py').read_text()
staff = (ROOT/'backend/app/api/franchise_staff.py').read_text()
commission = (ROOT/'backend/app/api/commission.py').read_text()
auth = (ROOT/'backend/app/api/auth.py').read_text()
login = (ROOT/'frontend/src/pages/LoginPage.jsx').read_text()
business = (ROOT/'frontend/src/pages/BusinessInformationPage.jsx').read_text()
mobile = (ROOT/'frontend/src/pages/MobileAttendancePage.jsx').read_text()
franchise_staff_page = (ROOT/'frontend/src/pages/FranchiseStaffPage.jsx').read_text()
frontend_client = (ROOT/'frontend/src/api/client.js').read_text()
user_mgmt = (ROOT/'backend/app/api/user_management.py').read_text()

for table in ('notifications','leave_applications','payroll_imports','payroll_import_rows','payroll_payslips','irp5_documents'):
    check(f'migration owns {table}', table in migration)
for role in ('Employee','Agent','Finance','Admin','Arrangement Officer','Driver','Cleaner','Mortuary Assistant','Garden Cleaner','Tea Lady'):
    check(f'role {role}', role in staff)
check('single employee create endpoint', staff.count('@router.post("/employees")') == 1)
check('single manager create endpoint', staff.count('@router.post("/managers")') == 1)
check('staff hierarchy migration head', 'fk_employee_manager_same_franchise' in staff_integrity_migration)
check('username-only account migration', 'ALTER COLUMN email DROP NOT NULL' in optional_email_migration)
check('username persisted during staff creation', 'username=normalised_username' in staff)
check('superuser franchise staff scope', 'requested_franchise_user_id' in staff)
check('superuser unscoped staff hidden', staff.count('if franchise_user_id is None:\n            return []') >= 2)
check('superuser explicit franchise selection', 'Managers and employees remain hidden until you select their franchise.' in franchise_staff_page)
check('franchise user response normalized', "return normalizeListResponse(await apiRequest('/franchise/users'))" in frontend_client)
check('HR staff uses normalized franchise users', 'getFranchiseUsers()' in franchise_staff_page)
check('manager staff visibility scope', 's.manager_user_id = :manager_user_id' in staff)
check('generic creation rejects profile roles', 'Organisational users must be created' in (ROOT/'backend/app/api/users.py').read_text())
check('manager commission participant', 'manager_users' in commission and "kind == \"manager\"" in commission)
check('manager commission totals exclude employee totals', "Keep the manager's own totals separate" in commission and '(c.employee_user_id=:uid OR ep.manager_user_id=:mid)' not in commission)
check('commission staff exposes manager hierarchy id', 'NULL::integer AS manager_profile_id' in commission and 'm.user_id, m.franchise_user_id, NULL, m.id' in commission)
check('commission notifications', '_notify(' in commission)
check('commission workflow migration head', '009_commission_workflow' in commission_migration)
check('commission joinings', '"joinings"' in commission)
check('commission duplicate protection', '_assert_not_duplicate' in commission)
check('commission duplicate query avoids ambiguous nullable parameter', 'exclude_clause = ""' in commission and ':exclude_id IS NULL' not in commission)
check('commission insert avoids mixed status parameter types', 'CASE WHEN :status' not in commission and ':reviewed_at,:reviewed_by' in commission)
check('commission self-review protection', 'You cannot approve or reject your own submission' in commission)
check('commission pending-only review', 'Only a pending submission can be reviewed' in commission)
check('commission cancellation retains history', "status='cancelled'" in commission and 'DELETE FROM commission_entries' not in commission)
check('commission audit history endpoint', "@router.get('/entries/{entry_id}/history')" in commission)
check('commission scoped single-entry notification endpoint', "@router.get('/entries/{entry_id}')" in commission and 'getCommissionEntry(id)' in (ROOT/'frontend/src/pages/CommissionPage.jsx').read_text(encoding='utf-8'))
check('superuser commission franchise scope', 'Select a franchise user to view only that franchise' in (ROOT/'frontend/src/pages/CommissionPage.jsx').read_text(encoding='utf-8'))
check('commission review uses PDF workspace', 'commission-review-workspace' in (ROOT/'frontend/src/pages/CommissionPage.jsx').read_text(encoding='utf-8') and 'Review PDF' in (ROOT/'frontend/src/pages/CommissionPage.jsx').read_text(encoding='utf-8'))
check('commission review is dedicated internal page', 'if(editing){' in (ROOT/'frontend/src/pages/CommissionPage.jsx').read_text(encoding='utf-8') and '← Back to commissions' in (ROOT/'frontend/src/pages/CommissionPage.jsx').read_text(encoding='utf-8'))
check('manager linked employee commission selector', 'Employees linked to me' in (ROOT/'frontend/src/pages/CommissionPage.jsx').read_text(encoding='utf-8') and 'viewingLinkedEmployee' in (ROOT/'frontend/src/pages/CommissionPage.jsx').read_text(encoding='utf-8'))
check('franchise commission hierarchy view', 'Managers and linked employees' in (ROOT/'frontend/src/pages/CommissionPage.jsx').read_text(encoding='utf-8') and 'commission-manager-group' in (ROOT/'frontend/src/pages/CommissionPage.jsx').read_text(encoding='utf-8'))
check('commission notification opens focused claimant', "sessionStorage.removeItem('commissionFocusId')" in (ROOT/'frontend/src/pages/CommissionPage.jsx').read_text(encoding='utf-8') and 'await openEmployee(employee)' in (ROOT/'frontend/src/pages/CommissionPage.jsx').read_text(encoding='utf-8'))
check('notification click navigates after marking read', 'openNotification(n)' in (ROOT/'frontend/src/pages/OverviewDashboardPage.jsx').read_text(encoding='utf-8'))
check('danger button text is white', 'color: #fff !important' in (ROOT/'frontend/src/styles.css').read_text(encoding='utf-8'))
check('forgot password endpoint', '@router.post("/forgot-password")' in auth)
check('reset password endpoint', '@router.post("/reset-password")' in auth)
check('show password control', 'showPassword' in login or 'type={showPassword' in login)
check('additional office UI', 'additional' in business.lower() and 'office' in business.lower())
check('mobile done navigation', 'Done' in mobile and ('navigate' in mobile or 'onDone' in mobile))
check('protected superuser', 'wjm@martinsdirect.com' in user_mgmt.lower())
check('idempotent migration 002', 'inspect' in (ROOT/'backend/alembic/versions/002_employee_number.py').read_text())
check('idempotent migration 003', 'inspect' in (ROOT/'backend/alembic/versions/003_payslip_documents.py').read_text())

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(('PASS' if ok else 'FAIL') + ' - ' + name)
if failed:
    raise SystemExit(f'Version 3 verification failed: {len(failed)} checks')
print(f'Version 3 verification passed: {len(checks)} checks')
