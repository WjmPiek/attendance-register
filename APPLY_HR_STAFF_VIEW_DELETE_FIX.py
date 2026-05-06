
from pathlib import Path

ROOT = Path.cwd()
backend = ROOT / 'backend' / 'app' / 'api' / 'franchise_staff.py'
frontend = ROOT / 'frontend' / 'src' / 'pages' / 'FranchiseStaffPage.jsx'

if not backend.exists():
    raise SystemExit(f'Could not find {backend}')
if not frontend.exists():
    raise SystemExit(f'Could not find {frontend}')

s = backend.read_text(encoding='utf-8')

repls = [
    ("""FROM manager_users mu\n            JOIN users u ON u.id = mu.user_id\n            LEFT JOIN gps_allocations_per_user g ON g.user_id = mu.user_id AND COALESCE(g.is_active, TRUE) = TRUE\n            LEFT JOIN areas a ON a.id = g.area_id\n            ORDER BY mu.id DESC""",
     """FROM manager_users mu\n            JOIN users u ON u.id = mu.user_id\n            LEFT JOIN gps_allocations_per_user g ON g.user_id = mu.user_id AND COALESCE(g.is_active, TRUE) = TRUE\n            LEFT JOIN areas a ON a.id = g.area_id\n            WHERE COALESCE(mu.is_active, TRUE) = TRUE AND COALESCE(u.is_active, TRUE) = TRUE\n            ORDER BY mu.id DESC"""),
    ("""WHERE mu.franchise_user_id = :franchise_user_id\n            ORDER BY mu.id DESC""",
     """WHERE mu.franchise_user_id = :franchise_user_id\n              AND COALESCE(mu.is_active, TRUE) = TRUE\n              AND COALESCE(u.is_active, TRUE) = TRUE\n            ORDER BY mu.id DESC"""),
    ("""FROM employee_users eu\n            JOIN users u ON u.id = eu.user_id\n            LEFT JOIN gps_allocations_per_user g ON g.user_id = eu.user_id AND COALESCE(g.is_active, TRUE) = TRUE\n            LEFT JOIN areas a ON a.id = g.area_id\n            ORDER BY eu.id DESC""",
     """FROM employee_users eu\n            JOIN users u ON u.id = eu.user_id\n            LEFT JOIN gps_allocations_per_user g ON g.user_id = eu.user_id AND COALESCE(g.is_active, TRUE) = TRUE\n            LEFT JOIN areas a ON a.id = g.area_id\n            WHERE COALESCE(eu.is_active, TRUE) = TRUE AND COALESCE(u.is_active, TRUE) = TRUE\n            ORDER BY eu.id DESC"""),
    ("""WHERE eu.franchise_user_id = :franchise_user_id\n            ORDER BY eu.id DESC""",
     """WHERE eu.franchise_user_id = :franchise_user_id\n              AND COALESCE(eu.is_active, TRUE) = TRUE\n              AND COALESCE(u.is_active, TRUE) = TRUE\n            ORDER BY eu.id DESC"""),
]
for old,new in repls:
    if old in s:
        s=s.replace(old,new)

marker = '@router.post("/managers/{manager_id}/reset-password")'
alias = """

@router.post("/managers/{manager_id}/delete")
def delete_manager_post(manager_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return delete_manager(manager_id, current_user, db)


@router.post("/employees/{employee_id}/delete")
def delete_employee_post(employee_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return delete_employee(employee_id, current_user, db)

"""
if marker in s and 'def delete_employee_post(' not in s:
    s=s.replace(marker, alias + marker)
backend.write_text(s, encoding='utf-8')

f = frontend.read_text(encoding='utf-8')
old = """      setViewItem(data)\n      setViewTitle(type === 'employees' ? 'Employee Information' : 'Manager Information')\n      setActiveSubTab('view')"""
new = """      setViewItem(data)\n      setViewTitle(type === 'employees' ? 'Employee Information' : 'Manager Information')\n      setActiveSubTab('view')\n      setTimeout(() => document.querySelector('.detail-panel')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50)"""
if old in f:
    f=f.replace(old,new)

old = """      await apiFetch(`/franchise-staff/${type}/${id}`, { method: 'DELETE' })\n      setMsg(`${label[0].toUpperCase() + label.slice(1)} made inactive.`)\n      load()"""
new = """      await apiFetch(`/franchise-staff/${type}/${id}/delete`, { method: 'POST' })\n      setMsg(`${label[0].toUpperCase() + label.slice(1)} made inactive.`)\n      if (viewItem && viewItem.id === id) setViewItem(null)\n      await load()"""
if old in f:
    f=f.replace(old,new)

f=f.replace("{managers.map((m) => <tr", "{managers.filter((m) => m.is_active !== false && m.login_active !== false).map((m) => <tr")
f=f.replace("{employees.map((e) => <tr", "{employees.filter((e) => e.is_active !== false && e.login_active !== false).map((e) => <tr")

frontend.write_text(f, encoding='utf-8')
print('Applied HR Staff View/Delete fix.')
