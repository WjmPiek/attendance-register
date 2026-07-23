from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
checks = []

def check(name, condition):
    checks.append((name, bool(condition)))

main = (ROOT/'backend/app/main.py').read_text()
client = (ROOT/'frontend/src/api/client.js').read_text()
dashboard = (ROOT/'frontend/src/pages/DashboardPage.jsx').read_text()
leave = (ROOT/'backend/app/api/leave.py').read_text()
staff = (ROOT/'backend/app/api/franchise_staff.py').read_text()
commission = (ROOT/'backend/app/api/commission.py').read_text()
payroll = (ROOT/'backend/app/api/payroll.py').read_text()
irp5 = (ROOT/'backend/app/api/irp5.py').read_text()
attendance = (ROOT/'backend/app/api/attendance.py').read_text()
franchise = (ROOT/'backend/app/api/franchise.py').read_text()

for module in ('auth','attendance','franchise','franchise_staff','alerts','irp5','leave','payroll','commission'):
    check(f'router mounted: {module}', f'app.include_router({module}.router' in main)
check('single frontend auth token source', "localStorage.getItem('token')" not in client and "getAccessToken()" in client)
check('401 invalidates session centrally', 'response.status === 401' in client and 'clearAccessToken' in client)
for role in ('FranchiseUser','ManagerUser','EmployeeUser'):
    check(f'role represented: {role}', role in dashboard and (role in staff or role == 'EmployeeUser'))
check('Agent supported as employee role', '"Agent"' in staff and "'Agent'" in (ROOT/'frontend/src/pages/FranchiseStaffPage.jsx').read_text())
check('Employee supported as employee role', '"Employee"' in staff)
check('leave decisions franchise-only', "if 'FranchiseUser' not in roles" in leave)
check('commission module present', '/entries' in commission and '/employees' in commission)
check('payroll self privacy present', 'ONLY see their own payslip' in payroll)
check('irp5 self privacy present', 'ONLY see their own IRP5' in irp5)
check('QR validation endpoint present', 'office-qr/validate' in attendance)
check('business information endpoint present', 'update_my_franchise_profile' in franchise)

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(('PASS' if ok else 'FAIL') + ' - ' + name)
if failed:
    raise SystemExit(f'Workflow verification failed: {len(failed)} check(s)')
print(f'Workflow verification passed: {len(checks)} checks')
