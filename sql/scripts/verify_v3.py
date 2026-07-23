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
staff = (ROOT/'backend/app/api/franchise_staff.py').read_text()
commission = (ROOT/'backend/app/api/commission.py').read_text()
auth = (ROOT/'backend/app/api/auth.py').read_text()
login = (ROOT/'frontend/src/pages/LoginPage.jsx').read_text()
business = (ROOT/'frontend/src/pages/BusinessInformationPage.jsx').read_text()
mobile = (ROOT/'frontend/src/pages/MobileAttendancePage.jsx').read_text()
user_mgmt = (ROOT/'backend/app/api/user_management.py').read_text()

for table in ('notifications','leave_applications','payroll_imports','payroll_import_rows','payroll_payslips','irp5_documents'):
    check(f'migration owns {table}', table in migration)
for role in ('Employee','Agent','Finance','Admin','Arrangement Officer','Driver','Cleaner','Mortuary Assistant','Garden Cleaner','Tea Lady'):
    check(f'role {role}', role in staff)
check('single employee create endpoint', staff.count('@router.post("/employees")') == 1)
check('single manager create endpoint', staff.count('@router.post("/managers")') == 1)
check('manager commission participant', 'manager_users' in commission and "kind == \"manager\"" in commission)
check('commission notifications', '_notify(' in commission)
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
