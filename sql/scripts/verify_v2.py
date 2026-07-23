from pathlib import Path
import ast
import re

ROOT = Path(__file__).resolve().parents[1]
checks = []

def check(name, value):
    checks.append((name, bool(value)))

# Parse every backend Python file.
for path in sorted((ROOT / "backend/app").rglob("*.py")):
    try:
        ast.parse(path.read_text(encoding="utf-8"))
        check(f"syntax {path.relative_to(ROOT)}", True)
    except SyntaxError:
        check(f"syntax {path.relative_to(ROOT)}", False)

staff = (ROOT / "backend/app/api/franchise_staff.py").read_text()
leave = (ROOT / "backend/app/api/leave.py").read_text()
commission = (ROOT / "backend/app/api/commission.py").read_text()
payroll = (ROOT / "backend/app/api/payroll.py").read_text()
irp5 = (ROOT / "backend/app/api/irp5.py").read_text()
attendance = (ROOT / "backend/app/api/attendance.py").read_text()
franchise = (ROOT / "backend/app/api/franchise.py").read_text()
main = (ROOT / "backend/app/main.py").read_text()
config = (ROOT / "backend/app/core/config.py").read_text()
migration = (ROOT / "backend/alembic/versions/004_stabilization_v2.py").read_text()

roles = ["Employee", "Agent", "Finance", "Admin", "Arrangement Officer", "Driver", "Cleaner", "Mortuary Assistant", "Garden Cleaner", "Tea Lady"]
for role in roles:
    check(f"employee role {role}", role in staff)
check("single employee creation endpoint", staff.count('@router.post("/employees")') == 1)
check("employee insert placeholders aligned", ":contact_number,\n            :contact_number" not in staff)
check("manager creation endpoint", '@router.post("/managers")' in staff)
check("franchise-only leave decision", "FranchiseUser" in leave and "approve" in leave and "decline" in leave)
check("commission employee directory", '/employees' in commission)
check("payroll employee privacy", "current_user.id" in payroll and "payroll_payslips" in payroll)
check("IRP5 employee privacy", "target_user_id" in irp5 and "current_user.id" in irp5)
check("QR endpoints", "office-qr" in attendance and "qr_token" in attendance)
check("business information", "business_name" in franchise and "office_address" in franchise)
check("Render database guard", "Production DATABASE_URL must point" in config)
check("consolidated migration", migration.count("ADD COLUMN IF NOT EXISTS") >= 30)
for module in ("auth", "users", "attendance", "franchise", "franchise_staff", "leave", "payroll", "irp5", "commission"):
    check(f"router {module}", f"include_router({module}.router" in main)

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("PASS" if ok else "FAIL") + " - " + name)
if failed:
    raise SystemExit(f"V2 verification failed: {len(failed)} checks")
print(f"V2 verification passed: {len(checks)} checks")
